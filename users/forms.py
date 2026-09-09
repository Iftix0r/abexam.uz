from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()

_input_attrs = {'class': 'form-control'}
_pw_attrs = {'class': 'form-control', 'placeholder': '••••••••'}


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs=_pw_attrs))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=_pw_attrs))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone_number']
        widgets = {
            'username': forms.TextInput(attrs={**_input_attrs, 'placeholder': 'Username'}),
            'first_name': forms.TextInput(attrs={**_input_attrs, 'placeholder': 'Ismingiz'}),
            'last_name': forms.TextInput(attrs={**_input_attrs, 'placeholder': 'Familiyangiz'}),
            'email': forms.EmailInput(attrs={**_input_attrs, 'placeholder': 'Email manzil'}),
            'phone_number': forms.TextInput(attrs={**_input_attrs, 'placeholder': '+998XXXXXXXXX'}),
        }

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        try:
            validate_password(password)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)
        return password

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('password') != cleaned_data.get('confirm_password'):
            raise forms.ValidationError("Parollar mos kelmadi!")
        return cleaned_data
