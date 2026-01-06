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
            'email': 'doctor@clinica.ro',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'doctor',
            'register-h-captcha-response': 'PASSED',
        })

        profile = UserProfile.objects.get(user__username='doctor1')
        self.assertNotEqual(profile.code, '0000')
        self.assertEqual(len(profile.code), 10)
        self.assertTrue(profile.code.isalnum())

    @patch('hcaptcha.fields.hCaptchaField.validate')
    def test_doctor_registration_requires_clinica_email(self, mock_validate):
        mock_validate.return_value = True

        # Try registering a doctor with a non-clinica.ro email
        response = self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'doctor2',
            'email': 'doctor@gmail.com',  # Invalid email
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'doctor',
            'doctor_code': 'VALIDCODE123',  # assume valid code exists for test
            'register-h-captcha-response': 'PASSED',
        })

        # Access the registration form from context
        form = response.context.get('registration_form')
        self.assertIsNotNone(form)
        self.assertIn('Doctors must register with a @clinica.ro email.', form.errors['__all__'])

        # User should not be created
        self.assertFalse(User.objects.filter(username='doctor2').exists())

        # Register a doctor with a valid @clinica.ro email
        response = self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'doctor3',
            'email': 'doctor@clinica.ro',  # Valid email
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'doctor',
            'doctor_code': 'VALIDCODE123',
            'register-h-captcha-response': 'PASSED',
        })

        # User should be created
        self.assertTrue(User.objects.filter(username='doctor3').exists())
        profile = UserProfile.objects.get(user__username='doctor3')
        self.assertEqual(profile.user_type, 'doctor')

        
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