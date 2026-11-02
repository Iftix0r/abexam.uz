from django.urls import path

from . import views

app_name = 'tgbot'

urlpatterns = [
    path('webhook/', views.webhook, name='webhook'),
    path('link/', views.link, name='link'),
    path('unlink/', views.unlink, name='unlink'),
]
