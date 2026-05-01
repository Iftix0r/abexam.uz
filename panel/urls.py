from django.urls import path
from . import views

app_name = 'panel'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('search/', views.search, name='search'),

    path('users/', views.users_list, name='users'),
    path('users/export/', views.users_export_csv, name='users_export'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('users/<int:pk>/logs/', views.user_login_logs, name='user_logs'),
    path('users/<int:pk>/toggle/', views.user_toggle_active, name='user_toggle'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/balance/', views.user_add_balance, name='user_balance'),
    path('users/<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/make-staff/', views.user_make_staff, name='user_make_staff'),
    path('users/bulk/', views.users_bulk_action, name='users_bulk'),

    path('exams/', views.exams_list, name='exams'),
    path('exams/create/', views.exam_create, name='exam_create'),
    path('exams/<int:pk>/', views.exam_detail, name='exam_detail'),
    path('exams/<int:pk>/edit/', views.exam_edit, name='exam_edit'),
    path('exams/<int:pk>/delete/', views.exam_delete, name='exam_delete'),
    path('exams/<int:pk>/toggle/', views.exam_toggle_active, name='exam_toggle'),
    path('exams/<int:pk>/review/', views.exam_review, name='exam_review'),

    path('transactions/', views.transactions_list, name='transactions'),
    path('transactions/<int:pk>/approve/', views.transaction_approve, name='tx_approve'),
    path('transactions/<int:pk>/reject/', views.transaction_reject, name='tx_reject'),

    path('results/', views.results_list, name='results'),
    path('results/export/', views.results_export_csv, name='results_export'),
    path('create-admin/', views.create_admin, name='create_admin'),
    path('security/', views.security_logs, name='security'),
    path('analytics/', views.analytics, name='analytics'),

    path('exams/generate/', views.exam_generate, name='exam_generate'),
    path('questions/<int:pk>/edit/', views.question_edit, name='question_edit'),
    path('questions/<int:pk>/delete/', views.question_delete, name='question_delete'),
]
