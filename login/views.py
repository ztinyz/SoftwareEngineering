from datetime import timedelta
import string
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
import uuid
import secrets
from axes.decorators import axes_dispatch

from .models import UserProfile
from .forms.registerform import RegistrationForm
from .forms.updateform import AccountUpdateForm
from .forms.captchaform import LoginCaptchaForm, RegisterCaptchaForm
from .forms.loginform import LoginForm


@axes_dispatch
def login_view(request):
    """Handle user login and registration"""
    # Initialize empty forms for the GET request
    registration_form = RegistrationForm()
    login_form = LoginForm()
    login_captcha_form = LoginCaptchaForm()
    register_captcha_form = RegisterCaptchaForm()
    
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
            login_form = LoginForm(request.POST)
            login_captcha_form = LoginCaptchaForm(request.POST)
            context['login_form'] = login_form
            context['login_captcha_form'] = login_captcha_form
            
            if login_form.is_valid() and login_captcha_form.is_valid():
                username = login_form.cleaned_data['username']
                password = login_form.cleaned_data['password']
                user = authenticate(request, username=username, password=password)
                
                if user:
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    return HttpResponseRedirect(reverse('login:dash'))
                else:
                    context['message'] = 'Invalid username or password.'
            else:
                if not login_captcha_form.is_valid():
                    context['message'] = 'Invalid CAPTCHA.'
                else:
                    context['message'] = 'Please correct the errors below.'
        
        # Handle Registration
        elif 'buton_register' in request.POST:
            registration_form = RegistrationForm(request.POST)
            register_captcha_form = RegisterCaptchaForm(request.POST)
            context['registration_form'] = registration_form
            context['register_captcha_form'] = register_captcha_form
            
            if registration_form.is_valid() and register_captcha_form.is_valid():
                try:
                    # Create user but don't save to database yet
                    user = registration_form.save(commit=False)
                    password = registration_form.cleaned_data['password']
                    user.set_password(password)
                    user.save()
                    
                    # Get user type and generate code
                    user_type = registration_form.cleaned_data['user_type']
                    code = ''.join(secrets.choice(string.ascii_letters + string.digits) 
                                   for _ in range(10)) if user_type == 'doctor' else '0000'
                    
                    # Generate verification token with expiration
                    verification_token = str(uuid.uuid4())
                    verification_expires = timezone.now() + timedelta(hours=24)
                    
                    # Create user profile
                    UserProfile.objects.create(
                        user=user,
                        user_type=user_type,
                        code=code,
                        verification_token=verification_token,
                        verification_token_expires=verification_expires
                    )
                    
                    # Send verification email
                    subject = 'Verify your email address'
                    verification_url = request.build_absolute_uri(
                        reverse('login:verify_email', args=[verification_token])
                    )
                    message = f'Please click the link to verify your email address: {verification_url}'
                    
                    try:
                        send_mail(
                            subject, 
                            message, 
                            settings.DEFAULT_FROM_EMAIL, 
                            [user.email], 
                            fail_silently=False
                        )
                    except Exception as e:
                        print(f"Email failed: {e}")
                    
                    # Authenticate and login the new user
                    authenticated_user = authenticate(
                        request, 
                        username=user.username, 
                        password=password
                    )
                    if authenticated_user:
                        login(request, authenticated_user, backend='django.contrib.auth.backends.ModelBackend')
                        return HttpResponseRedirect(reverse('login:dash'))
                    
                except Exception as e:
                    print(f"Registration error: {e}")
                    context['message'] = 'Internal error during registration.'
            else:
                if not register_captcha_form.is_valid():
                    context['message'] = 'Invalid CAPTCHA.'
                else:
                    error_msg = ""
                    for field, errors in registration_form.errors.items():
                        error_msg += f"{field}: {errors.as_text()} "
                    context['message'] = f"Form Error - {error_msg}"
    
    return render(request, 'login/login.html', context)


def logout_view(request):
    """Handle user logout"""
    logout(request)
    return render(request, 'login/login.html', {
        'message': 'Logged out.',
        'registration_form': RegistrationForm(),
        'login_form': LoginForm(),
        'login_captcha_form': LoginCaptchaForm(),
        'register_captcha_form': RegisterCaptchaForm(),
    })


@login_required(login_url='login:login')
def dash_view(request):
    """Dashboard view for authenticated users"""
    user = request.user
    
    try:
        user_profile = user.userprofile
    except UserProfile.DoesNotExist:
        return HttpResponse('User profile not found. Please contact support.')
    
    if request.method == 'POST':
        # Handle logout
        if 'Logout' in request.POST:
            return redirect('login:logout')
        
        # Handle email verification resend
        if 'email_resend' in request.POST:
            # Generate new verification token
            verification_token = str(uuid.uuid4())
            verification_expires = timezone.now() + timedelta(hours=24)
            
            user_profile.verification_token = verification_token
            user_profile.verification_token_expires = verification_expires
            user_profile.save()
            
            # Send verification email
            subject = 'Verify your email address'
            verification_url = request.build_absolute_uri(
                reverse('login:verify_email', args=[verification_token])
            )
            message = f'Please click the link to verify your email address: {verification_url}'
            
            try:
                send_mail(
                    subject, 
                    message, 
                    settings.DEFAULT_FROM_EMAIL, 
                    [user.email], 
                    fail_silently=False
                )
                messages.success(request, 'Verification email sent. Please check your inbox.')
            except Exception as e:
                print(f"Email error: {e}")
                messages.error(request, f'Error sending email: {str(e)}')
            
            return redirect('login:dash')
        
        # Handle account update
        form = AccountUpdateForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data.get('password')
            
            if password:
                user.set_password(password)
                user.save()
                # Keep user logged in after password change
                update_session_auth_hash(request, user)
            else:
                user.save()
            
            # Handle patient-doctor linking code
            code = request.POST.get('code', '').strip()
            if code and user_profile.user_type == 'patient':
                user_profile.code = code
                user_profile.save()
            
            messages.success(request, 'Account updated successfully.')
            return redirect('login:dash')
        else:
            messages.error(request, 'Please correct the errors below.')
    
    # Find linked doctor for patients
    doctor = None
    if user_profile.user_type == 'patient' and user_profile.code:
        doctor = UserProfile.objects.filter(
            user_type='doctor',
            code=user_profile.code
        ).select_related('user').first()
    
    return render(request, 'login/dash.html', {
        'form': AccountUpdateForm(instance=user),
        'user_type': user_profile.user_type,
        'email_verified': user_profile.email_verified,
        'code': user_profile.code,
        'doctor': doctor
    })


def verify_email(request, token):
    """Verify user email address using token"""
    user_profile = get_object_or_404(UserProfile, verification_token=token)
    
    # Check if token has expired
    if user_profile.verification_token_expires and user_profile.verification_token_expires < timezone.now():
        return render(request, 'login/verify_result.html', {
            'success': False,
            'message': 'This verification link has expired. Please log in and request a new verification email.',
            'show_resend': True
        })
    
    # Check if already verified
    if user_profile.email_verified:
        return render(request, 'login/verify_result.html', {
            'success': True,
            'message': 'Email already verified. You can now log in.',
            'show_login': True
        })
    
    # Verify email
    user_profile.email_verified = True
    user_profile.verification_token = None  # Invalidate token
    user_profile.verification_token_expires = None
    user_profile.save()
    
    return render(request, 'login/verify_result.html', {
        'success': True,
        'message': 'Email verified successfully! You can now use all features of your account.',
        'show_login': True
    })


def Test(request):
    """Test/home page view"""
    return render(request, "login/Test.html")