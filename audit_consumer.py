import json
from confluent_kafka import Consumer

conf = {
    "bootstrap.servers": "localhost:9092",
    "group.id": "audit-service",
    "auto.offset.reset": "earliest",
}

c = Consumer(conf)
c.subscribe(["appointments.events"])

print("Audit consumer started...")

try:
    while True:
        msg = c.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            print("Error:", msg.error())
            continue

        event = json.loads(msg.value().decode("utf-8"))
        print("[AUDIT]", event)

finally:
    c.close()
