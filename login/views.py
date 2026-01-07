from datetime import timedelta
import string
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect,HttpResponse
from django.urls import reverse
from django.contrib.auth import authenticate,login,logout
from .models import UserProfile
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from .forms.registerform import RegistrationForm
from .forms.updateform import AccountUpdateForm
from .forms.captchaform import LoginCaptchaForm, RegisterCaptchaForm
from .forms.loginform import LoginForm
import uuid
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
import secrets
from axes.decorators import axes_dispatch
from django.conf import settings

@axes_dispatch
def login_view(request):
    registration_form = RegistrationForm(request.POST or None)
    login_form = LoginForm(request.POST or None)
    login_captcha_form = LoginCaptchaForm(request.POST or None, prefix="login")
    register_captcha_form = RegisterCaptchaForm(request.POST or None, prefix="register")
    
    context = {
        'registration_form': registration_form,
        'login_form': login_form,
        'login_captcha_form': login_captcha_form,
        'register_captcha_form': register_captcha_form,
        'message': ''
    }

    if request.method == 'POST':
        # Handle Login
        if 'buton_login' in request.POST:
            if not login_form.is_valid():
                context['message'] = 'Invalid email or password.'
                return render(request, 'login/login.html', context)
            if not login_captcha_form.is_valid():
                context['message'] = 'Invalid CAPTCHA.'
                return render(request, 'login/login.html', context)

            username = login_form.cleaned_data['username']
            password = login_form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)

            if not user:
                context['message'] = 'Invalid email or password.'
                return render(request, 'login/login.html', context)

            login(request, user)
            return HttpResponseRedirect(reverse('login:Test'))

        # Handle Registration
        elif 'buton_register' in request.POST:
            if not register_captcha_form.is_valid():
                context['message'] = 'Invalid CAPTCHA.'
                return render(request, 'login/login.html', context)
            
            if registration_form.is_valid():
                try:
                    user = registration_form.save(commit=False)
                    user.set_password(registration_form.cleaned_data['password'])
                    user.save()
                    # Prevent forced logout after password change
                    update_session_auth_hash(request, user)

                    user_type = registration_form.cleaned_data['user_type']
                    if user_type == 'doctor':
                        code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
                    else:
                        code = '0000'

                    # Generate token with expiration
                    verification_expires = timezone.now() + timedelta(hours=24)
                    
                    UserProfile.objects.create(
                        user=user,
                        user_type=user_type,
                        code=code,
                        verification_token=uuid.uuid4(),
                        verification_token_expires=verification_expires
                    )
                    
                    login(request, user)
                    return HttpResponseRedirect(reverse('login:Test'))
                except Exception:
                    context['message'] = 'Internal Error'
            else:
                context['message'] = 'Registration form error.'
    return render(request, 'login/login.html', context)


def logout_view(request):
    logout(request)
    return redirect('http://127.0.0.1:8000')


@login_required(login_url='login:login')
def dash_view(request):
    user = request.user
    user_profile = user.userprofile

    if request.method == 'POST':

        # Logout
        if 'Logout' in request.POST:
            return redirect('login:logout')

        # Send verification email
        if 'email_resend' in request.POST:
            user_profile.verification_token = uuid.uuid4()
            user_profile.verification_token_expires = timezone.now() + timedelta(hours=24)
            user_profile.save()

            send_mail(
                'Verify your email address',
                f'Please click the link to verify your email address. This link will expire in 24 hours. '
                f'http://127.0.0.1:8000/users/verify-email/{user_profile.verification_token}/',
                'no-reply@yourapp.com',
                [user.email],
            )

            return render(request, 'login/dash.html', {
                'message': 'Please check your email to verify your account.'
            })

        # Update account
        form = AccountUpdateForm(request.POST, instance=user)

        if form.is_valid():
            user = form.save(commit=False)

            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
                user.save()
                update_session_auth_hash(request, user)
            else:
                user.save()

            # Patient-Doctor linking code handling
            code = request.POST.get('code', '').strip()
            if code and user_profile.user_type != 'doctor':
                user_profile.code = code
                user_profile.save()

            return redirect('login:dash')

        return render(request, 'login/dash.html', {
            'form': form,
            'message': form.errors
        })

    doctor = None
    if user_profile.user_type == 'patient':
        doctor = UserProfile.objects.filter(
            user_type='doctor',
            code=user_profile.code
        ).first()

    return render(request, 'login/dash.html', {
        'form': AccountUpdateForm(instance=user),
        'user_type': user_profile.user_type,
        'email_verified': user_profile.email_verified,
        'code': user_profile.code,
        'doctor': doctor
    })


def verify_email(request,token):
    user_profile = get_object_or_404(UserProfile, verification_token=token)
    
    # Check if token has expired
    if user_profile.verification_token_expires and user_profile.verification_token_expires < timezone.now():
        return HttpResponse(
            'This verification link has expired. '
            'Please log in and request a new verification email.'
        )
    
    # Check if already verified
    if user_profile.email_verified:
        return HttpResponse('Email already verified.')
    
    user_profile.email_verified = True
    user_profile.verification_token = None  # Invalidate token
    user_profile.verification_token_expires = None
    user_profile.save()
    
    return HttpResponse('Email verified successfully!')


def Test(request):
    return render(request, "login/Test.html")