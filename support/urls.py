from django.urls import path

from support import views

app_name = "support"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/tickets/", views.tickets, name="tickets"),
    path("api/tickets/new/", views.create, name="create"),
    path("api/tickets/<int:ticket_id>/", views.ticket, name="ticket"),
    path("api/tickets/<int:ticket_id>/reply/", views.reply, name="reply"),
    path("api/files/<int:file_id>/", views.file, name="file"),
    path("api/pulse/", views.pulse, name="pulse"),
]
