from django.urls import re_path

from team.consumers import RoomConsumer

websocket_urlpatterns = [
    re_path(r"(?:.*/)?studio/ws/(?P<room>.+)$", RoomConsumer.as_asgi()),      # и под префиксом прокси
]
