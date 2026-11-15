"""Возможности вне почты: скрытая команда терминала, окно с выбором на столе, действие над файлом в его окне."""
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


def make(nodes, wires):
    graph = Graph.objects.create(slug="g", title="g", active=True, doc={"nodes": nodes, "wires": wires})
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
        graph = make([node("m", "manual"), node("o", "act:offer.open", channel="command", command="unlock", text="door {{4471}}", attempts=2,
                                                reply_ok="door open", machine="core"),
                      node("u", "on:offer.used", offer="g:o", repeat="always"), node("c", "do:world_count", name="c")],
                     [wire("m", "fire", "o"), wire("u", "ok", "c")])
        self.assertIn("command not found", self.shell("unlock door 4471").output)
        self.open_for_ivan(graph)
        self.assertIn("invalid arguments", self.shell("unlock window").output)
        wrong = self.shell("unlock door 1111")
        self.assertEqual((wrong.output, wrong.exit_code), ("unlock: access denied", 1))
        self.assertEqual(self.shell("unlock door 4471").output, "door open")
        self.assertEqual(counter(), 1)
        self.assertIn("command not found", self.shell("unlock door 4471").output)          # использована — закрыта
        self.assertEqual(Event.objects.filter(name="offer.used").first().data["command"], "unlock")

    def test_attempts_lock_the_command_and_real_commands_stay(self):
        graph = make([node("m", "manual"), node("o", "act:offer.open", channel="command", command="unlock", text="{{x}}", attempts=1),
                      node("p", "act:offer.open", channel="command", command="ls")],
                     [wire("m", "fire", "o"), wire("o", "next", "p")])
        self.open_for_ivan(graph)
        self.assertEqual(self.shell("unlock y").output, "unlock: locked")
        self.assertIn("command not found", self.shell("unlock x").output)
        self.assertNotIn("access denied", self.shell("ls /").output)

    def test_a_choice_window_waits_for_a_button(self):
        graph = make([node("m", "manual"), node("o", "act:offer.open", channel="choice", title="Uplink", message="Accept the transfer?", buttons=["Yes", "No"]),
                      node("u", "on:offer.used", offer="g:o", word="Yes", repeat="always"), node("c", "do:world_count", name="c")],
                     [wire("m", "fire", "o"), wire("u", "ok", "c")])
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

    def test_an_action_on_a_file_window(self):
        made = make_file(self.core, "/home/ivan/sample.bin", body="x")
        Item.objects.filter(pk=made.item.pk).update(slug="sample")
        make_file(self.core, "/home/ivan/other.txt", body="y")
        graph = make([node("m", "manual"), node("o", "act:offer.open", channel="file", title="Send to lab", item="sample", caption="Lab uplink ready"),
                      node("u", "on:offer.used", offer="g:o", repeat="always"), node("c", "do:world_count", name="c")],
                     [wire("m", "fire", "o"), wire("u", "ok", "c")])
        self.open_for_ivan(graph)
        self.login()
        self.assertEqual(self.client.get("/desktop/file-actions/", {"path": "/home/ivan/other.txt"}).json()["actions"], [])
        answer = self.client.get("/desktop/file-actions/", {"path": "/home/ivan/sample.bin"}).json()
        self.assertEqual(answer["actions"], [{"id": "g:o", "title": "Send to lab"}])
        self.assertEqual(answer["caption"], "Lab uplink ready")
        self.client.post("/desktop/file-actions/", json.dumps({"offer": "g:o", "path": "/home/ivan/sample.bin"}), content_type="application/json")
        self.assertEqual(counter(), 1)
        self.assertEqual(Event.objects.get(name="offer.used").data["placement"], "ivan@core:/home/ivan/sample.bin")
        self.assertTrue(graph)
