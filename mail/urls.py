from django.urls import path

from . import views

app_name = "mail"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("api/messages/", views.message_list, name="messages"),
    path("api/messages/<int:pk>/", views.message_detail, name="message"),
    path("api/messages/<int:pk>/unread/", views.message_unread, name="unread"),
    path("api/attachments/<int:pk>/save/", views.attachment_save, name="save"),
]
