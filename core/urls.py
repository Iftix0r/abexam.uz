from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from core.admin_site import AbExamAdminSite
from users.views import (
    HomeView, DashboardView, CustomLoginView, RegisterView,
    ExamsListView, ResultsListView, VocabularyView, FinanceView,
    ChatAIView, ProfileView
)

admin.site.__class__ = AbExamAdminSite

urlpatterns = [
    path('admin/', admin.site.urls),
    path('panel/', include('panel.urls', namespace='panel')),
    path('', HomeView.as_view(), name='home'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('exams-list/', ExamsListView.as_view(), name='exams_list'),
    path('results-list/', ResultsListView.as_view(), name='results_list'),
    path('vocabulary/', VocabularyView.as_view(), name='vocabulary'),
    path('finance/', FinanceView.as_view(), name='finance'),
    path('api/chat/', ChatAIView.as_view(), name='chat_api'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),

    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='users/password_reset.html',
        email_template_name='users/password_reset_email.html',
        subject_template_name='users/password_reset_subject.txt',
        success_url='/password-reset/done/'
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/password_reset_done.html'
    ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='users/password_reset_confirm.html',
        success_url='/password-reset/complete/'
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/password_reset_complete.html'
    ), name='password_reset_complete'),
    path('users/', include('users.urls', namespace='users')),
    path('exams/', include('exams.urls', namespace='exams')),
    path('payments/', include('payments.urls', namespace='payments')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
