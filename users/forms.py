from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .backends import normalize_phone, phone_variants

User = get_user_model()

_input_attrs = {'class': 'form-control'}
_pw_attrs = {'class': 'form-control', 'placeholder': '••••••••'}


class RegisterForm(forms.ModelForm):
    """Ism, familiya, telefon va parol — login (username) telefondan yasaladi."""
    # Longer than the model's 15 so '+998 90 123 45 67' fits; it is saved normalized.
    phone_number = forms.CharField(max_length=25, widget=forms.TextInput(attrs={
        **_input_attrs, 'placeholder': '+998 90 123 45 67', 'type': 'tel', 'autocomplete': 'tel'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={**_pw_attrs, 'autocomplete': 'new-password'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number']
        widgets = {
            'first_name': forms.TextInput(attrs={**_input_attrs, 'placeholder': 'Ismingiz', 'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={**_input_attrs, 'placeholder': 'Familiyangiz', 'autocomplete': 'family-name'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('first_name', 'last_name', 'phone_number'):
            self.fields[name].required = True
        self.fields['first_name'].error_messages['required'] = "Ismingizni kiriting."
        self.fields['last_name'].error_messages['required'] = "Familiyangizni kiriting."
        self.fields['phone_number'].error_messages['required'] = "Telefon raqamingizni kiriting."
        self.fields['password'].error_messages['required'] = "Parol kiriting."

    def clean_phone_number(self):
        phone = normalize_phone(self.cleaned_data.get('phone_number'))
        if not phone:
            raise forms.ValidationError("To'g'ri telefon raqam kiriting (masalan: +998 90 123 45 67).")
        if User.objects.filter(phone_number__in=phone_variants(phone)).exists():
            raise forms.ValidationError("Bu telefon raqam bilan hisob allaqachon bor. Kirish sahifasidan kiring.")
        return phone

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        try:
            validate_password(password)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = _free_username(self.cleaned_data['phone_number'].lstrip('+'))
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


def _free_username(base):
    username, n = base, 1
    while User.objects.filter(username__iexact=username).exists():
        n += 1
        username = f'{base}_{n}'
    return username


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': "Telefon raqam yoki parol noto'g'ri.",
        'inactive': "Bu hisob bloklangan. Administratorga murojaat qiling.",
    }
