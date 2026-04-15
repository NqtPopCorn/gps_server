from django.urls import path
from accounts.views import RegisterView, LoginView, ProfileView

urlpatterns = [
    path('register', RegisterView.as_view(), name='auth-register'),
    path('login', LoginView.as_view(), name='auth-login'),
    path('profile', ProfileView.as_view(), name='auth-profile'),
]
