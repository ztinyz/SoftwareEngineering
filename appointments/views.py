from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .kafka import publish_event
from .models import Appointment, AppointmentSlot, Reminder

from django.db.models import Exists, OuterRef
from django.contrib.auth import get_user_model
User = get_user_model()


def available_slots(request):
    booked_exists = Appointment.objects.filter(
        slot_id=OuterRef("pk"),
        status="booked",
    )

    qs = (
        AppointmentSlot.objects
        .filter(status="available", start_time__gte=timezone.now())
        .annotate(has_appt=Exists(booked_exists))
        .filter(has_appt=False)
        .select_related("doctor")
        .order_by("start_time")
    )

    doctors = User.objects.filter(is_staff=True).order_by("username")

    doctor_id = request.GET.get("doctor")
    if doctor_id:
        qs = qs.filter(doctor_id=doctor_id)

    slots = qs[:200]  # ✅ slice at the end

    return render(
        request,
        "appointments/available_slots.html",
        {"slots": slots, "doctors": doctors, "selected_doctor": doctor_id},
    )

@login_required
def my_appointments(request: HttpRequest) -> HttpResponse:
    appts = (
        Appointment.objects.filter(patient=request.user)
        .select_related("doctor", "slot")
        .order_by("-created_at")
    )
    return render(request, "appointments/my_appointments.html", {"appts": appts})

from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from .models import AppointmentSlot, Appointment
from .kafka import publish_event  # your publish_event

from django.db import transaction, IntegrityError
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth.decorators import login_required

from .models import AppointmentSlot, Appointment
from .kafka import publish_event



def book_slot(request, slot_id: int):
    slot = get_object_or_404(AppointmentSlot, id=slot_id)

    # ✅ GET -> show form
    if request.method == "GET":
        # basic safety: don't show booking page for unavailable/past
        if slot.status != "available" or slot.start_time < timezone.now():
            messages.error(request, "This slot is not available.")
            return redirect("appointments:available_slots")

        return render(request, "appointments/book_slot.html", {"slot": slot})

    # ✅ POST -> actually book
    contact_email = (request.POST.get("contact_email") or "").strip()

    if not contact_email:
        messages.error(request, "Please enter an email.")
        return redirect("appointments:book_slot", slot_id=slot_id)

    try:
        with transaction.atomic():
            slot = AppointmentSlot.objects.select_for_update().get(id=slot_id)

            if Appointment.objects.filter(slot=slot, status="booked").exists():
                messages.error(request, "This slot is already booked.")
                return redirect("appointments:available_slots")


            if slot.start_time < timezone.now():
                messages.error(request, "This slot is in the past.")
                return redirect("appointments:available_slots")

            if slot.status != "available":
                messages.error(request, "This slot is no longer available.")
                return redirect("appointments:available_slots")

            patient = request.user if request.user.is_authenticated else None

            appt = Appointment.objects.create(
                patient=patient,          
                doctor=slot.doctor,
                slot=slot,
                status="booked",
                contact_email=contact_email,
            )


            slot.status = "booked"
            slot.save(update_fields=["status"])

        # ✅ Kafka audit event (include email so notifier can use it)
        publish_event(
            "appointment_booked",
            {
                "appointment_id": appt.id,
                "slot_id": slot.id,
                "patient_id": request.user.id,
                "doctor_id": slot.doctor_id,
                "contact_email": appt.contact_email,
                "start_time": slot.start_time.isoformat(),
                "end_time": slot.end_time.isoformat(),
            }
        )

        messages.success(request, "Appointment booked!")
        return redirect("appointments:my_appointments")

    except AppointmentSlot.DoesNotExist:
        messages.error(request, "Slot not found.")
        return redirect("appointments:available_slots")

    except IntegrityError:
        messages.error(request, "This slot was just booked by someone else.")
        return redirect("appointments:available_slots")

@login_required
def cancel(request: HttpRequest, appointment_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("appointments:my_appointments")

    try:
        appt = Appointment.objects.select_related("slot").get(id=appointment_id)

        # allow patient OR doctor
        if request.user.id not in (appt.patient_id, appt.doctor_id):
            raise PermissionError("Not allowed")

        appt.status = "cancelled"
        appt.save(update_fields=["status"])

        appt.slot.status = "available"
        appt.slot.save(update_fields=["status"])

        Reminder.objects.filter(appointment=appt, status="pending").update(status="cancelled")


        # Kafka CANCEL EVENT
        publish_event(
            "appointment_cancelled",
            {
                "appointment_id": appt.id,
                "slot_id": appt.slot.id,
                "patient_id": appt.patient_id,
                "doctor_id": appt.doctor_id,
                "contact_email": appt.contact_email,
                "start_time": appt.slot.start_time.isoformat(),
                "end_time": appt.slot.end_time.isoformat(),
                "cancelled_by": request.user.id,
            }
        )

        messages.success(request, "Appointment cancelled.")
    except Exception as e:
        messages.error(request, f"Could not cancel: {e}")

    return redirect("appointments:my_appointments")


@login_required
def doctor_create_slot(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can create slots.")

    if request.method == "GET":
        return render(request, "appointments/doctor_create_slot.html")

    start_str = request.POST.get("start_time")
    end_str = request.POST.get("end_time")

    start_dt = parse_datetime(start_str.replace("T", " ")) if start_str else None
    end_dt = parse_datetime(end_str.replace("T", " ")) if end_str else None

    if not start_dt or not end_dt:
        messages.error(request, "Invalid datetime format.")
        return redirect("appointments:doctor_create_slot")

    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt)
    if timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt)

    if start_dt >= end_dt:
        messages.error(request, "Start must be before end.")
        return redirect("appointments:doctor_create_slot")

    if start_dt < timezone.now():
        messages.error(request, "Cannot create slots in the past.")
        return redirect("appointments:doctor_create_slot")

    AppointmentSlot.objects.create(
        doctor=request.user,
        start_time=start_dt,
        end_time=end_dt,
        status="available",
    )

    messages.success(request, "Slot created.")
    return redirect("appointments:doctor_create_slot")



from django.db.models import OuterRef, Subquery
from .models import Appointment, AppointmentSlot

@login_required
def doctor_schedule(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can view this page.")

    appt_id_sq = Appointment.objects.filter(
        slot_id=OuterRef("pk"),
        status="booked",
    ).values("id")[:1]

    slots = (
        AppointmentSlot.objects
        .filter(doctor=request.user, start_time__gte=timezone.now())
        .annotate(booked_appointment_id=Subquery(appt_id_sq))
        .order_by("start_time")
    )

    return render(request, "appointments/doctor_schedule.html", {"slots": slots})


@login_required
def doctor_delete_slot(request: HttpRequest, slot_id: int) -> HttpResponse:
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can do this.")

    if request.method != "POST":
        return redirect("appointments:doctor_schedule")

    slot = get_object_or_404(AppointmentSlot, id=slot_id, doctor=request.user)

    if slot.status != "available":
        messages.error(request, "You can only delete an available slot.")
        return redirect("appointments:doctor_schedule")

    slot.delete()
    messages.success(request, "Slot deleted.")
    return redirect("appointments:doctor_schedule")
