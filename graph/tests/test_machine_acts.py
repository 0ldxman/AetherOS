"""Машина и учётки в графе: «Машина: Изменить», сущность «Учётка», «Изменить учётку», «Доступ к учётке», «Создать или удалить учётку»."""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.test import TestCase

from engine import values
from graph import check, runtime
from graph.models import Run
from graph.runtime import Doc, value_of
from graph.tests.test_runtime import make, node, wire
from machines.models import AccountBlock, Machine, MachineProfile, MachineProfileToken, SystemType


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class MachineActTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core")
        SystemType.objects.get_or_create(code="LINUX", defaults={"name": "Linux"})
        self.ops = MachineProfile.objects.create(machine=self.core, login="ops", name="Ops", endpoints=["22.000"], groups=["staff"])

    def act(self, kind, **data):
        graph = make([node("m", "manual"), node("a", kind, **data), node("ok", "act:tag", variant="on", name="ok"),
                      node("bad", "act:tag", variant="on", name="bad")],
                     [wire("m", "fire", "a"), wire("a", "next", "ok"), wire("a", "fail", "bad")], slug=f"g{Run.objects.count()}")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        return (Run.objects.order_by("-pk").first().state.get("vals") or {}).get("a", {})

    def test_change_machine(self):
        for variant, value in (("name", "Core-2"), ("system", "LINUX"), ("time_zone", "Asia/Tokyo"), ("host_key", ""), ("note", "welcome"),
                               ("booted", "2031-03-02 14:05")):
            self.act("act:machine.change", variant=variant, machine="core", **{variant: value})
        self.assertFalse(values.on("world", 0, "bad"))
        self.core.refresh_from_db()
        self.assertEqual((self.core.name, self.core.system, self.core.time_zone, self.core.note, self.core.booted_at.year),
                         ("Core-2", "LINUX", "Asia/Tokyo", "welcome", 2031))
        self.assertTrue(self.core.host_key.startswith("SHA256:"))
        self.act("act:machine.change", variant="system", machine="core", system="NOPE")            # нет такой ОС — «Не вышло»
        self.assertTrue(values.on("world", 0, "bad"))

    def test_account_entity(self):
        doc = Doc({"nodes": [node("u", "ent:account", account="ops@core")], "wires": []})
        get = lambda out: value_of(type("R", (), {"user": self.ivan, "state": {}, "ctx": {}})(), doc, "u", out)      # noqa: E731
        self.assertEqual([get(o) for o in ("value", "machine", "login", "groups", "endpoints", "blocked")],
                         ["ops@core", "core", "ops", ["staff"], ["22.000"], False])

    def test_change_account(self):
        self.act("act:account.change", variant="password", account="ops@core", password="s3cret")
        self.act("act:account.change", variant="points_add", account="ops@core", points="2222")
        self.act("act:account.change", variant="groups_remove", account="ops@core", groups="staff")
        self.act("act:account.change", variant="keys", account="ops@core", keys="cardkey")
        token = self.act("act:account.change", variant="token_add", account="ops@core", uses=1)["token"]
        self.ops.refresh_from_db()
        self.assertTrue(check_password("s3cret", self.ops.password_hash))
        self.assertEqual((self.ops.endpoints, self.ops.groups, bool(self.ops.key_condition)), (["22.000", "2222.000"], [], True))
        self.assertTrue(MachineProfileToken.objects.filter(profile=self.ops, token=token, max_usage=1).exists())
        self.act("act:account.change", variant="token_remove", account="ops@core")
        self.assertFalse(MachineProfileToken.objects.filter(profile=self.ops).exists())

    def test_access_and_manage(self):
        self.act("act:account.access", variant="block", account="ops@core", minutes=5, text="locked")
        self.assertTrue(AccountBlock.objects.filter(profile=self.ops, user=self.ivan).exists())
        self.act("act:account.access", variant="unblock", account="ops@core")
        self.assertFalse(AccountBlock.objects.exists())
        made = self.act("act:account.manage", variant="create", machine="core", login="ghost", points="14.230", password="x")
        self.assertEqual(made["account"], "ghost@core")
        self.assertEqual(MachineProfile.objects.get(login="ghost").endpoints, ["14.230"])
        self.act("act:account.manage", variant="delete", account="ghost@core")
        self.assertFalse(MachineProfile.objects.filter(login="ghost").exists())

    def test_an_account_for_the_player_of_the_turn(self):
        made = self.act("act:account.manage", variant="create", owner="player", machine="core", login="lab-{player}")
        self.assertEqual(made["account"], "lab-ivan@core")
        self.assertEqual(MachineProfile.objects.get(login="lab-ivan").user, self.ivan)
        again = self.act("act:account.manage", variant="create", owner="player", machine="core", login="lab2-{player}")
        self.assertEqual(again, {"account": ""})                                             # одна на машину: «Не вышло»
        self.act("act:account.manage", variant="delete", account="lab-ivan@core")
        self.assertTrue(MachineProfile.objects.filter(login="lab-ivan").exists())            # учётку игрока не удалить
