"""Словарь действий движка: каталог, проверки по месту, выполнение по контексту, ссылки, перенос старых записей."""
import importlib

from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import actions as engine
from engine.context import ACCOUNT, SESSION, USER, WORLD, Ctx
from filesystem import keystore
from filesystem.testing import key_item
from machines.models import Machine, MachineProfile
from mail.boxes import Box
from mail.models import Flag
from world.models import WorldEvent, WorldFlag


class CatalogTests(TestCase):
    def test_every_action_is_described_with_its_fields(self):
        names = {row["name"]: row for row in engine.catalog()}
        for name in ("flag", "key", "file", "letter", "alert", "open", "kick", "world_flag", "world_count", "news", "air", "letter_all", "forum", "goto", "bounce"):
            self.assertIn(name, names)
        self.assertEqual(names["key"]["needs"], ACCOUNT)
        self.assertEqual([f["name"] for f in names["world_count"]["fields"]], ["name", "delta"])

    def test_check_knows_what_the_place_provides(self):
        self.assertEqual(engine.check([{"do": "world_flag", "name": "a"}]), [])
        self.assertEqual(engine.check([{"do": "flag", "name": "a"}]), ["действие 1: «Поставить метку игрока» здесь недоступно"])
        self.assertEqual(engine.check([{"do": "flag", "name": "a"}], provides=(WORLD, USER)), [])
        self.assertEqual(engine.check([{"do": "goto", "step": "x"}], provides=(WORLD, USER, ACCOUNT, SESSION)),
                         ["действие 1: «Перейти на шаг» здесь недоступно"])
        self.assertEqual(engine.check([{"do": "goto", "step": "x"}], host=("goto",)), [])
        self.assertEqual(engine.check([{"do": "world_flag", "name": "Bad Name"}])[0][:12], "действие 1: ")
        self.assertEqual(engine.check([{"do": "key", "slug": "nope"}], provides=(ACCOUNT,)), ["действие 1: нет ключа «nope»"])
        self.assertEqual(engine.check([{"do": "open", "url": "/abs"}], provides=(SESSION,))[0][:18], "действие 1: «open»")

    def test_refs_say_what_is_granted(self):
        found = engine.refs([{"do": "key", "slug": "mask"}, {"do": "world_count", "name": "fragments"}, {"do": "news", "title": "x"}])
        self.assertEqual(found, [("key", "mask", "grants"), ("counter", "fragments", "grants")])


class RunTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.ivan = get_user_model().objects.create_user("ivan")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.ivan, name="Ivan", login="ivan", freq=1)

    def box(self):
        return Box.of_profile(self.profile, self.ivan)

    def test_world_actions_run_without_a_player(self):
        engine.run([{"do": "world_flag", "name": "core"}], Ctx(source="test"))
        self.assertTrue(WorldFlag.objects.get(name="core").on)

    def test_player_actions_need_a_player_and_are_logged_otherwise(self):
        engine.run([{"do": "flag", "name": "met"}], Ctx(source="test"))
        self.assertFalse(Flag.objects.exists())
        self.assertTrue(WorldEvent.objects.filter(text__contains="здесь недоступно").exists())
        engine.run([{"do": "flag", "name": "met"}], Ctx(source="test", user=self.ivan))
        self.assertTrue(Flag.objects.filter(user=self.ivan, name="met").exists())

    def test_account_actions_give_keys_and_session_effects_go_to_the_browser(self):
        key_item("dock")
        effects = engine.run([{"do": "key", "slug": "dock"}, {"do": "alert", "message": "intruder", "count": 2}, {"do": "open", "url": "apps/wiki/go/x/"}],
                             Ctx(source="test", user=self.ivan, box=self.box(), session=True))
        self.assertTrue(self.box().view.exists(f"{keystore.secrets_dir(self.machine, 'ivan')}/dock"))
        self.assertEqual([e["op"] for e in effects], ["alert", "open"])

    def test_session_effects_without_a_browser_are_dropped_silently(self):
        effects = engine.run([{"do": "alert", "message": "intruder"}], Ctx(source="test", user=self.ivan, box=self.box()))
        self.assertEqual(effects, [])
        self.assertFalse(WorldEvent.objects.exists())

    def test_host_actions_are_run_by_the_host(self):
        seen = []
        engine.run([{"do": "goto", "step": "next"}], Ctx(host={"goto": lambda action, ctx: seen.append(action["step"])}))
        self.assertEqual(seen, ["next"])

    def test_a_broken_action_does_not_stop_the_rest(self):
        engine.run([{"do": "key", "slug": "nope"}, {"do": "flag", "name": "after"}], Ctx(source="test", user=self.ivan, box=self.box()))
        self.assertTrue(Flag.objects.filter(name="after").exists())
        self.assertTrue(WorldEvent.objects.filter(text__contains="нет ключа").exists())


class LegacyTests(TestCase):
    def test_old_records_are_converted(self):
        world = importlib.import_module("world.migrations.0005_engine_actions")
        self.assertEqual(world.convert([{"do": "flag", "name": "a"}, {"do": "letter", "item": "x"}, {"do": "news", "title": "t"}]),
                         [{"do": "world_flag", "name": "a"}, {"do": "letter_all", "item": "x"}, {"do": "news", "title": "t"}])
        mail = importlib.import_module("mail.migrations.0017_engine_actions")
        self.assertEqual(mail.convert([{"do": "hook", "text": 'alert intruder count=3\nopen "apps/map/?scene=x"\nkick'}, {"do": "flag", "name": "a"}]),
                         [{"do": "alert", "message": "intruder", "count": 3}, {"do": "open", "url": "apps/map/?scene=x"}, {"do": "kick"}, {"do": "flag", "name": "a"}])
