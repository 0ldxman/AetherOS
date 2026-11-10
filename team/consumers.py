"""WebSocket комнаты совместной правки (team.collab): протокол y-websocket поверх Django Channels."""
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from team import collab


class RoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        self.room_name = self.scope["url_route"]["kwargs"]["room"].strip("/")
        allowed, self.writer = await sync_to_async(self._rights)()
        if not allowed:
            await self.close(code=4403)
            return
        self.room = await collab.room(self.room_name)
        await self.accept()
        await self.room.join(self)

    def _rights(self):
        """(можно ли войти, можно ли править): роль читается из базы, поэтому не в цикле событий."""
        user = self.user
        if user is None or not user.is_authenticated or not user.is_staff or not collab.can_join(user, self.room_name):
            return False, False
        return True, collab.can_write(user, self.room_name)

    async def disconnect(self, code):
        found = getattr(self, "room", None)
        if found is not None:
            await found.leave(self)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None and getattr(self, "room", None) is not None:
            await self.room.receive(self, bytes_data)

    async def send_bytes(self, data):
        await self.send(bytes_data=bytes(data))
