from django.urls import path

from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.room_page, name='home'),
    path('xabar/<int:pk>/delete/', views.delete, name='delete'),
    path('xabar/<int:pk>/report/', views.report, name='report'),
    path('xabar/<int:pk>/react/', views.react, name='react'),
    path('xabar/<int:pk>/pin/', views.pin, name='pin'),
    path('yordam/', views.support_page, name='support'),
    path('yordam/messages/', views.support_messages, name='support_messages'),
    path('yordam/send/', views.support_send, name='support_send'),
    path('u/<int:pk>/', views.user_card, name='user_card'),
    path('u/<int:pk>/start/', views.start_chat, name='start_chat'),
    path('u/<int:pk>/block/', views.toggle_block, name='toggle_block'),
    path('lichka/<int:pk>/', views.thread_page, name='thread'),
    path('lichka/<int:pk>/messages/', views.thread_messages, name='thread_messages'),
    path('lichka/<int:pk>/send/', views.thread_send, name='thread_send'),
    path('lichka/<int:pk>/answer/', views.thread_answer, name='thread_answer'),
    path('<slug:slug>/', views.room_page, name='room'),
    path('<slug:slug>/messages/', views.message_list, name='messages'),
    path('<slug:slug>/members/', views.members, name='members'),
    path('<slug:slug>/send/', views.send, name='send'),
]
