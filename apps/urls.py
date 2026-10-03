from django.urls import path
from . import views

urlpatterns = [
    path("sessions/", views.sessions, name="sessions"),
    path("sessions/<str:sid>/", views.session_inspector, name="session_inspector"),
]