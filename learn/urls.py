from django.urls import path

from . import views

app_name = 'learn'

urlpatterns = [
    path('', views.HubView.as_view(), name='hub'),
    path('goal/', views.GoalView.as_view(), name='goal'),
    path('lesson/<slug:slug>/', views.LessonView.as_view(), name='lesson'),
    path('lesson/<slug:slug>/complete/', views.LessonCompleteView.as_view(), name='lesson_complete'),
    path('lesson/<slug:slug>/draft/', views.LessonDraftView.as_view(), name='lesson_draft'),
    path('app/', views.AppView.as_view(), name='app'),
    path('app/download/', views.app_download, name='app_download'),
    path('write-check/', views.WriteCheckView.as_view(), name='write_check'),
    path('tts/', views.TtsView.as_view(), name='tts'),
    path('transcribe/', views.TranscribeView.as_view(), name='transcribe'),
    path('review/', views.ReviewView.as_view(), name='review'),
    path('review/grade/', views.ReviewGradeView.as_view(), name='review_grade'),
    path('tutor/', views.TutorView.as_view(), name='tutor'),
    path('tutor/send/', views.TutorSendView.as_view(), name='tutor_send'),
    path('placement/', views.PlacementView.as_view(), name='placement'),
    path('placement/save/', views.PlacementSaveView.as_view(), name='placement_save'),
    path('grammar/', views.GrammarView.as_view(), name='grammar'),
    path('practice/', views.PracticeView.as_view(), name='practice'),
    path('practice/complete/', views.PracticeCompleteView.as_view(), name='practice_complete'),
    path('stories/', views.StoriesView.as_view(), name='stories'),
    path('stories/<slug:slug>/', views.StoryView.as_view(), name='story'),
    path('stories/<slug:slug>/complete/', views.StoryCompleteView.as_view(), name='story_complete'),
    path('leaderboard/', views.LeaderboardView.as_view(), name='leaderboard'),
]
