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
from functools import wraps
from axes.decorators import axes_dispatch
import logging

from appointments.models import Appointment
from .models import UserProfile
from .forms.registerform import RegistrationForm
from .forms.updateform import AccountUpdateForm
from .forms.captchaform import LoginCaptchaForm, RegisterCaptchaForm
from .forms.loginform import LoginForm

# Import runtime verification components (Marshmallow + Transitions)
from .verification_service import RegistrationVerificationService, format_marshmallow_errors

# Logger for registration audit trail
registration_logger = logging.getLogger('verification_service')


# Custom decorator to require email verification
def email_verified_required(function):
    """Decorator to require email verification before accessing a view"""
    @wraps(function)
    def wrap(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login:login')
        
        try:
            user_profile = request.user.userprofile
            if not user_profile.email_verified:
                messages.warning(request, 'Please verify your email address to access this page.')
                return redirect('login:dash')
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('login:login')
        
        return function(request, *args, **kwargs)
    return wrap


@axes_dispatch
def login_view(request):
    """Handle user login and registration"""
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('login:dash')
    
    # Initialize forms with prefix to avoid conflicts
    registration_form = RegistrationForm(request.POST if request.method == 'POST' and 'buton_register' in request.POST else None)
    login_form = LoginForm(request.POST if request.method == 'POST' and 'buton_login' in request.POST else None)
    login_captcha_form = LoginCaptchaForm(
        request.POST if request.method == 'POST' and 'buton_login' in request.POST else None,
        prefix="login"
    )
    register_captcha_form = RegisterCaptchaForm(
        request.POST if request.method == 'POST' and 'buton_register' in request.POST else None,
        prefix="register"
    )
    
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
                context['message'] = 'Please correct the login form errors.'
                for field, errors in login_form.errors.items():
                    context['message'] += f" {field}: {', '.join(errors)}"
                return render(request, 'login/login.html', context)
            
            if not login_captcha_form.is_valid():
                context['message'] = 'Invalid CAPTCHA. Please try again.'
                return render(request, 'login/login.html', context)
            
            username = login_form.cleaned_data['username']
            password = login_form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if not user:
                context['message'] = 'Invalid username or password.'
                return render(request, 'login/login.html', context)
            
            # Login user
            login(request, user)
            
            # Link any appointments made with this email before registration
            try:
                Appointment.objects.filter(
                    patient__isnull=True,
                    contact_email=user.email
                ).update(patient=user)
            except Exception as e:
                print(f"Appointment linking error: {e}")
            
            messages.success(request, f'Welcome back, {user.username}!')
            
            # Redirect to next parameter or dashboard
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('login:dash')
        
        # Handle Registration
        elif 'buton_register' in request.POST:
            if not register_captcha_form.is_valid():
                context['message'] = 'Invalid CAPTCHA. Please try again.'
                return render(request, 'login/login.html', context)
            
            # ========== RUNTIME VERIFICATION LAYER (Marshmallow + Transitions) ==========
            # Initialize the verification service for state machine tracking
            verification_service = RegistrationVerificationService(request)
            username = request.POST.get('username', 'unknown')
            verification_service.initialize_state_machine(username)
            
            # Record form submission in state machine
            verification_service.record_form_submission()
            
            # ========== EXISTING DJANGO FORM VALIDATION (Preserved) ==========
            if not registration_form.is_valid():
                context['message'] = 'Please correct the registration form errors.'
                for field, errors in registration_form.errors.items():
                    # Handle __all__ errors (form-level validation errors)
                    if field == '__all__':
                        field_name = 'Form'
                    else:
                        field_name = registration_form.fields.get(field)
                        field_name = field_name.label if field_name and field_name.label else field
                    context['message'] += f" {field_name}: {', '.join(errors)}"
                # Record failure in state machine
                verification_service.record_failure(f"Django form validation failed: {registration_form.errors}")
                return render(request, 'login/login.html', context)
            
            # Record Django validation passed in state machine
            verification_service.record_django_validation_passed()
            
            # ========== ADDITIONAL MARSHMALLOW VALIDATION ==========
            # This runs AFTER Django validation as an extra verification layer
            form_data = {
                'username': registration_form.cleaned_data.get('username'),
                'email': registration_form.cleaned_data.get('email'),
                'password': registration_form.cleaned_data.get('password'),
                'password_confirm': registration_form.cleaned_data.get('password_confirm'),
                'first_name': registration_form.cleaned_data.get('first_name', ''),
                'last_name': registration_form.cleaned_data.get('last_name', ''),
                'user_type': registration_form.cleaned_data.get('user_type')
            }
            
            marshmallow_success, validated_data, marshmallow_errors = verification_service.validate_with_marshmallow(form_data)
            
            if not marshmallow_success:
                context['message'] = 'Additional validation failed: '
                context['message'] += format_marshmallow_errors(marshmallow_errors)
                context['validation_errors'] = marshmallow_errors
                registration_logger.warning(f"Marshmallow validation failed for {username}: {marshmallow_errors}")
                return render(request, 'login/login.html', context)
            
            registration_logger.info(f"All validations passed for user: {username}")
            # ========== END RUNTIME VERIFICATION LAYER ==========
            
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
                
                # Record user creation in state machine
                verification_service.record_user_created()
                
                # Send verification email
                subject = 'Verify your email address'
                verification_url = request.build_absolute_uri(
                    reverse('login:verify_email', args=[verification_token])
                )
                message = f'Please click the link to verify your email address: {verification_url}\n\nThis link will expire in 24 hours.'
                
                try:
                    send_mail(
                        subject, 
                        message, 
                        settings.DEFAULT_FROM_EMAIL, 
                        [user.email], 
                        fail_silently=False
                    )
                    # Record email sent in state machine
                    verification_service.record_email_sent()
                except Exception as e:
                    print(f"Email failed: {e}")
                    messages.warning(request, 'Account created but verification email could not be sent. Please request a new one from your dashboard.')
                
                # Clear registration state from session (completed successfully)
                verification_service.clear_registration_state()
                
                # Authenticate and login the new user
                authenticated_user = authenticate(
                    request, 
                    username=user.username, 
                    password=password
                )
                if authenticated_user:
                    login(request, authenticated_user)
                    
                    # Link any appointments made with this email before registration
                    try:
                        Appointment.objects.filter(
                            patient__isnull=True,
                            contact_email=user.email
                        ).update(patient=user)
                    except Exception as e:
                        print(f"Appointment linking error: {e}")
                    
                    messages.info(request, 'Registration successful! Please verify your email address to access all features.')
                    return redirect('login:dash')
                
            except Exception as e:
                print(f"Registration error: {e}")
                context['message'] = f'Internal error during registration: {str(e)}'
                return render(request, 'login/login.html', context)
    
    return render(request, 'login/login.html', context)


def logout_view(request):
    """Handle user logout"""
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
    
    return redirect('login:login')


@login_required(login_url='login:login')
def dash_view(request):
    """Dashboard view for authenticated users"""
    user = request.user
    
    try:
        user_profile = user.userprofile
    except UserProfile.DoesNotExist:
        messages.error(request, 'User profile not found. Please contact support.')
        logout(request)
        return redirect('login:login')
    
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
            message = f'Please click the link to verify your email address: {verification_url}\n\nThis link will expire in 24 hours.'
            
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
                messages.success(request, 'Password updated successfully.')
            else:
                user.save()
                messages.success(request, 'Account updated successfully.')
            
            # Handle patient-doctor linking code
            code = request.POST.get('code', '').strip()
            if code and user_profile.user_type == 'patient':
                # Verify the doctor code exists
                doctor_exists = UserProfile.objects.filter(
                    user_type='doctor',
                    code=code
                ).exists()
                
                if doctor_exists:
                    user_profile.code = code
                    user_profile.save()
                    messages.success(request, 'Successfully linked to doctor.')
                else:
                    messages.error(request, 'Invalid doctor code. Please check and try again.')
            
            return redirect('login:dash')
        else:
            # Show specific form errors
            for field, errors in form.errors.items():
                field_name = form.fields[field].label if field in form.fields else field
                for error in errors:
                    messages.error(request, f'{field_name}: {error}')
    
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
        'doctor': doctor,
        'user': user
    })


