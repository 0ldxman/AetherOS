"""«Сессия: Вход и выход» и «Журнал: Записать»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check
from graph.models import Entry
from graph.runtime import start_control
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile, Session
from machines.network import bridge


def count(name):
    return values.get(values.COUNT, "world", 0, name)


class SessionEventTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("ivan")
        self.machine = Machine.objects.create(name="Core", hostname="core")
        self.profile = MachineProfile.objects.create(machine=self.machine, login="root")
        self.graph = make([node("in", "on:session", login="ro*"), node("out", "on:session", login="ro*"), node("a", "do:world_count", name="entered"), node("b", "do:world_count", name="left")],
                          [wire("in", "in", "a"), wire("out", "out", "b")], slug="sess")           # старт игрока срабатывает один раз за игру — по одной ноде на выход

    def test_graph_is_valid(self):
        self.assertEqual([p for p in check.problems(self.graph.doc) if p["level"] == "error"], [])

    def test_login_and_logout_events_start_the_matching_outputs(self):
        emit("machine.login", self.user, machine=self.machine, login="root")
        self.assertEqual((count("entered"), count("left")), (1, 0))
        emit("machine.logout", self.user, machine=self.machine, login="root")
        self.assertEqual((count("entered"), count("left")), (1, 1))
        emit("machine.logout", self.user, machine=self.machine, login="guest")           # другая учётка: фильтр «ro*» (и старт уже был)
        self.assertEqual(count("left"), 1)

    def test_closing_a_session_in_the_bridge_announces_the_logout(self):
        session = Session.objects.create(user=self.user, profile=self.profile)
        rows = {str(session.pk): Session.objects.select_related("profile__machine").get(pk=session.pk)}
        request = type("Req", (), {"user": self.user})()
        bridge._save(request, {"nodes": {}, "_was": {str(session.pk)}, "_rows": rows, "desktop": "1", "terminal": "1"})
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())
        self.assertEqual(count("left"), 1)


class JournalNodeTests(TestCase):
    def test_writes_an_author_entry_with_the_text(self):
        graph = make([node("go", "manual", name="Go"), node("j", "journal", text="дошли до сейфа")], [wire("go", "fire", "j")], slug="note")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        start_control(graph, "go")
        entry = Entry.objects.get(graph=graph, kind="note")
        self.assertEqual((entry.text, entry.node), ("дошли до сейфа", "j"))


class SignalJournalTests(TestCase):
    def test_a_sent_signal_is_written_to_the_journal(self):
        graph = make([node("go", "manual", name="Go"), node("s", "send_signal", name="bunker-open", scope="world")], [wire("go", "fire", "s")], slug="sig")
        start_control(graph, "go")
        entry = Entry.objects.get(graph=graph, kind="signal")
        self.assertEqual((entry.text, entry.node), ("Сигнал «bunker-open»: Мир", "s"))


class NotifyNodeTests(TestCase):
    def test_authors_get_a_notification_with_a_link_to_the_journal(self):
        from team.models import Notification

        users = get_user_model().objects
        boss, other, player = users.create_user("boss", is_staff=True), users.create_user("other", is_staff=True), users.create_user("ivan")
        graph = make([node("go", "manual", name="Go"), node("n", "notify", text="{player} дошёл до сейфа"), node("n2", "notify", text="только boss", to=["Boss"])],
                     [wire("go", "fire", "n"), wire("n", "next", "n2")], slug="ntf")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        start_control(graph, "go", user=player)
        self.assertEqual(sorted(Notification.objects.filter(user=boss).values_list("text", flat=True)), ["«ntf»: ivan дошёл до сейфа", "«ntf»: только boss"])
        self.assertEqual(list(Notification.objects.filter(user=other).values_list("text", flat=True)), ["«ntf»: ivan дошёл до сейфа"])
        self.assertFalse(Notification.objects.filter(user=player).exists())
        self.assertEqual(Notification.objects.filter(user=boss).first().link, f"#/world/scenario/{graph.pk}/journal")
