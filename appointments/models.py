from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class AppointmentSlot(models.Model):
    STATUS_CHOICES = [
        ("available", "Available"),
        ("booked", "Booked"),
        ("cancelled", "Cancelled"),
    ]

    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="slots")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="available")

    class Meta:
        indexes = [
            models.Index(fields=["doctor", "start_time", "status"]),
        ]

    def __str__(self):
        return f"{self.doctor_id} {self.start_time} - {self.end_time} ({self.status})"


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("booked", "Booked"),
        ("cancelled", "Cancelled"),
        ("rescheduled", "Rescheduled"),
    ]

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appointments_as_patient")
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appointments_as_doctor")
    slot = models.OneToOneField(AppointmentSlot, on_delete=models.PROTECT, related_name="appointment")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="booked")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Appt #{self.id} patient={self.patient_id} doctor={self.doctor_id} ({self.status})"


class OutboxEvent(models.Model):
    topic = models.CharField(max_length=255)
    key = models.CharField(max_length=255, blank=True, null=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["published_at", "created_at"])]