def verify_email(request, token):
    """Verify user email address using token with runtime verification"""
    
    # ========== RUNTIME VERIFICATION LAYER (Marshmallow) ==========
    # Validate token format using Marshmallow schema
    verification_service = RegistrationVerificationService(request)
    token_valid, profile_from_marshmallow, token_errors = verification_service.verify_email_token(str(token))
    
    if not token_valid:
        # Marshmallow validation failed (invalid token format)
        error_message = 'Invalid verification token.'
        if token_errors:
            error_message = format_marshmallow_errors(token_errors)
        registration_logger.warning(f"Token validation failed: {error_message}")
        return render(request, 'login/verify_result.html', {
            'success': False,
            'message': error_message,
            'show_resend': True
        })
    # ========== END RUNTIME VERIFICATION LAYER ==========
    
    # Existing verification logic (preserved)
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
            'message': 'Email already verified. You can now use all features.',
            'show_login': not request.user.is_authenticated,
            'show_dashboard': request.user.is_authenticated
        })
    
    # Verify email
    user_profile.email_verified = True
    user_profile.verification_token = None  # Invalidate token
    user_profile.verification_token_expires = None
    user_profile.save()
    
    # Record successful email verification
    registration_logger.info(f"Email verified successfully for user: {user_profile.user.username}")
    
    # Show different message based on authentication status
    if request.user.is_authenticated and request.user == user_profile.user:
        messages.success(request, 'Email verified successfully! You now have full access.')
        return redirect('login:dash')
    
    return render(request, 'login/verify_result.html', {
        'success': True,
        'message': 'Email verified successfully! You can now log in and use all features.',
        'show_login': True
    })


@login_required(login_url='login:login')
@email_verified_required
def Test(request):
    """Test/home page view - requires authentication and email verification"""
    user_profile = request.user.userprofile
    
    return render(request, "login/Test.html", {
        'user': request.user,
        'user_profile': user_profile
    })