from django.urls import path

from . import api, views

app_name = 'tgbot'

urlpatterns = [
    path('webhook/', views.legacy_webhook, name='webhook'),
    path(f'webhook/{api.webhook_path_token()}/', views.webhook, name='hidden_webhook'),
    path('link/', views.link, name='link'),
    path('unlink/', views.unlink, name='unlink'),
]
