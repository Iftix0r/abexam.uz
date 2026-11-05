from django.urls import path

from . import views

app_name = 'games'

urlpatterns = [
    path('', views.hub, name='hub'),
    path('finish/', views.finish, name='finish'),
    path('<slug:slug>/', views.play, name='play'),
    path('<slug:slug>/start/', views.start, name='start'),
]
