from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from hcaptcha.fields import hCaptchaField

class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, validators=[validate_password])
    password_confirm = forms.CharField(widget=forms.PasswordInput)
    user_type = forms.ChoiceField(choices=(('patient', 'Patient'), ('doctor', 'Doctor')))
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    hcaptcha = hCaptchaField()

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        email = cleaned_data.get("email")
        user_type = cleaned_data.get("user_type")
        
        # Validate password match
        if password and password_confirm and password != password_confirm:
            raise ValidationError("Passwords do not match.")
        
        # Validate doctor email domain
        if user_type == 'doctor' and email and not email.endswith('@clinica.ro'):
            raise ValidationError("Doctors must register with a @clinica.ro email.")
        
        return cleaned_data