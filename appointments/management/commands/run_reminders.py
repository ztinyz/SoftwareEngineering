import time
from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import Reminder
from appointments.kafka import publish_event  # adjust path to where your publish_event is

class Command(BaseCommand):
    help = "Sends due reminders"

    def handle(self, *args, **options):
        self.stdout.write("Reminder worker started...")

        while True:
            now = timezone.now()

            due = Reminder.objects.select_related(
                "appointment",
                "appointment__patient",
                "appointment__doctor",
                "appointment__slot",
            ).filter(
                status="pending",
                remind_at__lte=now
            )[:50]

            for r in due:
                appt = r.appointment

                # ✅ Kafka REMINDER EVENT
                publish_event(
                    "appointment_reminder_due",
                    {
                        "reminder_id": r.id,
                        "appointment_id": appt.id,
                        "patient_id": appt.patient_id,
                        "doctor_id": appt.doctor_id,
                        "contact_email": appt.contact_email,
                        "slot_id": appt.slot_id,
                        "start_time": appt.slot.start_time.isoformat(),
                        "end_time": appt.slot.end_time.isoformat(),
                        "remind_at": r.remind_at.isoformat(),
                    }
                )

                # mark as sent (so it won't re-send)
                r.status = "sent"
                r.sent_at = timezone.now()
                r.save(update_fields=["status", "sent_at"])

                self.stdout.write(
                    f"⏰ REMINDER SENT: appointment {appt.id} (patient={appt.patient_id} doctor={appt.doctor_id})"
                )

            time.sleep(5)
