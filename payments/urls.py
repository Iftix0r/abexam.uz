from django.urls import path
from .views import TopUpView

app_name = 'payments'

urlpatterns = [
    path('topup/', TopUpView.as_view(), name='topup'),
]
