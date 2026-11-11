from django.urls import path

from news import views

app_name = "news"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/posts/", views.posts, name="posts"),
    path("api/read/", views.read, name="read"),
    path("api/pulse/", views.pulse, name="pulse"),
]
