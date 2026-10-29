"""Корзина: del, rcvr, wipe, место корзины записи.

Запуск: python manage.py test terminal.tests.test_trash
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app, make_file
from machines.models import Machine


@override_settings(FORCE_SCRIPT_NAME=None)
class TrashTests(TestCase):
    """del, rcvr, wipe: корзина записи (/home/ivan/.trash), подтверждение, повреждение при возврате, срок хранения."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt", "/home/docs/x.txt", "/home/docs/y.txt", "/etc/keep.cfg"):
            make_file(cls.main, path, state="")
        make_file(cls.main, "/home/core.sys", state="", system=True)
        make_file(cls.main, "/home/locked.bin", state="> encrypted hunter2")
        make_file(cls.main, "/home/bait.txt", state='> binary utf16\non delete: say "Somebody is watching {name}."')
        make_file(cls.main, "/home/trap.txt", state="> binary utf16\non delete: alert unreachable count=2 gap=100")
        make_file(cls.main, "/home/boom.txt", state="> binary utf16\non delete: drop /home/a.txt")
        make_file(cls.main, "/home/ghost.txt", state='> binary utf16\non restore: say "It remembers you."')
        make_file(cls.main, "/etc", directory=True, system=True)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def post(self, payload):
        response = self.client.post(reverse("terminal:execute"), data=json.dumps(payload), content_type="application/json")
        return json.loads(response.content)

    def run_command(self, text):
        return self.post({"command": text})

    def answer(self, text):
        return self.post({"answer": text})

    def ls(self, path="/home"):
        return self.run_command(f"ls {path}")["output"]

    def test_del_asks_and_a_yes_moves_the_file_to_the_trash(self):
        data = self.run_command("del /home/a.txt")
        self.assertEqual(data["prompt"]["kind"], "confirm")
        self.assertIn("a.txt", self.ls())                                   # пока не подтвердили
        data = self.answer("y")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertNotIn("a.txt", self.ls())
        self.assertIn("a.txt", self.ls("/home/ivan/.trash"))

    def test_anything_but_yes_cancels(self):
        self.run_command("del /home/a.txt")
        self.assertEqual(self.answer("n")["output"], "")
        self.assertIn("a.txt", self.ls())
        self.run_command("del /home/a.txt")
        self.post({"cancel": True})
        self.assertIsNone(self.answer("y")["prompt"])                       # отменённый вопрос не оживает
        self.assertIn("a.txt", self.ls())

    def test_force_skips_the_question_and_several_files_work(self):
        data = self.run_command("del -f /home/a.txt /home/b.txt")
        self.assertIsNone(data["prompt"])
        self.assertEqual(self.ls("/home/ivan/.trash").split(), ["a.txt", "b.txt"])

    def test_a_folder_needs_r_and_keeps_its_structure(self):
        self.assertIn("Is a directory", self.run_command("del -f /home/docs")["output"])
        self.run_command("del -rf /home/docs")
        self.assertNotIn("docs", self.ls())
        self.assertEqual(self.ls("/home/ivan/.trash/docs").split(), ["x.txt", "y.txt"])

    def test_system_files_protected_paths_and_the_trash_cannot_be_deleted(self):
        self.assertIn("Operation not permitted", self.run_command("del -f /home/core.sys")["output"])
        self.assertIn("Operation not permitted", self.run_command("del -rf /home")["output"])        # внутри системный файл и /home защищён
        self.assertIn("Operation not permitted", self.run_command("del -rf /")["output"])
        self.assertIn("Operation not permitted", self.run_command("del -rf /etc")["output"])         # защищён у этой машины
        self.assertIn("core.sys", self.ls())
        self.run_command("del -f /home/a.txt")
        self.assertIn("already in the trash", self.run_command("del -f /home/ivan/.trash/a.txt")["output"])
        self.assertIn("No such file", self.run_command("del -f /home/none")["output"])

    def test_a_live_name_in_the_trash_gets_a_numbered_suffix(self):
        self.run_command("del -f /home/a.txt")
        self.run_command("rcvr /home/ivan/.trash/a.txt /home/b2.txt")
        self.run_command("del -f /home/b.txt")
        self.run_command("rcvr /home/ivan/.trash/b.txt /home/a.txt")
        self.run_command("del -f /home/a.txt")                              # в корзине теперь b.txt под именем a.txt
        self.run_command("del -f /home/b2.txt")
        self.run_command("rcvr /home/ivan/.trash/b2.txt /home/a.txt")
        self.run_command("del -f /home/a.txt")
        self.assertEqual(self.ls("/home/ivan/.trash").split(), ["a.txt", "a.txt.1"])

    def test_rcvr_returns_the_file_damaged_and_longer_stay_means_more_layers(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        data = self.run_command("rcvr /home/ivan/.trash/a.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("a.txt", self.ls())
        self.assertEqual(self.run_command("rpr /home/a.txt")["exit_code"], 0)         # один слой
        self.assertIn("nothing to repair", self.run_command("rpr /home/a.txt")["output"])

        self.run_command("del -f /home/b.txt")
        PlayerFile.objects.filter(path="home/ivan/.trash/b.txt").update(trashed_at=timezone.now() - timedelta(days=3, hours=1))
        self.run_command("rcvr /home/ivan/.trash/b.txt")
        repaired = [self.run_command("rpr /home/b.txt")["exit_code"] for _ in range(5)]
        self.assertEqual(repaired, [0, 0, 0, 0, 1])                                   # 1 + 3 дня = 4 слоя

    def test_the_number_of_damaged_layers_is_capped(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        PlayerFile.objects.filter(path="home/ivan/.trash/a.txt").update(trashed_at=timezone.now() - timedelta(days=6))
        self.run_command("rcvr /home/ivan/.trash/a.txt")
        self.assertEqual([self.run_command("rpr /home/a.txt")["exit_code"] for _ in range(7)], [0] * 5 + [1, 1])

    def test_rcvr_errors_and_a_destination(self):
        self.run_command("del -f /home/a.txt /home/b.txt")
        self.assertIn("not in the trash", self.run_command("rcvr /home/a.txt")["output"])
        self.assertIn("No such file", self.run_command("rcvr /home/ivan/.trash/none")["output"])
        self.run_command("rcvr /home/ivan/.trash/a.txt /home/b.txt")
        self.assertIn("b.txt", self.ls("/home/ivan/.trash"))                                      # путь назначения был занят? нет: b.txt в корзине
        self.run_command("rcvr /home/ivan/.trash/b.txt /home/moved.txt")
        self.assertIn("moved.txt", self.ls())

    def test_a_folder_comes_back_whole_to_its_old_places(self):
        self.run_command("del -rf /home/docs")
        self.assertEqual(self.run_command("rcvr /home/ivan/.trash/docs")["exit_code"], 0)
        self.assertEqual(self.ls("/home/docs").split(), ["x.txt", "y.txt"])
        self.run_command("del -rf /home/docs")
        self.assertIn("a destination can only be given", self.run_command("rcvr /home/ivan/.trash/docs /home/other")["output"])

    def test_expired_files_vanish_for_good_and_the_original_does_not_return(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        PlayerFile.objects.filter(path="home/ivan/.trash/a.txt").update(purge_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.run_command("rcvr /home/ivan/.trash/a.txt")["exit_code"], 1)         # срок вышел: возвращать нечего
        self.assertNotIn("a.txt", self.ls())                                           # машинный файл не вернулся на старое место
        self.assertIn("No such file", self.ls("/home/ivan/.trash"))                               # корзина пуста

    def test_wipe_empties_the_trash_after_a_question(self):
        self.run_command("del -f /home/a.txt /home/b.txt")
        data = self.run_command("wipe")
        self.assertEqual(data["prompt"]["kind"], "confirm")
        self.assertIn("2 files removed", self.answer("y")["output"])
        self.assertIn("empty", self.run_command("wipe")["output"])
        self.assertNotIn("a.txt", self.ls())                                           # и со старых мест не вернулись
        self.assertNotIn("b.txt", self.ls())

    def test_the_purge_command_cleans_every_session(self):
        from datetime import timedelta
        from io import StringIO

        from django.core.management import call_command
        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        PlayerFile.objects.update(purge_at=timezone.now() - timedelta(minutes=1))
        out = StringIO()
        call_command("purge_trash", stdout=out)
        self.assertIn("purged: 1", out.getvalue())
        self.assertFalse(PlayerFile.objects.filter(purge_at__isnull=False, deleted_at__isnull=True).exists())

    def test_on_delete_runs_the_hooks_of_the_top_layer(self):
        data = self.run_command("del -f /home/bait.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("Somebody is watching bait.txt.", data["output"])
        self.assertIn("bait.txt", self.ls("/home/ivan/.trash"))                                    # удалился, как обычно
        self.assertNotIn("Somebody", self.run_command("del -f /home/b.txt")["output"])  # у файла без слоёв хуков нет

    def test_on_delete_can_throw_effects_and_drop_other_files(self):
        data = self.run_command("del -f /home/trap.txt")
        self.assertEqual([e["op"] for e in data["effects"]], ["alert"])
        self.assertEqual(data["effects"][0]["count"], 2)
        self.run_command("del -f /home/boom.txt")
        self.assertNotIn("a.txt", self.ls())                                            # хук убрал и a.txt

    def test_on_restore_sees_the_file_before_the_damage_and_the_damage_still_comes(self):
        self.run_command("del -f /home/ghost.txt")
        data = self.run_command("rcvr /home/ivan/.trash/ghost.txt")
        self.assertIn("It remembers you.", data["output"])
        self.assertEqual(self.run_command("rpr /home/ghost.txt")["exit_code"], 0)       # повреждение осталось
        self.assertEqual(self.run_command("cvt enc utf16 /home/ghost.txt")["exit_code"], 0)       # и слой автора под ним цел


class TrashPlaceTests(TestCase):
    def test_every_record_has_its_own_trash_and_the_place_can_be_overridden(self):
        from machines.models import MachineProfile, Place, Session
        from terminal.engine.context import TerminalContext

        machine = Machine.objects.create(name="Main", hostname="aether-main")
        user = get_user_model().objects.create_user("ivan", password="pw")
        contexts = []
        for login in ("ivan", "admin"):
            profile = MachineProfile.objects.create(machine=machine, user=user, name=login, login=login, freq=1)
            contexts.append(TerminalContext(session=Session.objects.create(user=user, profile=profile)))
        self.assertEqual([c.trash_dir for c in contexts], ["/home/ivan/.trash", "/home/admin/.trash"])

        Place.objects.create(machine=machine, name="trash", path="/trash")
        self.assertEqual([c.trash_dir for c in contexts], ["/trash", "/trash"])
