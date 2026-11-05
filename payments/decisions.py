"""Approving and rejecting top-ups, one payment or many."""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from chat import services as chat
from users.models import User

from .models import Transaction


def _tell_student(tx, by):
    if tx.status == 'success':
        text = f"To'lovingiz tasdiqlandi: balansingizga {tx.amount:,.0f} so'm qo'shildi.".replace(',', ' ')
    else:
        text = f"{tx.amount:,.0f} so'm to'lov so'rovingiz rad etildi.".replace(',', ' ')
        if tx.reject_reason:
            text += f" Sabab: {tx.reject_reason}"
    chat.message_from_admin(tx.user, by, text, auto=True)


def decide(pk, approve, by, reason=''):
    """Returns (transaction, changed). Only a pending payment changes, so a
    second click or a second admin can never credit the balance twice."""
    with transaction.atomic():
        tx = Transaction.objects.select_for_update().select_related('user').get(pk=pk)
        if tx.status != 'pending':
            return tx, False
        tx.status = 'success' if approve else 'failed'
        tx.decided_by, tx.decided_at = by, timezone.now()
        tx.reject_reason = '' if approve else reason[:200]
        tx.save(update_fields=['status', 'decided_by', 'decided_at', 'reject_reason'])
        if approve:
            User.objects.filter(pk=tx.user_id).update(balance=F('balance') + tx.amount)
    _tell_student(tx, by)
    return tx, True
