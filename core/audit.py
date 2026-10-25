"""Staff action log: one line per panel action that changes something."""
import logging

from .models import AuditLog
from .utils import get_client_ip

logger = logging.getLogger(__name__)

# action code → label shown in the panel's log
ACTIONS = {
    'balance': "Balans o'zgartirildi",
    'user_edit': 'Foydalanuvchi tahrirlandi',
    'user_block': 'Bloklandi / faollashtirildi',
    'user_delete': "Foydalanuvchi o'chirildi",
    'user_password': 'Parol tiklandi',
    'user_staff': 'Admin huquqi',
    'user_bulk': 'Foydalanuvchilar (ommaviy)',
    'admin_create': 'Admin yaratildi',
    'exam_edit': 'Imtihon tahrirlandi',
    'exam_toggle': "Imtihon yoqildi / o'chirildi",
    'exam_delete': "Imtihon o'chirildi",
    'exam_bulk': 'Imtihonlar (ommaviy)',
    'exam_import': 'Test yuklandi',
    'exam_regrade': 'Natijalar qayta hisoblandi',
    'question_key': "Kalit o'zgartirildi",
    'question_edit': 'Savol tahrirlandi',
    'question_delete': "Savol o'chirildi",
    'notes_edit': 'Notes bloklari',
    'result_grade': 'Natija baholandi',
    'result_delete': "Natija o'chirildi",
    'tx_approve': "To'lov tasdiqlandi",
    'tx_reject': "To'lov rad etildi",
    'group': 'Guruh',
    'settings': 'Sayt sozlamalari',
    'promocode': 'Promokod',
}


def log_action(request, action, target='', target_url='', details=''):
    """Records `action` by request.user. Never raises — the action itself
    already happened and must not fail because its log line did."""
    try:
        user = request.user
        AuditLog.objects.create(
            staff=user, staff_name=getattr(user, 'display_name', '') or user.username,
            action=action, target=str(target)[:255], target_url=str(target_url)[:255],
            details=str(details), ip=get_client_ip(request) or None,
        )
    except Exception:
        logger.exception('audit log write failed (%s)', action)
