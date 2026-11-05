from django.urls import path

from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.room_page, name='home'),
    path('xabar/<int:pk>/delete/', views.delete, name='delete'),
    path('xabar/<int:pk>/report/', views.report, name='report'),
    path('<slug:slug>/', views.room_page, name='room'),
    path('<slug:slug>/messages/', views.message_list, name='messages'),
    path('<slug:slug>/send/', views.send, name='send'),
]
