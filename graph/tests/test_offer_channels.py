"""Возможности вне почты: скрытая команда терминала, окно с выбором на столе, кнопка у файла в его окне."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone

from engine.models import Event
from filesystem.models import Item
from filesystem.testing import make_file
from graph import runtime
from graph.models import Graph
from graph.tests.test_runtime import counter, node, wire
from machines.current import SESSION_KEY
from machines.models import Machine, MachineProfile, Session
from terminal.engine.executor import TerminalExecutor


def make(entity, nodes=(), wires=()):
    """Сущность «o» (entity — её данные), «Открыть» её по «m» и ещё ноды."""
    doc = {"nodes": [node("m", "manual"), node("o", "ent:offer", **entity), node("op", "act:offer.open", offer="g:o"), *nodes],
           "wires": [wire("m", "fire", "op"), *wires]}
    graph = Graph.objects.create(slug="g", title="g", active=True, doc=doc)
    runtime.rebuild_starts(graph)
    return graph


@override_settings(FORCE_SCRIPT_NAME=None)
class ChannelTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.ivan = get_user_model().objects.create_user("ivan", password="pw")
        self.profile = MachineProfile.objects.create(machine=self.core, user=self.ivan, name="Ivan", login="ivan", freq=1)
        self.session = Session.objects.create(user=self.ivan, profile=self.profile, seen_at=timezone.now())

    def open_for_ivan(self, graph):
        runtime.start(graph, "m", "fire", self.ivan, {"host": "core", "login": "ivan"}, repeat="always")

    def shell(self, source):
        return TerminalExecutor().execute(session=self.session, source=source)[0]

    def login(self):
        self.client.force_login(self.ivan)
        session = self.client.session
        session[SESSION_KEY] = self.session.pk
        session.save()

    def test_a_hidden_command_checks_its_arguments(self):
        graph = make({"channel": "command", "command": "unlock", "text": "[[door|gate]] {{4471}}", "reply_ok": "{args}: open", "machine": "core"},
                     [node("u", "on:offer.used", repeat="always"), node("c", "do:world_count", name="c"), node("w", "do:world_count", name="w")],
                     [wire("o", "offer", "u", "f:offer"), wire("u", "ok", "c"), wire("u", "wrong", "w")])
        self.assertIn("command not found", self.shell("unlock door 4471").output)
        self.open_for_ivan(graph)
        self.assertIn("invalid arguments", self.shell("unlock window").output)
        wrong = self.shell("unlock door 1111")
        self.assertEqual((wrong.output, wrong.exit_code), ("unlock: access denied", 1))
        self.assertEqual(self.shell("unlock door 1112").exit_code, 1)                    # попыток не считаем: это счётчик сценария
        self.assertEqual(self.shell("unlock gate 4471").output, "gate 4471: open")
        self.assertEqual((counter(), counter("w")), (1, 2))
        self.assertIn("command not found", self.shell("unlock door 4471").output)          # использована — закрыта
        event = Event.objects.filter(name="offer.used").first()
        self.assertEqual((event.data["command"], event.data["forks"]), ("unlock", {"1": "gate"}))

    def test_real_commands_stay(self):
        graph = make({"channel": "command", "command": "ls"})
        self.open_for_ivan(graph)
        self.assertNotIn("access denied", self.shell("ls /").output)

    def test_a_choice_window_goes_by_the_pressed_button(self):
        graph = make({"channel": "choice", "title": "Uplink", "message": "Accept the transfer?", "buttons": ["Yes", "No"]},
                     [node("u", "on:offer.used", repeat="always"), node("c", "do:world_count", name="c")],
                     [wire("o", "offer", "u", "f:offer"), wire("u", "b1", "c")])
        self.login()
        self.assertEqual(self.client.get("/desktop/push/").json()["offers"], [])
        self.open_for_ivan(graph)
        offers = self.client.get("/desktop/push/").json()["offers"]
        self.assertEqual(offers, [{"id": "g:o", "title": "Uplink", "text": "Accept the transfer?", "buttons": ["Yes", "No"]}])
        bad = self.client.post("/desktop/choose/", json.dumps({"offer": "g:o", "button": "Maybe"}), content_type="application/json")
        self.assertEqual(bad.status_code, 404)
        self.client.post("/desktop/choose/", json.dumps({"offer": "g:o", "button": "Yes"}), content_type="application/json")
        self.assertEqual(counter(), 1)
        self.assertEqual(self.client.get("/desktop/push/").json()["offers"], [])

    def test_a_button_on_a_file_window(self):
        made = make_file(self.core, "/home/ivan/sample.bin", body="x")
        Item.objects.filter(pk=made.item.pk).update(slug="sample")
        make_file(self.core, "/home/ivan/other.txt", body="y")
        graph = make({"channel": "file", "title": "Send to lab", "item": "sample", "caption": "Lab uplink ready"},
                     [node("u", "on:offer.used", repeat="always"), node("c", "do:world_count", name="c")],
                     [wire("o", "offer", "u", "f:offer"), wire("u", "ok", "c")])
        self.open_for_ivan(graph)
        self.login()
        self.assertEqual(self.client.get("/desktop/file-actions/", {"path": "/home/ivan/other.txt"}).json()["actions"], [])
        answer = self.client.get("/desktop/file-actions/", {"path": "/home/ivan/sample.bin"}).json()
        self.assertEqual(answer["actions"], [{"id": "g:o", "title": "Send to lab"}])
        self.assertEqual(answer["caption"], "Lab uplink ready")
        self.client.post("/desktop/file-actions/", json.dumps({"offer": "g:o", "path": "/home/ivan/sample.bin"}), content_type="application/json")
        self.assertEqual(counter(), 1)
        self.assertEqual(Event.objects.get(name="offer.used").data["placement"], "ivan@core:/home/ivan/sample.bin")
