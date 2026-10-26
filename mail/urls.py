from django.urls import path

from . import views

app_name = "mail"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("api/messages/", views.message_list, name="messages"),
    path("api/pulse/", views.pulse, name="pulse"),
    path("api/messages/<int:pk>/", views.message_detail, name="message"),
    path("api/messages/<int:pk>/unread/", views.message_unread, name="unread"),
    path("api/attachments/<int:pk>/open/", views.attachment_open, name="open"),
    path("api/attachments/<int:pk>/save/", views.attachment_save, name="save"),
    path("api/tasks/", views.task_list, name="tasks"),
    path("api/tasks/<int:pk>/send/", views.task_send, name="send"),
]
