"""Совместная правка: комната Yjs по сущности, синхронизация двух авторов, права, присутствие, черновик в базе.

Запуск: python manage.py test team
"""
from asgiref.sync import async_to_sync, sync_to_async
from channels.auth import AuthMiddlewareStack
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from pycrdt import Doc, Map, Text, YMessageType, YSyncMessageType, create_sync_message, create_update_message, handle_sync_message

from team import collab
from team.models import Draft, Role
from team.routing import websocket_urlpatterns

application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))


class Client:
    """Клиент y-websocket в тесте: свой документ pycrdt, приём и отправка сообщений."""

    def __init__(self, cookie, room):
        self.doc = Doc()
        self.socket = WebsocketCommunicator(application, f"/studio/ws/{room}", headers=[(b"cookie", cookie.encode())])

    async def open(self):
        connected, code = await self.socket.connect()
        if connected:
            await self.socket.send_to(bytes_data=create_sync_message(self.doc))
        return connected, code

    async def drain(self):
        """Принять всё, что пришло, и ответить на шаги синхронизации."""
        while not await self.socket.receive_nothing(timeout=0.2):
            data = await self.socket.receive_from()
            data = data if isinstance(data, bytes) else data.encode()
            if data[0] == YMessageType.SYNC:
                reply = handle_sync_message(data[1:], self.doc)
                if reply is not None:
                    await self.socket.send_to(bytes_data=reply)

    async def edit(self, change):
        before = self.doc.get_state()
        change(self.doc)
        await self.socket.send_to(bytes_data=create_update_message(self.doc.get_update(before)))


class CollabTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        # TransactionTestCase очищает таблицы: роли из миграции может не быть
        role = Role.objects.filter(name="Полный доступ").first() or Role.objects.create(name="Полный доступ", rights={"machines": "edit"})
        self.anna = User.objects.create_user("anna", password="pw", is_staff=True, role=role)
        self.olga = User.objects.create_user("olga", password="pw", is_staff=True)            # без роли: только смотрит
        self.player = User.objects.create_user("ivan", password="pw")

    def cookie(self, user):
        from django.test import Client as HttpClient

        browser = HttpClient()                       # у каждого автора своя сессия: вход другого не сбрасывает её
        browser.force_login(user)
        return f"sessionid={browser.cookies['sessionid'].value}"

    def test_two_authors_share_the_document_and_the_draft_is_kept_while_unsaved(self):
        async def run():
            anna = Client(await sync_to_async(self.cookie)(self.anna), "machines/1")
            other = Client(await sync_to_async(self.cookie)(self.anna), "machines/1")
            self.assertTrue((await anna.open())[0])
            self.assertTrue((await other.open())[0])
            await anna.drain(); await other.drain()

            def write(doc):
                doc.get("name", type=Text).insert(0, "Главная")
                meta = doc.get("_meta", type=Map)
                meta["main"] = {"dirty": True, "editors": ["anna"]}
                meta["account:4"] = {"dirty": False, "editors": []}
            await anna.edit(write)
            await other.drain()
            self.assertEqual(str(other.doc.get("name", type=Text)), "Главная")
            self.assertEqual(collab.live(), {"machines/1": ["anna"]})
            await anna.socket.disconnect(); await other.socket.disconnect()

        async_to_sync(run)()
        draft = Draft.objects.get(room="machines/1")
        self.assertTrue(draft.dirty)
        self.assertEqual(draft.editors, ["anna"])
        restored = Doc()
        restored.apply_update(bytes(draft.state))
        self.assertEqual(str(restored.get("name", type=Text)), "Главная")
        self.assertEqual(collab.live(), {})

    def test_a_clean_draft_is_dropped_when_everyone_leaves(self):
        async def run():
            anna = Client(await sync_to_async(self.cookie)(self.anna), "machines/2")
            await anna.open(); await anna.drain()
            await anna.edit(lambda doc: doc.get("name", type=Text).insert(0, "x"))
            await anna.socket.disconnect()
        async_to_sync(run)()
        self.assertFalse(Draft.objects.filter(room="machines/2").exists())

    def test_a_viewer_joins_but_cannot_change_and_a_player_is_refused(self):
        async def run():
            olga = Client(await sync_to_async(self.cookie)(self.olga), "machines/3")
            anna = Client(await sync_to_async(self.cookie)(self.anna), "machines/3")
            self.assertTrue((await olga.open())[0])
            await anna.open(); await olga.drain(); await anna.drain()
            await olga.edit(lambda doc: doc.get("name", type=Text).insert(0, "чужое"))
            await anna.drain()
            self.assertEqual(str(anna.doc.get("name", type=Text)), "")
            await olga.socket.disconnect(); await anna.socket.disconnect()
            player = Client(await sync_to_async(self.cookie)(self.player), "machines/3")
            connected, code = await player.open()
            self.assertFalse(connected)
        async_to_sync(run)()
