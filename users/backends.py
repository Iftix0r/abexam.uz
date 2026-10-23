import re

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def normalize_phone(raw):
    """'+998 90 123-45-67', '998901234567' and '901234567' all become
    '+998901234567'. Returns '' when the text isn't a phone number."""
    raw = (raw or '').strip()
    if not re.fullmatch(r'\+?[\d\s\-()]{7,20}', raw):
        return ''
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 9:
        digits = '998' + digits
    if not 10 <= len(digits) <= 14:
        return ''
    return '+' + digits


def phone_variants(phone):
    """Spellings an already normalized number may have been saved under
    before registration started normalizing it."""
    digits = phone.lstrip('+')
    variants = {phone, digits}
    if digits.startswith('998') and len(digits) == 12:
        variants.add(digits[3:])
    return variants


class PhoneOrUsernameBackend(ModelBackend):
    """Students log in with their phone number; older accounts and staff can
    still use their username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        phone = normalize_phone(username)
        if phone and password is not None:
            user = (get_user_model().objects
                    .filter(phone_number__in=phone_variants(phone)).order_by('pk').first())
            if user and user.check_password(password) and self.user_can_authenticate(user):
                return user
        return super().authenticate(request, username=username, password=password, **kwargs)
