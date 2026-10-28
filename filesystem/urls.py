from django.urls import path

from . import views

app_name = "fsview"

urlpatterns = [
    path("raw/", views.raw_page, name="raw"),
    path("text/", views.text_content, name="text"),
    path("edit/", views.edit_page, name="edit"),
    path("raw/content/", views.raw_content, name="content"),
]
