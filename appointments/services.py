from django.db import transaction
from django.utils import timezone

from .models import Appointment, AppointmentSlot, OutboxEvent


def _emit(topic: str, key: str | None, payload: dict) -> None:
    OutboxEvent.objects.create(topic=topic, key=key, payload=payload)


@transaction.atomic
def book_slot(*, patient, slot_id: int) -> Appointment:
    slot = AppointmentSlot.objects.select_for_update().get(id=slot_id)

    if slot.status != "available":
        raise ValueError("Slot not available")

    appt = Appointment.objects.create(
        patient=patient,
        doctor=slot.doctor,
        slot=slot,
        status="booked",
    )

    slot.status = "booked"
    slot.save(update_fields=["status"])

    _emit(
        topic="appointments.events",
        key=str(appt.id),
        payload={
            "type": "appointment.booked",
            "schemaVersion": 1,
            "appointment_id": appt.id,
            "doctor_id": appt.doctor_id,
            "patient_id": appt.patient_id,
            "slot_id": slot.id,
            "created_at": timezone.now().isoformat(),
        },
    )

    return appt


@transaction.atomic
def cancel_appointment(*, user, appointment_id: int) -> Appointment:
    appt = Appointment.objects.select_for_update().select_related("slot").get(id=appointment_id)

    # basic permission: patient or doctor can cancel
    if user.id not in (appt.patient_id, appt.doctor_id):
        raise PermissionError("Not allowed")

    if appt.status == "cancelled":
        return appt

    appt.status = "cancelled"
    appt.save(update_fields=["status"])

    appt.slot.status = "available"  # or "cancelled" depending on your business rule
    appt.slot.save(update_fields=["status"])

    _emit(
        topic="appointments.events",
        key=str(appt.id),
        payload={
            "type": "appointment.cancelled",
            "schemaVersion": 1,
            "appointment_id": appt.id,
            "doctor_id": appt.doctor_id,
            "patient_id": appt.patient_id,
            "slot_id": appt.slot_id,
            "created_at": timezone.now().isoformat(),
        },
    )

    return appt
