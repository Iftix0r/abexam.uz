from django.urls import path

from . import views

app_name = 'learn'

urlpatterns = [
    path('', views.HubView.as_view(), name='hub'),
    path('goal/', views.GoalView.as_view(), name='goal'),
    path('lesson/<slug:slug>/', views.LessonView.as_view(), name='lesson'),
    path('lesson/<slug:slug>/complete/', views.LessonCompleteView.as_view(), name='lesson_complete'),
    path('write-check/', views.WriteCheckView.as_view(), name='write_check'),
    path('review/', views.ReviewView.as_view(), name='review'),
    path('review/grade/', views.ReviewGradeView.as_view(), name='review_grade'),
    path('tutor/', views.TutorView.as_view(), name='tutor'),
    path('tutor/send/', views.TutorSendView.as_view(), name='tutor_send'),
]
