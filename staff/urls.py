from django.urls import path
from . import views
from . import telegram_views

app_name = 'staff'
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/new/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/<str:action>/', views.task_action, name='task_action'),
    path('report/', views.report_create, name='report_create'),
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/new/', views.leave_create, name='leave_create'),
    path('leaves/<int:pk>/<str:decision>/', views.leave_decide, name='leave_decide'),
    path('announcements/', views.announcements, name='announcements'),
    path('announcements/<int:pk>/ack/', views.announcement_ack, name='announcement_ack'),
    path('suggestions/new/', views.suggestion_create, name='suggestion_create'),
    path('bot/webhook/<str:path_token>/', telegram_views.webhook, name='bot_webhook'),
]
