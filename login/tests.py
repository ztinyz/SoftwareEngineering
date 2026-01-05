from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core import mail
from .models import UserProfile
import uuid


class RegistrationTests(TestCase):

    def test_user_registration_patient(self):
        response = self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'patient1',
            'email': 'patient@test.com',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'patient',
        })

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get(username='patient1')
        profile = UserProfile.objects.get(user=user)

        self.assertEqual(profile.user_type, 'patient')
        self.assertEqual(profile.code, '0000')
        self.assertTrue(user.check_password('StrongPass123!'))

    def test_doctor_registration_code_generated(self):
        self.client.post(reverse('login:login'), {
            'buton_register': 'buton_register',
            'username': 'doctor1',
            'email': 'doctor@test.com',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'user_type': 'doctor',
        })

        profile = UserProfile.objects.get(user__username='doctor1')
        self.assertNotEqual(profile.code, '0000')
        self.assertEqual(len(profile.code), 10)

class LoginTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            password='StrongPass123!'
        )

    def test_login_success(self):
        response = self.client.post(reverse('login:login'), {
            'buton_login': 'buton_login',
            'username_login': 'user1',
            'password_login': 'StrongPass123!'
        })

        self.assertEqual(response.status_code, 302)

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login:login'), {
            'buton_login': 'buton_login',
            'username_login': 'user1',
            'password_login': 'WrongPassword'
        })

        self.assertContains(response, 'Invalid credentials')

class DashboardAccessTests(TestCase):

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('login:dash'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login:login'), response.url)


class DashboardUpdateTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            email='old@test.com',
            password='StrongPass123!'
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4()
        )
        self.client.login(username='user1', password='StrongPass123!')

    def test_update_username_email(self):
        response = self.client.post(reverse('login:dash'), {
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


class EmailVerificationTests(TestCase):

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
            verification_token=uuid.uuid4()
        )
        self.client.login(username='user1', password='StrongPass123!')

    def test_verification_email_sent(self):
        response = self.client.post(reverse('login:dash'), {
            'email_resend': 'email_resend'
        })

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your email address', mail.outbox[0].subject)

    def test_verify_email_token(self):
        token = self.profile.verification_token
        response = self.client.get(
            reverse('login:verify_email', args=[token])
        )

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)


class LogoutTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='user1',
            password='StrongPass123!'
        )
        UserProfile.objects.create(
            user=self.user,
            user_type='patient',
            code='0000',
            verification_token=uuid.uuid4()
        )
        self.client.login(username='user1', password='StrongPass123!')

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

