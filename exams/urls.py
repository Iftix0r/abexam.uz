from django.urls import path
from .views import ExamDetailView, ExamUnlockView, TakeExamView, SubmitExamView, ResultDetailView, SpeakingEvalView, DemoAnswersView, ExamAutosaveView

app_name = 'exams'

urlpatterns = [
    path('<int:pk>/', ExamDetailView.as_view(), name='exam_detail'),
    path('<int:pk>/unlock/', ExamUnlockView.as_view(), name='unlock_exam'),
    path('<int:pk>/take/', TakeExamView.as_view(), name='take_exam'),
    path('<int:pk>/demo-answers/', DemoAnswersView.as_view(), name='demo_answers'),
    path('<int:pk>/autosave/', ExamAutosaveView.as_view(), name='autosave'),
    path('<int:pk>/submit/', SubmitExamView.as_view(), name='submit_exam'),
    path('result/<int:pk>/', ResultDetailView.as_view(), name='result_detail'),
    path('speaking/evaluate/', SpeakingEvalView.as_view(), name='speaking_eval'),
]
