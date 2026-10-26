from django.urls import path

from . import views

app_name = "fsview"

urlpatterns = [
    path("raw/", views.raw_page, name="raw"),
    path("raw/content/", views.raw_content, name="content"),
]
