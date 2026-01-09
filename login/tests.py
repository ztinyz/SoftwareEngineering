from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from datetime import timedelta
from .models import UserProfile
import uuid
from axes.models import AccessAttempt
import time
from unittest.mock import patch

@override_settings(HCAPTCHA_TESTING=True)
class CaptchaTestCase(TestCase):
    pass


class RegistrationTests(CaptchaTestCase):

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_user_registration_patient(self, mock_validate):
        mock_validate.return_value = True
        
        response = self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'patient1',
            'email': 'patient@test.com',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'patient',
            'register-h-captcha-response': 'PASSED',
        })

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get(username='patient1')
        profile = UserProfile.objects.get(user=user)

        self.assertEqual(profile.user_type, 'patient')
        self.assertEqual(profile.code, '0000')
        self.assertTrue(user.check_password('StrongPass123!'))
        self.assertIsNotNone(profile.verification_token_expires)
        self.assertTrue(profile.verification_token_expires > timezone.now())

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_doctor_registration_code_generated(self, mock_validate):
        mock_validate.return_value = True
        
        self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'doctor1',
            'email': 'doctor@clinica.ro',  # Doctors must use @clinica.ro domain
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'doctor',
            'register-h-captcha-response': 'PASSED',
        })

        profile = UserProfile.objects.get(user__username='doctor1')
        self.assertNotEqual(profile.code, '0000')
        self.assertEqual(len(profile.code), 10)
        self.assertTrue(profile.code.isalnum())


class LoginTests(CaptchaTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            email='test@test.com',
            password='StrongPass123!'
        )
        UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4(),
            verification_token_expires=timezone.now() + timedelta(hours=24)
        )

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_login_success(self, mock_validate):
        mock_validate.return_value = True
        
        response = self.client.post(reverse('login:login'), {
            'buton_login': 'buton_login',
            'username': 'user1',
            'password': 'StrongPass123!',
            'login-h-captcha-response': 'PASSED',
        })
        self.assertEqual(response.status_code, 302)

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_login_invalid_credentials(self, mock_validate):
        mock_validate.return_value = True
        
        response = self.client.post(reverse('login:login'), {
            'buton_login': 'buton_login',
            'username': 'user1',
            'password': 'WrongPassword',
            'login-h-captcha-response': 'PASSED',
        })
        self.assertContains(response, 'Invalid email or password.')
        self.assertIn('login_form', response.context)
        self.assertIn('registration_form', response.context)


class DashboardAccessTests(CaptchaTestCase):

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('login:dash'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login:login'), response.url)


class DashboardUpdateTests(CaptchaTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            email='old@test.com',
            password='StrongPass123!'
        )
        UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4(),
            verification_token_expires=timezone.now() + timedelta(hours=24)
        )
        self.client.force_login(self.user)

    def test_update_username_email(self):
        self.client.post(reverse('login:dash'), {
            'username': 'newuser',
            'email': 'new@test.com',
        })

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newuser')
        self.assertEqual(self.user.email, 'new@test.com')

    def test_password_change_keeps_session(self):
        response = self.client.post(reverse('login:dash'), {
            'username': 'user1',
            'email': 'old@test.com',
            'password': 'NewStrongPass123!',
            'password_confirm': 'NewStrongPass123!',
        })

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass123!'))

        response = self.client.get(reverse('login:dash'))
        self.assertEqual(response.status_code, 200)


class EmailVerificationTests(CaptchaTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            email='test@test.com',
            password='StrongPass123!'
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4(),
            verification_token_expires=timezone.now() + timedelta(hours=24)
        )
        self.client.force_login(self.user)

    def test_verification_email_sent(self):
        self.client.post(reverse('login:dash'), {
            'email_resend': 'email_resend'
        })

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your email address', mail.outbox[0].subject)
        self.assertIn('This link will expire in 24 hours', mail.outbox[0].body)

    def test_verify_email_token(self):
        token = self.profile.verification_token
        response = self.client.get(
            reverse('login:verify_email', args=[token])
        )

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)
        self.assertIsNone(self.profile.verification_token)
        self.assertIsNone(self.profile.verification_token_expires)
        self.assertContains(response, 'Email verified successfully')

    def test_verify_email_expired_token(self):
        self.profile.verification_token_expires = timezone.now() - timedelta(hours=1)
        self.profile.save()

        token = self.profile.verification_token
        response = self.client.get(
            reverse('login:verify_email', args=[token])
        )

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_verified)
        self.assertContains(response, 'expired')

    def test_verify_email_already_verified(self):
        self.profile.email_verified = True
        self.profile.save()

        token = self.profile.verification_token
        response = self.client.get(
            reverse('login:verify_email', args=[token])
        )

        self.assertContains(response, 'already verified')

    def test_resend_generates_new_token(self):
        old_token = self.profile.verification_token
        old_expires = self.profile.verification_token_expires

        # Add a small delay to ensure time difference
        time.sleep(0.01)
        
        self.client.post(reverse('login:dash'), {
            'email_resend': 'email_resend'
        })

        self.profile.refresh_from_db()
        self.assertNotEqual(self.profile.verification_token, old_token)
        self.assertGreaterEqual(self.profile.verification_token_expires, old_expires)


