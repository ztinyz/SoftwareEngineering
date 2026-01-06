from django import forms
from hcaptcha.fields import hCaptchaField

class LoginCaptchaForm(forms.Form):
    hcaptcha = hCaptchaField()

class RegisterCaptchaForm(forms.Form):
    hcaptcha = hCaptchaField()
