"""
Verification service that integrates Marshmallow validation with the state machine.
This service provides an additional layer of runtime verification on top of
Django's existing form validation - it does NOT replace the existing validation.
"""

from .schemas import UserRegistrationSchema, EmailVerificationSchema
from .registration_state_machine import RegistrationStateMachine, RegistrationStateManager
from .models import UserProfile
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from marshmallow import ValidationError as MarshmallowValidationError
import uuid
import secrets
import string
import logging

logger = logging.getLogger('verification_service')


class RegistrationVerificationService:
    """
    Service class that adds Marshmallow validation and state machine tracking
    as an additional layer on top of Django's existing form validation.
    
    This does NOT replace Django form validation - both validations run.
    """
    
    def __init__(self, request):
        self.request = request
        self.schema = UserRegistrationSchema()
        self.errors = {}
        self.validated_data = None
        self.state_machine = None
    
    def initialize_state_machine(self, username):
        """
        Initialize or retrieve the state machine for tracking registration progress.
        """
        self.state_machine = RegistrationStateManager.get_or_create(
            self.request, 
            username
        )
        return self.state_machine
    
    def record_form_submission(self):
        """Record that form data was submitted (first step)."""
        if self.state_machine and self.state_machine.state == 'initial':
            try:
                self.state_machine.submit_data()
                RegistrationStateManager.save(self.request, self.state_machine)
                return True
            except Exception as e:
                logger.error(f"State transition error on submit: {e}")
        return False
    
    def record_django_validation_passed(self):
        """Record that Django form validation passed."""
        if self.state_machine and self.state_machine.state == 'data_submitted':
            try:
                self.state_machine.django_validate()
                RegistrationStateManager.save(self.request, self.state_machine)
                return True
            except Exception as e:
                logger.error(f"State transition error on django_validate: {e}")
        return False
    
    def validate_with_marshmallow(self, form_data):
        """
        Perform additional Marshmallow validation on the registration data.
        This runs AFTER Django form validation has already passed.
        
        Args:
            form_data: Dictionary containing registration form data
            
        Returns:
            Tuple of (success: bool, validated_data: dict or None, errors: dict or None)
        """
        try:
            self.validated_data = self.schema.load(form_data)
            self.state_machine.set_validation_result(True)
            
            # Transition to marshmallow_validated state
            if self.state_machine.state == 'django_validated':
                self.state_machine.marshmallow_validate()
                RegistrationStateManager.save(self.request, self.state_machine)
            
            logger.info(f"Marshmallow validation passed for user: {form_data.get('username')}")
            return True, self.validated_data, None
            
        except MarshmallowValidationError as e:
            self.errors = e.messages
            self.state_machine.set_validation_result(False, self.errors)
            self.state_machine.error_message = str(self.errors)
            
            logger.warning(f"Marshmallow validation failed: {self.errors}")
            
            # Don't transition to failed - let the existing flow handle the error
            RegistrationStateManager.save(self.request, self.state_machine)
            return False, None, self.errors
    
    def record_user_created(self):
        """Record that user was successfully created."""
        if self.state_machine and self.state_machine.state == 'marshmallow_validated':
            try:
                self.state_machine.create_user()
                RegistrationStateManager.save(self.request, self.state_machine)
                return True
            except Exception as e:
                logger.error(f"State transition error on create_user: {e}")
        return False
    
    def record_email_sent(self):
        """Record that verification email was sent."""
        if self.state_machine and self.state_machine.state == 'user_created':
            try:
                self.state_machine.send_verification_email()
                RegistrationStateManager.save(self.request, self.state_machine)
                return True
            except Exception as e:
                logger.error(f"State transition error on send_email: {e}")
        return False
    
    def verify_email_token(self, token_string):
        """
        Verify email token using Marshmallow schema validation.
        
        Args:
            token_string: The verification token from the URL
            
        Returns:
            Tuple of (success: bool, user_profile: UserProfile or None, errors: dict or None)
        """
        # Validate token format with Marshmallow
        email_schema = EmailVerificationSchema()
        try:
            validated = email_schema.load({'token': token_string})
        except MarshmallowValidationError as e:
            logger.warning(f"Token validation failed: {e.messages}")
            return False, None, e.messages
        
        # Find user profile with this token
        try:
            profile = UserProfile.objects.get(verification_token=token_string)
        except UserProfile.DoesNotExist:
            return False, None, {'token': ['Invalid or expired verification token.']}
        
        # Check if token has expired
        if profile.verification_token_expires and profile.verification_token_expires < timezone.now():
            return False, None, {'token': ['Verification token has expired. Please request a new one.']}
        
        logger.info(f"Email token verified for user: {profile.user.username}")
        return True, profile, None
    
    def record_email_verified(self):
        """Record that email was successfully verified."""
        if self.state_machine:
            self.state_machine.set_token_validation(True)
            if self.state_machine.state == 'email_sent':
                try:
                    self.state_machine.verify_email()
                    self.state_machine.complete_registration()
                    RegistrationStateManager.save(self.request, self.state_machine)
                    return True
                except Exception as e:
                    logger.error(f"State transition error on verify_email: {e}")
        return False
    
    def record_failure(self, error_message):
        """Record a failure in the registration process."""
        if self.state_machine:
            self.state_machine.error_message = error_message
            try:
                self.state_machine.fail()
                RegistrationStateManager.save(self.request, self.state_machine)
            except Exception as e:
                logger.error(f"State transition error on fail: {e}")
    
    def get_state_history(self):
        """Get the registration state history for debugging."""
        if self.state_machine:
            return self.state_machine.get_state_history()
        return []
    
    def get_current_state(self):
        """Get the current registration state."""
        if self.state_machine:
            return self.state_machine.state
        return None
    
    def clear_registration_state(self):
        """Clear the registration state from session."""
        RegistrationStateManager.clear(self.request)


def format_marshmallow_errors(errors):
    """
    Format Marshmallow validation errors into a user-friendly string.
    
    Args:
        errors: Dictionary of field -> error list
        
    Returns:
        Formatted error string
    """
    error_messages = []
    for field, field_errors in errors.items():
        if isinstance(field_errors, list):
            for error in field_errors:
                error_messages.append(f"{field}: {error}")
        else:
            error_messages.append(f"{field}: {field_errors}")
    return " | ".join(error_messages)