class LogoutTests(CaptchaTestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            email='test@test.com',
            password='StrongPass123!'
        )
        UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4(),
            verification_token_expires=timezone.now() + timedelta(hours=24)
        )
        self.client.force_login(self.user)

    def test_logout(self):
        response = self.client.post(
            reverse('login:dash'),
            {'Logout': 'Logout'},
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Logged out')

        # check user logged out
        response = self.client.get(reverse('login:dash'))
        self.assertEqual(response.status_code, 302)


class BruteForceProtectionTests(CaptchaTestCase):

    def setUp(self):
        self.username = 'victim_user'
        self.password = 'StrongPass123!'
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password
        )
        UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4(),
            verification_token_expires=timezone.now() + timedelta(hours=24)
        )
        self.login_url = reverse('login:login')

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_axes_lockout_after_five_attempts(self, mock_validate):
        mock_validate.return_value = True
        
        # Perform 5 failed login attempts
        for i in range(5):
            response = self.client.post(self.login_url, {
                'buton_login': 'buton_login',
                'username': self.username,
                'password': 'WrongPassword',
                'login-h-captcha-response': 'PASSED'
            })
            if i < 4:
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Invalid email or password.')

        # 6th attempt should be blocked
        response = self.client.post(self.login_url, {
            'buton_login': 'buton_login',
            'username': self.username,
            'password': self.password,
            'login-h-captcha-response': 'PASSED'
        })

        self.assertEqual(response.status_code, 429)  # Too Many Requests 

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_axes_reset_on_success(self, mock_validate):
        mock_validate.return_value = True
        
        # Perform 3 failed login attempts
        for _ in range(3):
            self.client.post(self.login_url, {
                'buton_login': 'buton_login',
                'username': self.username,
                'password': 'WrongPassword',
                'login-h-captcha-response': 'PASSED'
            })
        
        # Check that attempts were recorded
        attempt = AccessAttempt.objects.filter(username=self.username).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.failures_since_start, 3)

        # Successful login
        self.client.post(self.login_url, {
            'buton_login': 'buton_login',
            'username': self.username,
            'password': self.password,
            'login-h-captcha-response': 'PASSED'
        })

        # Check attempts reset
        self.assertEqual(AccessAttempt.objects.filter(username=self.username).count(), 0)

    @override_settings(AXES_COOLOFF_TIME=timedelta(seconds=1))
    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_axes_cooloff_period(self, mock_validate):
        mock_validate.return_value = True
        
        # Trigger lockout
        for _ in range(5):
            self.client.post(self.login_url, {
                'buton_login': 'buton_login',
                'username': self.username,
                'password': 'Wrong',
                'login-h-captcha-response': 'PASSED'
            })
            
        # Verify locked
        response = self.client.post(self.login_url, {
            'buton_login': 'buton_login',
            'username': self.username,
            'password': self.password,
            'login-h-captcha-response': 'PASSED'
        })
        self.assertEqual(response.status_code, 429)  # Too Many Requests

        # Wait for cooloff
        time.sleep(2)

        # Should be able to login now
        response = self.client.post(self.login_url, {
            'buton_login': 'buton_login',
            'username': self.username,
            'password': self.password,
            'login-h-captcha-response': 'PASSED'
        })
        self.assertEqual(response.status_code, 302)


# ============================================================================
# RUNTIME VERIFICATION TESTS (Marshmallow + Transitions)
# ============================================================================

