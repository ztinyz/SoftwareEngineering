from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task
def send_password_reset_email(user_email, reset_link):
    """Send password reset email in background"""
    subject = 'Password Reset Request'
    message = f'''
Hello,

You requested a password reset. Click the link below to reset your password:

{reset_link}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.

Best regards,
Clinica Team
    '''
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user_email],
        fail_silently=False,
    )
    return f'Password reset email sent to {user_email}'