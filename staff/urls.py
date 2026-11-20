from django.urls import path
from . import views
from . import telegram_views

app_name = 'staff'
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('team/', views.team_list, name='team_list'),
    path('team/add/', views.team_add, name='team_add'),
    path('team/<int:pk>/', views.team_detail, name='team_detail'),
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/new/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/<str:action>/', views.task_action, name='task_action'),
    path('report/', views.report_create, name='report_create'),
    path('reports/', views.reports, name='reports'),
    path('attendance/', views.attendance, name='attendance'),
    path('attendance/<str:action>/', views.attendance_action, name='attendance_action'),
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/new/', views.leave_create, name='leave_create'),
    path('leaves/<int:pk>/<str:decision>/', views.leave_decide, name='leave_decide'),
    path('announcements/', views.announcements, name='announcements'),
    path('announcements/<int:pk>/ack/', views.announcement_ack, name='announcement_ack'),
    path('suggestions/new/', views.suggestion_create, name='suggestion_create'),
    path('suggestions/', views.suggestions, name='suggestions'),
    path('suggestions/<int:pk>/status/', views.suggestion_status, name='suggestion_status'),
    path('bot/webhook/<str:path_token>/', telegram_views.webhook, name='bot_webhook'),
]
