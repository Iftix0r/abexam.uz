from django.urls import path
from django.contrib.auth.views import LogoutView, PasswordChangeView, PasswordChangeDoneView
from django.urls import reverse_lazy

app_name = 'users'

urlpatterns = [
    path('logout/', LogoutView.as_view(next_page='login', http_method_names=['get', 'post']), name='logout'),
    path('password-change/', PasswordChangeView.as_view(
        template_name='users/password_change.html',
        success_url=reverse_lazy('users:password_change_done')
    ), name='password_change'),
    path('password-change/done/', PasswordChangeDoneView.as_view(
        template_name='users/password_change_done.html'
    ), name='password_change_done'),
]
