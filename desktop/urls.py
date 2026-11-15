from django.urls import path
from desktop import views

urlpatterns = [
    path("", views.desktop, name="desktop"),
    path("wallpaper/<str:code>/", views.wallpaper, name="os_wallpaper"),
    path("moments/", views.moments, name="desktop_moments"),
    path("push/", views.push, name="desktop_push"),
    path("choose/", views.choose, name="desktop_choose"),
    path("file-actions/", views.file_actions, name="desktop_file_actions"),
    path("cards/events/", views.cards_events, name="desktop_cards_events"),
]