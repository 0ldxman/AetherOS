from django.urls import path
from desktop import views

urlpatterns = [path("", views.desktop, name="desktop")]