import logging

from django.db import DatabaseError
from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import User

from . import services

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def welcome_new_user(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    try:
        services.send_welcome(instance)
    except DatabaseError:  # a greeting must never fail a registration
        logger.exception('AB Admin welcome failed')
