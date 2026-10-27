from django.urls import path

from terminal import views


app_name = "terminal"

urlpatterns = [
    path("", views.terminal_page, name="index"),
    path("execute/", views.execute, name="execute"),
    path("bridge/close/", views.bridge_close, name="bridge_close"),
    path("tab/", views.tab_focus, name="tab_focus"),
    path("tab/desktop/", views.tab_desktop, name="tab_desktop"),
    path("tab/close/", views.tab_close, name="tab_close"),
]