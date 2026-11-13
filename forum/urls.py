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
    path("api/files/", views.files, name="files"),
    path("api/attachment/save/", views.save_attachment, name="save_attachment"),
    path("api/section/new/", views.new_section, name="new_section"),
    path("api/section/archive/", views.archive_section, name="archive_section"),
    path("api/post/hide/", views.hide_post, name="hide_post"),
    path("api/post/restore/", views.restore_post, name="restore_post"),
    path("api/topic/flags/", views.topic_flags, name="topic_flags"),
]
