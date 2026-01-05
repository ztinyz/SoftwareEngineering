from django.contrib.auth.models import User
from django.db import models
import uuid

class UserProfile(models.Model):
    USER_TYPE_CHOICES = (
        ('patient', 'Patient'),
        ('doctor', 'Doctor'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    email_verified = models.BooleanField(default=False)
    verification_token = models.UUIDField(null=True, blank=True)
    verification_token_expires = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=10, default='0000')

    def __str__(self):
        return self.user.username