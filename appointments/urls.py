from django.urls import path
from . import views

app_name = "appointments"

urlpatterns = [
    path("slots/", views.available_slots, name="available_slots"),
    path("mine/", views.my_appointments, name="my_appointments"),
    path("book/<int:slot_id>/", views.book, name="book"),
    path("cancel/<int:appointment_id>/", views.cancel, name="cancel"),
    path("doctor/slots/new/", views.doctor_create_slot, name="doctor_create_slot"),
    path("doctor/schedule/", views.doctor_schedule, name="doctor_schedule"),
    path("doctor/slots/<int:slot_id>/delete/", views.doctor_delete_slot, name="doctor_delete_slot"),
    path("slots/<int:slot_id>/book/", views.book_slot, name="book_slot"),


]
