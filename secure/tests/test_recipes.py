"""Сборка ключа из частей: рецепт, разделение на части, откуда части выдаются, kjoin в терминале."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem import keystore
from filesystem.models import KEY_FORMAT, Item
from filesystem.testing import make_app
from machines.models import Machine, MachineProfile
from secure import recipes
from terminal.testing import TerminalClient


def key(slug):
    return Item.objects.create(slug=slug, name=slug, format=KEY_FORMAT)


class RecipeTests(TestCase):
    def test_split_and_choose_parts(self):
        door = key("vault-door")
        recipe = recipes.split(door, 3)
        self.assertEqual([item.slug for item in recipes.parts_of(recipe)], ["vault-door.1", "vault-door.2", "vault-door.3"])
        self.assertEqual(Item.objects.get(slug="vault-door.2").name, "vault-door fragment 2/3")
        self.assertEqual(recipes.part_of(Item.objects.get(slug="vault-door.3")), [(door, 3, 3)])
        with self.assertRaises(recipes.RecipeError):
            recipes.split(door, 3)                                   # части уже есть
        with self.assertRaises(recipes.RecipeError):
            recipes.set_parts(door, ["vault-door.1"])                # одной мало
        with self.assertRaises(recipes.RecipeError):
            recipes.set_parts(door, ["vault-door.1", "ghost"])
        key("a"), key("b")
        recipes.set_parts(door, ["b", "a"], consume=True)
        self.assertEqual([item.slug for item in recipes.parts_of(recipes.recipe_of(door))], ["b", "a"])
        self.assertIsNone(recipes.set_parts(door, []))

    def test_sources_name_where_a_part_is_given(self):
        from air.models import Responder, Station

        part = key("shard")
        self.assertEqual(recipes.sources(part), [])
        Responder.objects.create(station=Station.objects.create(name="BOREAS"), freq=Decimal("7.205"), pattern="qrz", actions=[{"do": "key", "slug": "shard"}])
        self.assertEqual(recipes.sources(part), [("ответчик", "BOREAS 7.205")])


@override_settings(FORCE_SCRIPT_NAME=None)
class KjoinTests(TerminalClient, TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(self.main, label="console", icon="terminal", path="/apps/terminal/")
        self.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=self.main, user=self.user, name="Ivan", login="ivan", freq=1)
        self.client.force_login(self.user)
        self.door = key("vault-door")
        recipes.split(self.door, 2)

    def give(self, slug):
        from filesystem.machine_view import view_for

        view = view_for(self.main, self.user, login="ivan")
        keystore.put(view, self.main, "ivan", Item.objects.get(slug=slug))

    def test_fragments_join_into_the_key(self):
        self.run_command("ls")
        self.give("vault-door.1")
        self.assertIn("usage: kjoin", self.run_command("kjoin vault-door.1")["output"])
        self.assertIn("not in /home/.secrets", self.run_command("kjoin vault-door.1 vault-door.2")["output"])
        self.give("vault-door.2")
        key("other")
        self.give("other")
        self.assertIn("fragments do not fit", self.run_command("kjoin vault-door.1 other")["output"])
        done = self.run_command("kjoin /home/.secrets/vault-door.1 vault-door.2")
        self.assertEqual(done["exit_code"], 0)
        self.assertIn("key vault-door assembled in /home/.secrets/vault-door", done["output"])
        self.assertIn("vault-door", self.run_command("ls /home/.secrets")["output"])
        self.assertIn("vault-door.1", self.run_command("ls /home/.secrets")["output"])     # части остались
