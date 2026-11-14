"""Лента событий: механики сообщают, что случилось, и из этого собирается журнал игрока."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import events
from engine.models import Event
from filesystem import keystore
from filesystem.machine_view import view_for
from filesystem.testing import key_item
from forum import logic
from forum.models import Section, Space
from machines.access import entry
from machines.models import LoginEvent, Machine, MachineProfile
from team.testing import full_role
from world import state


class EventTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.ivan = get_user_model().objects.create_user("ivan")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.ivan, name="Ivan", login="ivan", freq=1)

    def test_emit_keeps_plain_details_and_never_raises(self):
        found = events.emit("file.read", self.ivan, machine=self.machine, login="ivan", path="/home/ivan/a.txt", extra=object())
        self.assertEqual((found.host, found.login, found.data["path"]), ("aether-main", "ivan", "/home/ivan/a.txt"))
        self.assertIsInstance(found.data["extra"], str)
        self.assertEqual(events.describe(found), "Открыл файл: /home/ivan/a.txt")

    def test_a_new_key_is_an_event_once(self):
        key = key_item("dock")
        view = view_for(self.machine, self.ivan, login="ivan")
        if not keystore.secrets_dir(self.machine, "ivan"):
            self.skipTest("нет папки секретов в тестовой машине")
        keystore.put(view, self.machine, "ivan", key)
        keystore.put(view, self.machine, "ivan", key)
        self.assertEqual(list(Event.objects.filter(name="key.got").values_list("data__slug", flat=True)), ["dock"])

    def test_forum_world_and_login_report_events(self):
        space = Space.objects.create(slug="net", title="Net")
        board = Section.objects.create(space=space, title="General")
        logic.start_topic(board, self.ivan, "Hello", "first", set())
        state.set_flag("core", True, "test", self.ivan)
        entry.record(self.profile, self.ivan, LoginEvent.Kind.OK)
        entry.record(self.profile, self.ivan, LoginEvent.Kind.BAD_PASSWORD)
        self.assertEqual([e.name for e in events.journal(self.ivan)][::-1], ["forum.posted", "world.flag", "machine.login"])


class JournalApiTests(TestCase):
    def test_the_player_card_shows_the_journal(self):
        boss = get_user_model().objects.create_user("boss", is_staff=True, role=full_role())
        ivan = get_user_model().objects.create_user("ivan")
        events.emit("key.got", ivan, machine="aether-main", login="ivan", slug="dock")
        self.client.force_login(boss)
        card = self.client.get(f"/studio/api/players/{ivan.pk}").json()
        self.assertEqual([(row["text"], row["where"]) for row in card["journal"]], [("Получил ключ: dock", "ivan@aether-main")])
