from django.urls import path
from . import views

urlpatterns = [
    path("", views.HistoryView.as_view()),
]