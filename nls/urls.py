from django.urls import path
from .views import TranslateAPIView, TTSAPIView

urlpatterns = [
    path('translate', TranslateAPIView.as_view(), name='translate'),
    path('tts', TTSAPIView.as_view(), name='tts'),
]
