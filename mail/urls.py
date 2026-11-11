from django.urls import path

from mail import views

app_name = "mail"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("api/messages/", views.message_list, name="messages"),
    path("api/pulse/", views.pulse, name="pulse"),
    path("api/message/", views.message_detail, name="message"),
    path("api/message/unread/", views.message_unread, name="unread"),
    path("api/message/trash/", views.message_trash, name="trash"),
    path("api/compose/", views.compose_options, name="compose"),
    path("api/send/", views.send_letter, name="send"),
    path("api/files/", views.files, name="files"),
    path("api/attachment/", views.attachment, name="attachment"),
]
