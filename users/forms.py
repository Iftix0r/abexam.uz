from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from datetime import date

from django.utils import timezone

from .backends import is_uz_mobile, normalize_phone, phone_variants
from .models import age_on
from .regions import REGIONS

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
        if not is_uz_mobile(phone):
            raise forms.ValidationError("O'zbekiston mobil raqamini kiriting (masalan: +998 90 123 45 67).")
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


MIN_AGE = 13  # the privacy policy: the service is not for younger children
MAX_AGE = 100


class DetailsForm(forms.Form):
    """Birth date and region, asked in the welcome window and on the profile."""
    birth_day = forms.IntegerField(min_value=1, max_value=31)
    birth_month = forms.IntegerField(min_value=1, max_value=12)
    birth_year = forms.IntegerField()
    region = forms.ChoiceField(choices=[(r, r) for r in REGIONS])
    district = forms.CharField(max_length=40)

    def clean(self):
        data = super().clean()
        if self.errors:
            raise forms.ValidationError("Barcha maydonlarni to'ldiring.")
        try:
            birth_date = date(data['birth_year'], data['birth_month'], data['birth_day'])
        except ValueError:
            raise forms.ValidationError("Bunday sana yo'q. Kun va oyni tekshiring.")
        age = age_on(birth_date, timezone.localdate())
        if age < MIN_AGE:
            raise forms.ValidationError(f"AbExam {MIN_AGE} yoshdan katta foydalanuvchilar uchun.")
        if age > MAX_AGE:
            raise forms.ValidationError("Tug'ilgan yilni tekshiring.")
        if data['district'] not in REGIONS[data['region']]:
            raise forms.ValidationError("Tuman tanlangan viloyatga tegishli emas.")
        data['birth_date'] = birth_date
        return data

    def apply_to(self, user):
        user.birth_date = self.cleaned_data['birth_date']
        user.region = self.cleaned_data['region']
        user.district = self.cleaned_data['district']

    @property
    def error_text(self):
        return ' '.join(self.non_field_errors())


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
