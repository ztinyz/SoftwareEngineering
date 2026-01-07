from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Appointment, AppointmentSlot
from django.shortcuts import render, redirect, get_object_or_404


@login_required
def available_slots(request: HttpRequest) -> HttpResponse:
    slots = AppointmentSlot.objects.filter(
        status="available",
        start_time__gte=timezone.now()
    ).select_related("doctor").order_by("start_time")[:200]

    return render(request, "appointments/available_slots.html", {"slots": slots})


@login_required
def my_appointments(request: HttpRequest) -> HttpResponse:
    appts = Appointment.objects.filter(
        patient=request.user
    ).select_related("doctor", "slot").order_by("-created_at")

    return render(request, "appointments/my_appointments.html", {"appts": appts})


@login_required
def book(request: HttpRequest, slot_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("appointments:available_slots")

    try:
        slot = AppointmentSlot.objects.get(id=slot_id)
        if slot.status != "available":
            raise ValueError("Slot not available")

        # simplest booking for now:
        Appointment.objects.create(
            patient=request.user,
            doctor=slot.doctor,
            slot=slot,
            status="booked",
        )
        slot.status = "booked"
        slot.save(update_fields=["status"])

        messages.success(request, "Appointment booked.")
    except Exception as e:
        messages.error(request, f"Could not book: {e}")

    return redirect("appointments:my_appointments")


@login_required
def cancel(request: HttpRequest, appointment_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("appointments:my_appointments")

    try:
        appt = Appointment.objects.select_related("slot").get(id=appointment_id)

        if request.user.id not in (appt.patient_id, appt.doctor_id):
            raise PermissionError("Not allowed")

        appt.status = "cancelled"
        appt.save(update_fields=["status"])

        appt.slot.status = "available"
        appt.slot.save(update_fields=["status"])

        messages.success(request, "Appointment cancelled.")
    except Exception as e:
        messages.error(request, f"Could not cancel: {e}")

    return redirect("appointments:my_appointments")

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from .models import AppointmentSlot

@login_required
def doctor_create_slot(request):
    # TEMP rule for now: staff users are doctors
    # (we’ll replace this with your real doctor role later)
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can create slots.")

    if request.method == "GET":
        return render(request, "appointments/doctor_create_slot.html")

    # POST
    start_str = request.POST.get("start_time")
    end_str = request.POST.get("end_time")

    start_dt = parse_datetime(start_str.replace("T", " "))
    end_dt = parse_datetime(end_str.replace("T", " "))


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

    from django.http import HttpResponseForbidden
from django.utils import timezone
from .models import AppointmentSlot

@login_required
def doctor_schedule(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can view this page.")

    slots = (
        AppointmentSlot.objects.filter(doctor=request.user, start_time__gte=timezone.now())
        .select_related("appointment")
        .order_by("start_time")
    )
    return render(request, "appointments/doctor_schedule.html", {"slots": slots})

    from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

@login_required
def doctor_delete_slot(request, slot_id: int):
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

    from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import AppointmentSlot, Appointment

@login_required
def book_slot(request, slot_id: int):
    if request.method != "POST":
        return redirect("appointments:available_slots")

    slot = get_object_or_404(AppointmentSlot, id=slot_id)

    # basic rules
    if slot.status != "available" or slot.start_time < timezone.now():
        messages.error(request, "This slot is no longer available.")
        return redirect("appointments:available_slots")

    # create appointment and lock slot
    appt = Appointment.objects.create(
        patient=request.user,
        doctor=slot.doctor,
        slot=slot,
        status="booked",
    )
    slot.status = "booked"
    slot.appointment = appt  # only if your model has this FK/OneToOne
    slot.save()

    messages.success(request, "Appointment booked!")
    return redirect("appointments:my_appointments")
