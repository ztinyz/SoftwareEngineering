import json
from confluent_kafka import Producer

producer = Producer({
    "bootstrap.servers": "127.0.0.1:9092",
})

TOPIC = "appointments.events"


def publish_event(event_type: str, payload: dict):
    event = {
        "type": event_type,
        "payload": payload,
    }

    producer.produce(
        TOPIC,
        json.dumps(event).encode("utf-8")
    )
    producer.flush()