from marshmallow import ValidationError
from .schemas import UserRegistrationSchema, EmailVerificationSchema
from .registration_state_machine import RegistrationStateMachine


class MarshmallowSchemaTests(TestCase):
    """Tests for Marshmallow schema validation (runtime verification)."""
    
    def setUp(self):
        self.schema = UserRegistrationSchema()
        self.valid_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'user_type': 'patient'
        }
    
    def test_valid_patient_registration(self):
        """Test that valid patient data passes Marshmallow validation."""
        result = self.schema.load(self.valid_data)
        self.assertEqual(result['username'], 'newuser')
        self.assertEqual(result['email'], 'newuser@example.com')
        self.assertEqual(result['user_type'], 'patient')
    
    def test_valid_doctor_registration(self):
        """Test that valid doctor data passes Marshmallow validation."""
        doctor_data = self.valid_data.copy()
        doctor_data['user_type'] = 'doctor'
        doctor_data['email'] = 'doctor@clinica.ro'
        
        result = self.schema.load(doctor_data)
        self.assertEqual(result['user_type'], 'doctor')
        self.assertEqual(result['email'], 'doctor@clinica.ro')
    
    def test_password_mismatch_fails(self):
        """Test that mismatched passwords fail Marshmallow validation."""
        data = self.valid_data.copy()
        data['password_confirm'] = 'DifferentPass123!'
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('password_confirm', context.exception.messages)
    
    def test_doctor_wrong_email_domain_fails(self):
        """Test that doctors with non-clinica.ro email fail validation."""
        data = self.valid_data.copy()
        data['user_type'] = 'doctor'
        data['email'] = 'doctor@gmail.com'
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('email', context.exception.messages)
    
    def test_weak_password_fails(self):
        """Test that weak passwords fail Marshmallow validation."""
        data = self.valid_data.copy()
        data['password'] = 'weakpass'
        data['password_confirm'] = 'weakpass'
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('password', context.exception.messages)
    
    def test_invalid_username_fails(self):
        """Test that invalid usernames fail validation."""
        data = self.valid_data.copy()
        data['username'] = 'ab'  # Too short
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('username', context.exception.messages)
    
    def test_invalid_email_fails(self):
        """Test that invalid email format fails validation."""
        data = self.valid_data.copy()
        data['email'] = 'not-an-email'
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('email', context.exception.messages)
    
    def test_invalid_user_type_fails(self):
        """Test that invalid user type fails validation."""
        data = self.valid_data.copy()
        data['user_type'] = 'admin'  # Not allowed
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('user_type', context.exception.messages)
    
    def test_duplicate_username_fails(self):
        """Test that duplicate usernames fail validation."""
        # Create existing user
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='Test123!'
        )
        
        data = self.valid_data.copy()
        data['username'] = 'existinguser'
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('username', context.exception.messages)
    
    def test_duplicate_email_fails(self):
        """Test that duplicate emails fail validation."""
        User.objects.create_user(
            username='otheruser',
            email='taken@example.com',
            password='Test123!'
        )
        
        data = self.valid_data.copy()
        data['email'] = 'taken@example.com'
        
        with self.assertRaises(ValidationError) as context:
            self.schema.load(data)
        
        self.assertIn('email', context.exception.messages)


class EmailVerificationSchemaTests(TestCase):
    """Tests for email verification token schema."""
    
    def setUp(self):
        self.schema = EmailVerificationSchema()
    
    def test_valid_uuid_token(self):
        """Test that valid UUID tokens pass validation."""
        valid_token = str(uuid.uuid4())
        result = self.schema.load({'token': valid_token})
        self.assertIsNotNone(result['token'])
    
    def test_invalid_token_format_fails(self):
        """Test that invalid token formats fail validation."""
        with self.assertRaises(ValidationError) as context:
            self.schema.load({'token': 'not-a-valid-uuid'})
        
        self.assertIn('token', context.exception.messages)


