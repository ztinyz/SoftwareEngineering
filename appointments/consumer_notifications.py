import json
from confluent_kafka import Consumer

TOPIC = "appointments.events"

c = Consumer({
    "bootstrap.servers": "127.0.0.1:9092",
    "group.id": "appointments-notifications",
    "auto.offset.reset": "earliest",
})

c.subscribe([TOPIC])

print("✅ notifications consumer started...")

try:
    while True:
        msg = c.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            print("Kafka error:", msg.error())
            continue

        event = json.loads(msg.value().decode("utf-8"))
        if event.get("type") == "appointment_booked":
            payload = event.get("payload", {})
            print(f"📩 NOTIFY: Appointment booked -> appt={payload.get('appointment_id')} "
                  f"patient={payload.get('patient_id')} doctor={payload.get('doctor_id')}")
finally:
    c.close()
