from django.urls import path

from terminal import views


app_name = "terminal"

urlpatterns = [
    path("", views.terminal_page, name="index"),
    path("execute/", views.execute, name="execute"),
]