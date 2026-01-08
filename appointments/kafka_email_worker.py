import os
import sys
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Clinica.settings")

import django
django.setup()

from confluent_kafka import Consumer
from django.conf import settings
from django.core.mail import send_mail

consumer = Consumer({
    "bootstrap.servers": "127.0.0.1:9092",
    "group.id": "email-service-v2",   # ✅ change group id so you see events again
    "auto.offset.reset": "earliest",
})

consumer.subscribe(["appointments.events"])

print("📧 Email worker started...")

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Kafka error:", msg.error())
        continue

    try:
        event = json.loads(msg.value().decode("utf-8"))
    except Exception as e:
        print("Bad JSON:", e, msg.value())
        continue

    event_type = event.get("type")
    payload = event.get("payload") or {}

    # ✅ only handle these two
    if event_type not in ("appointment_booked", "appointment_cancelled"):
        continue

    email = payload.get("contact_email")
    if not email:
        print(f"No contact_email for {event_type}, skipping")
        continue

    start = payload.get("start_time", "N/A")
    end = payload.get("end_time", "N/A")

    if event_type == "appointment_booked":
        subject = "Your appointment is confirmed"
        message = (
            "Your appointment has been booked.\n\n"
            f"Start: {start}\n"
            f"End: {end}\n"
        )
    else:
        subject = "Your appointment was cancelled"
        message = (
            "Your appointment has been cancelled.\n\n"
            f"Start: {start}\n"
            f"End: {end}\n"
        )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,  # ✅ NOT None
            recipient_list=[email],
            fail_silently=False,
        )
        print(f"📧 {event_type} email sent to {email}")
    except Exception as e:
        print("Email send failed:", repr(e))
