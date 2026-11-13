from django.urls import path

from forum import views

app_name = "forum"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/spaces/", views.spaces, name="spaces"),
    path("api/space/<slug:slug>/", views.space, name="space"),
    path("api/section/<int:pk>/", views.section, name="section"),
    path("api/topic/<int:pk>/", views.topic, name="topic"),
    path("api/topic/new/", views.new_topic, name="new_topic"),
    path("api/post/new/", views.new_post, name="new_post"),
]
