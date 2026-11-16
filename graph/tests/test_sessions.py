"""Сессии в графе: «Сессия: Найти» (Текущая, Все, Машина; только активные), сущность «Сессия», выход-список по режиму,
ограничение возможности машиной через условие."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from graph import check, nodes as N, offers, runtime, sessions
from graph.models import Graph, Run
from graph.tests.test_runtime import node, wire
from machines.models import Machine, MachineProfile, Session


class SessionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ivan, self.anna = User.objects.create_user("ivan"), User.objects.create_user("anna")
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        self.core = Machine.objects.create(name="Core", hostname="aether-core")
        self.home = MachineProfile.objects.create(machine=self.main, user=self.ivan, login="ivan", name="ivan", freq=1)
        self.guest = MachineProfile.objects.create(machine=self.core, login="guest", name="guest", freq=1)
        now = timezone.now()
        Session.objects.create(user=self.ivan, profile=self.home, seen_at=now - timedelta(hours=1))
        Session.objects.create(user=self.ivan, profile=self.guest, seen_at=now)
        Session.objects.create(user=self.anna, profile=self.guest, seen_at=now - timedelta(hours=2))

    def run_of(self, user=None, host="", login=""):
        return Run(graph=Graph(slug="g"), user=user or self.ivan, ctx={"host": host, "login": login}, state={})

    def test_current_is_where_the_action_happened(self):
        self.assertEqual(sessions.find(self.run_of(host="aether-core", login="guest"), "current"), "ivan/guest@aether-core")
        self.assertEqual(sessions.find(self.run_of(), "current"), "")

    def test_all_of_a_player_and_all_on_a_machine_fresh_first(self):
        run = self.run_of()
        self.assertEqual(sessions.find(run, "all"), ["ivan/guest@aether-core", "ivan/ivan@aether-main"])
        self.assertEqual(sessions.find(run, "all", active=True), ["ivan/guest@aether-core"])
        self.assertEqual(sessions.find(run, "all", player="anna"), ["anna/guest@aether-core"])
        self.assertEqual(sessions.find(run, "machine", machine="aether-core"), ["ivan/guest@aether-core", "anna/guest@aether-core"])
        self.assertEqual(sessions.find(run, "machine", machine="Core", active=True), ["ivan/guest@aether-core"])
        self.assertEqual(sessions.find(run, "machine", machine="nowhere"), [])

    def test_the_entity_reads_the_session(self):
        found = sessions.props("ivan/ivan@aether-main")
        found.pop("seen")                                                                    # дата — test_times
        self.assertEqual(found, {"value": "ivan/ivan@aether-main", "player": "ivan", "machine": "aether-main", "account": "ivan@aether-main",
                                 "active": False, "linked": True, "status": "подключена", "via": "local", "where": ""})
        self.assertEqual(sessions.props("ivan/root@aether-core")["status"], "закрыта")
        self.assertTrue(sessions.props("ivan/guest@aether-core")["active"])
        self.assertFalse(sessions.props("ivan/root@aether-core")["linked"])                   # входа не было — не подключена
        self.assertIsNone(sessions.props("guest@aether-core"))

    def test_the_output_is_a_list_in_all_and_machine(self):
        kind = N.KINDS["session.find"]
        self.assertEqual(N.sock_type(kind, {}, "out", "value"), "session")
        self.assertEqual(N.sock_type(kind, {"mode": "all"}, "out", "value"), "list:session")
        self.assertEqual(N.sock_type(kind, {"mode": "machine"}, "out", "value"), "list:session")
        doc = {"nodes": [node("f", "session.find", mode="all"), node("s", "ent:session")], "wires": [wire("f", "value", "s", "f:session")]}
        self.assertIn("«Сессия» ждёт сессию, а приходит список (сессия)", [p["text"] for p in check.problems(doc, slug="g")])

    def test_an_offer_only_on_one_machine_by_condition(self):
        graph = Graph.objects.create(slug="g", title="g", active=True, doc={"nodes": [
            node("a", "ent:offer", channel="command", command="unlock"), node("cur", "session.find"), node("s", "ent:session"),
            node("eq", "compare", op="eq", b="aether-core"), node("o", "act:offer", offer="g:a"),
        ], "wires": [wire("cur", "value", "s", "f:session"), wire("s", "machine", "eq", "f:a"), wire("eq", "value", "o")]})
        runtime.rebuild_starts(graph)
        here = [view.open for view in offers.visible(self.ivan, "aether-core", "guest", "command")]
        there = [view.open for view in offers.visible(self.ivan, "aether-main", "ivan", "command")]
        self.assertEqual((here, there), ([True], []))

    def test_sessions_of_an_account_and_closing_them(self):
        run = self.run_of(host="aether-core", login="guest")
        self.assertEqual(sessions.find(run, "account", account="guest@aether-core"), ["ivan/guest@aether-core", "anna/guest@aether-core"])
        self.assertEqual(sessions.find(run, "account", account="guest@aether-core", active=True), ["ivan/guest@aether-core"])
        self.assertEqual(sessions.of_account(self.home), ["ivan/ivan@aether-main"])
        self.assertEqual(sessions.close(run, []), 1)                                         # пусто — текущая
        self.assertIsNotNone(Session.objects.get(user=self.ivan, profile=self.guest).kick_at)
        self.assertEqual(sessions.close(run, ["anna/guest@aether-core", "nobody/x@y"]), 1)
        self.assertIsNone(Session.objects.get(user=self.ivan, profile=self.home).kick_at)

    def test_everyone_on_a_machine_is_closed_through_the_machine_output(self):
        from graph.tests.test_data import f

        graph = Graph.objects.create(slug="kick-all", doc={"nodes": [node("m", "manual"), node("e", "ent:machine", machine="aether-core"),
                                                                     node("c", "act:session.close")],
                                                           "wires": [wire("m", "fire", "c"), f("e", "sessions", "c", "session")]})
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(Session.objects.filter(profile=self.guest, kick_at__isnull=False).count(), 2)
        self.assertIsNone(Session.objects.get(profile=self.home).kick_at)

    def test_screen_goes_to_who_is_there_now(self):
        from unittest import mock

        from graph.tests.test_data import f

        sent = []
        with mock.patch("engine.push.send", lambda user, op, **kw: sent.append((user.get_username(), op))):
            graph = Graph.objects.create(slug="scr", doc={"nodes": [node("m", "manual"), node("e", "ent:machine", machine="aether-core"),
                                                                    node("s", "act:screen", variant="notify", who="list", title="ALERT")],
                                                          "wires": [wire("m", "fire", "s"), f("e", "value", "s", "targets")]})
            runtime.start_manual(graph, "m", self.anna)
            self.assertEqual(sent, [("ivan", "notify")])                     # на aether-core сейчас только ivan; anna давно
            sent.clear()
            self.assertEqual(sessions.users_of(["anna", "ivan/guest@aether-core", "guest@aether-core", "nobody"]), [self.anna, self.ivan])
            graph.doc = {"nodes": [node("m", "manual"), node("s", "act:screen", variant="ticker", text="x")], "wires": [wire("m", "fire", "s")]}
            graph.save()
            runtime.start_manual(graph, "m", self.anna)
            self.assertEqual(sent, [("anna", "ticker")])                     # по умолчанию — игроку хода

    def test_screen_is_one_node_and_kick_is_hidden(self):
        self.assertEqual([label for _, label in N.KINDS["act:screen"].fields[0].options],
                         ["Уведомление", "Бегущая строка", "Окна ошибок", "Окно с адресом", "Чёрный экран", "Сцена"])
        self.assertTrue(N.KINDS["do:notify"].hidden and N.KINDS["do:kick"].hidden)
        self.assertEqual(N.KINDS["act:account.change"].label, "Учётка: Изменить")
        self.assertEqual(N.KINDS["ent:server"].label, "Сетевой ресурс")