class StateMachineTests(TestCase):
    """Tests for the registration state machine (Transitions library)."""
    
    def test_initial_state(self):
        """Test that machine starts in 'initial' state."""
        machine = RegistrationStateMachine('testuser')
        self.assertEqual(machine.state, 'initial')
    
    def test_submit_data_transition(self):
        """Test transition from initial to data_submitted."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        self.assertEqual(machine.state, 'data_submitted')
    
    def test_django_validate_transition(self):
        """Test transition from data_submitted to django_validated."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        machine.django_validate()
        self.assertEqual(machine.state, 'django_validated')
    
    def test_marshmallow_validate_transition(self):
        """Test transition from django_validated to marshmallow_validated."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        machine.django_validate()
        machine.set_validation_result(True)
        machine.marshmallow_validate()
        self.assertEqual(machine.state, 'marshmallow_validated')
    
    def test_full_registration_flow(self):
        """Test complete registration state machine flow."""
        machine = RegistrationStateMachine('testuser')
        
        # Step 1: Submit data
        machine.submit_data()
        self.assertEqual(machine.state, 'data_submitted')
        
        # Step 2: Django validation
        machine.django_validate()
        self.assertEqual(machine.state, 'django_validated')
        
        # Step 3: Marshmallow validation
        machine.set_validation_result(True)
        machine.marshmallow_validate()
        self.assertEqual(machine.state, 'marshmallow_validated')
        
        # Step 4: Create user
        machine.create_user()
        self.assertEqual(machine.state, 'user_created')
        
        # Step 5: Send email
        machine.send_verification_email()
        self.assertEqual(machine.state, 'email_sent')
    
    def test_invalid_transition_blocked(self):
        """Test that invalid transitions raise exceptions."""
        machine = RegistrationStateMachine('testuser')
        
        # Cannot go directly to django_validated from initial
        with self.assertRaises(Exception):
            machine.django_validate()
        
        self.assertEqual(machine.state, 'initial')
    
    def test_marshmallow_validation_guard(self):
        """Test that marshmallow_validate is blocked without valid data."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        machine.django_validate()
        
        # Don't set validation_passed to True
        machine.set_validation_result(False)
        
        # Try to transition - it should not change state because guard is False
        # Note: transitions library doesn't raise exception, it just doesn't transition
        result = machine.marshmallow_validate()
        
        # State should remain at django_validated because guard blocked transition
        self.assertEqual(machine.state, 'django_validated')
        # The transition returns False when blocked by guard
        self.assertFalse(result)
    
    def test_failure_transition(self):
        """Test transition to failed state."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        machine.error_message = "Test failure"
        machine.fail()
        
        self.assertEqual(machine.state, 'failed')
    
    def test_state_history_recording(self):
        """Test that state history is properly recorded."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        machine.django_validate()
        
        history = machine.get_state_history()
        self.assertEqual(len(history), 2)
        
        self.assertEqual(history[0]['from_state'], 'initial')
        self.assertEqual(history[0]['to_state'], 'data_submitted')
        
        self.assertEqual(history[1]['from_state'], 'data_submitted')
        self.assertEqual(history[1]['to_state'], 'django_validated')
    
    def test_retry_from_failed(self):
        """Test retry transition from failed state."""
        machine = RegistrationStateMachine('testuser')
        machine.submit_data()
        machine.fail()
        self.assertEqual(machine.state, 'failed')
        
        machine.retry()
        self.assertEqual(machine.state, 'initial')


@override_settings(HCAPTCHA_TESTING=True)
class IntegrationRuntimeVerificationTests(CaptchaTestCase):
    """Integration tests for runtime verification with existing registration."""
    
    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_registration_with_runtime_verification(self, mock_validate):
        """Test that registration works with the new runtime verification layer."""
        mock_validate.return_value = True
        
        response = self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'runtimeuser',
            'email': 'runtime@test.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'user_type': 'patient',
            'register-h-captcha-response': 'PASSED',
        })
        
        # User should be created
        self.assertEqual(User.objects.filter(username='runtimeuser').count(), 1)
        user = User.objects.get(username='runtimeuser')
        profile = UserProfile.objects.get(user=user)
        
        self.assertEqual(profile.user_type, 'patient')
        self.assertFalse(profile.email_verified)
    
    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_weak_password_blocked_by_marshmallow(self, mock_validate):
        """Test that weak passwords are blocked by Marshmallow validation."""
        mock_validate.return_value = True
        
        response = self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'weakpassuser',
            'email': 'weak@test.com',
            'password': 'weak',  # No uppercase, no digit, no special char
            'password_confirm': 'weak',
            'user_type': 'patient',
            'register-h-captcha-response': 'PASSED',
        })
        
        # User should NOT be created due to Marshmallow validation
        self.assertEqual(User.objects.filter(username='weakpassuser').count(), 0)
