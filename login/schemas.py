"""
Marshmallow schemas for runtime validation of user registration data.
This provides an additional validation layer on top of Django's form validation.
"""

from marshmallow import Schema, fields, validate, validates, validates_schema, ValidationError
from django.contrib.auth.models import User
import re


class UserRegistrationSchema(Schema):
    """
    Marshmallow schema for validating user registration data.
    Provides runtime verification of all registration inputs.
    """
    
    username = fields.Str(
        required=True,
        validate=[
            validate.Length(min=3, max=150, error="Username must be between 3 and 150 characters."),
            validate.Regexp(
                r'^[\w.@+-]+$',
                error="Username can only contain letters, digits, and @/./+/-/_ characters."
            )
        ]
    )
    
    email = fields.Email(
        required=True,
        error_messages={'invalid': 'Please provide a valid email address.'}
    )
    
    password = fields.Str(
        required=True,
        load_only=True,
        validate=validate.Length(min=8, error="Password must be at least 8 characters long.")
    )
    
    password_confirm = fields.Str(
        required=True,
        load_only=True
    )
    
    first_name = fields.Str(
        required=False,
        validate=validate.Length(max=150),
        load_default=""
    )
    
    last_name = fields.Str(
        required=False,
        validate=validate.Length(max=150),
        load_default=""
    )
    
    user_type = fields.Str(
        required=True,
        validate=validate.OneOf(['patient', 'doctor'], error="User type must be 'patient' or 'doctor'.")
    )

    @validates('username')
    def validate_username_unique(self, value):
        """Runtime verification: Check if username already exists."""
        if User.objects.filter(username=value).exists():
            raise ValidationError(f"Username '{value}' is already taken.")
    
    @validates('email')
    def validate_email_unique(self, value):
        """Runtime verification: Check if email already exists."""
        if User.objects.filter(email=value).exists():
            raise ValidationError(f"Email '{value}' is already registered.")
    
    @validates('password')
    def validate_password_strength(self, value):
        """Runtime verification: Enforce password complexity rules."""
        errors = []
        
        if not re.search(r'[A-Z]', value):
            errors.append("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', value):
            errors.append("Password must contain at least one lowercase letter.")
        if not re.search(r'\d', value):
            errors.append("Password must contain at least one digit.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            errors.append("Password must contain at least one special character.")
        
        if errors:
            raise ValidationError(errors)
    
    @validates_schema
    def validate_passwords_match(self, data, **kwargs):
        """Runtime verification: Ensure passwords match."""
        password = data.get('password')
        password_confirm = data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise ValidationError({'password_confirm': ['Passwords do not match.']})
    
    @validates_schema
    def validate_doctor_email_domain(self, data, **kwargs):
        """Runtime verification: Doctors must use @clinica.ro email."""
        user_type = data.get('user_type')
        email = data.get('email')
        
        if user_type == 'doctor' and email and not email.endswith('@clinica.ro'):
            raise ValidationError({'email': ['Doctors must register with a @clinica.ro email address.']})


class EmailVerificationSchema(Schema):
    """Schema for validating email verification tokens."""
    
    token = fields.UUID(
        required=True,
        error_messages={'invalid': 'Invalid verification token format.'}
    )


class PasswordResetSchema(Schema):
    """Schema for validating password reset requests."""
    
    email = fields.Email(
        required=True,
        error_messages={'invalid': 'Please provide a valid email address.'}
    )
    
    @validates('email')
    def validate_email_exists(self, value):
        """Runtime verification: Check if email exists in system."""
        if not User.objects.filter(email=value).exists():
            raise ValidationError("No account found with this email address.")
