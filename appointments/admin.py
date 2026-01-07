from django.contrib import admin
from .models import AppointmentSlot, Appointment

admin.site.register(AppointmentSlot)
admin.site.register(Appointment)
