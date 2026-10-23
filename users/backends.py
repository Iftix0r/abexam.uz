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


# Uzbek mobile operator codes: Beeline 90/91, Ucell 93/94/50, Uzmobile 95/99/77,
# Mobiuz 97/88, Perfectum 98, Humans 33, 55, OQ 20.
UZ_MOBILE_CODES = {'20', '33', '50', '55', '77', '88', '90', '91', '93', '94', '95', '97', '98', '99'}


def is_uz_mobile(phone):
    """True for a normalized '+998XXXXXXXXX' with a real operator code and a
    subscriber part that isn't an obvious fake (0000000, 1234567, …)."""
    if not re.fullmatch(r'\+998\d{9}', phone or ''):
        return False
    code, sub = phone[4:6], phone[6:]
    if code not in UZ_MOBILE_CODES:
        return False
    if len(set(sub)) == 1 or sub in '01234567890' or sub in '09876543210':
        return False
    return True


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
