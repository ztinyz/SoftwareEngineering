import json
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from confluent_kafka import Producer

from appointments.models import OutboxEvent


class Command(BaseCommand):
    help = "Publish OutboxEvent rows to Kafka"

    def handle(self, *args, **options):
        producer = Producer({"bootstrap.servers": "127.0.0.1:9092"})

        while True:
            events = list(
                OutboxEvent.objects.filter(published_at__isnull=True)
                .order_by("created_at")[:100]
            )

            if not events:
                time.sleep(0.5)
                continue

            for ev in events:
                producer.produce(
                    ev.topic,
                    key=(ev.key or "").encode("utf-8"),
                    value=json.dumps(ev.payload).encode("utf-8"),
                )

            producer.flush()

            with transaction.atomic():
                OutboxEvent.objects.filter(id__in=[e.id for e in events]).update(
                    published_at=timezone.now()
                )
