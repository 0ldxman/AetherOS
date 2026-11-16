"""Часы машины в мире игрока и диски, которые игрок подключает сам.

Запуск: python manage.py test machines.tests.test_clock_mounts
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix
from django.utils import timezone

from filesystem.models import Item, Placement, Volume
from filesystem.testing import make_app
from machines.world import chrono, clock
from terminal.testing import TerminalClient
from machines.models import EntryPolicy, Export, Group, LoginEvent, Machine, MachineMount, MachineProfile, PlayerMount, Share


@override_settings(FORCE_SCRIPT_NAME=None)
class WorldCase(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.core = Machine.objects.create(name="Core", hostname="aether-core")
        make_app(cls.main, label="console", icon="terminal", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.other = get_user_model().objects.create_user("petr", password="pw")
        cls.home = MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)
        MachineProfile.objects.create(machine=cls.main, user=cls.other, name="Petr", login="petr", freq=1)
        cls.reader = MachineProfile.objects.create(machine=cls.core, login="reader", name="Reader", freq=1, password_hash=make_password("right"))
        volume = Volume.objects.create(slug="harbor")
        item = Item.objects.create(slug="manifest", name="manifest.txt", body="cargo")
        Placement.objects.create(volume=volume, name="manifest.txt", kind="item", item=item)
        MachineMount.objects.create(machine=cls.core, volume=volume, mount_path="/srv/harbor")
        Export.objects.create(machine=cls.core, path="/srv/harbor")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        cache.clear()
        self.client.force_login(self.user)

    def allow(self, *privileges):
        Group.objects.create(machine=self.main, name="users", privileges=["bridge", "transfer", *privileges], everyone=True)



class ClockTests(WorldCase):
    def test_date_shows_the_time_of_the_machine_and_tmset_needs_the_privilege(self):
        self.assertEqual(self.run_command("date")["exit_code"], 0)
        self.assertIn("Operation not permitted", self.run_command("tmset +3h")["output"])
        self.assertEqual(clock.offset_of(self.main, self.user), 0)

    def test_tmset_moves_the_clock_of_this_machine_for_this_player_only(self):
        self.allow("clock")
        self.run_command("tmset +3h")
        self.assertAlmostEqual(clock.offset_of(self.main, self.user), 3 * 3600, delta=2)
        self.assertEqual(clock.offset_of(self.main, self.other), 0)
        self.assertEqual(clock.offset_of(self.core, self.user), 0)
        shown = clock.now(self.main, self.user)
        self.assertAlmostEqual((shown - chrono.game_now()).total_seconds(), 3 * 3600, delta=5)
        self.run_command("tmset -1h")
        self.assertAlmostEqual(clock.offset_of(self.main, self.user), 2 * 3600, delta=2)
        self.run_command("tmset reset")
        self.assertEqual(clock.offset_of(self.main, self.user), 0)

    def test_an_exact_time_and_a_bad_text(self):
        self.allow("clock")
        data = self.run_command("tmset 2030-05-17 08:30")
        self.assertIn("2030", data["output"])
        self.assertEqual(clock.now(self.main, self.user).strftime("%Y-%m-%d %H:%M"), "2030-05-17 08:30")
        self.assertEqual(self.run_command("tmset next tuesday")["exit_code"], 2)

    def test_the_clock_of_the_target_machine_decides_the_window_of_entering(self):
        policy = EntryPolicy.objects.create(name="shift", windows="mon: 9:00-9:01")
        MachineProfile.objects.create(machine=self.core, login="shift", name="s", freq=2, entry_policy=policy)
        self.assertIn("Permission denied", self.run_command("rshell shift@aether-core")["output"])
        monday = timezone.make_aware(timezone.datetime(2030, 5, 20, 9, 0, 30))          # 20 мая 2030 понедельник
        clock.set_offset(self.core, self.user, int((monday - chrono.game_now()).total_seconds()))
        self.assertEqual(self.run_command("rshell shift@aether-core")["exit_code"], 0)

    def test_the_journal_keeps_the_time_the_clock_showed_when_it_happened(self):
        from machines.access import entry

        clock.set_offset(self.core, self.user, 5 * 86400)
        event = entry.record(self.reader, self.user, "ok", "aether-main")
        clock.set_offset(self.core, self.user, 0)
        self.assertGreater((event.shown_at - event.at).total_seconds(), 4 * 86400)
        self.assertIn(timezone.localtime(event.shown_at).strftime("%Y-%m-%d"), self.log_text())

    def log_text(self):
        from filesystem.machine_view import MachineView
        from filesystem.content.rawview import build_raw
        from filesystem.testing import make_file

        made = make_file(self.core, "/var/log/auth.log", format="log")
        view = MachineView(self.core, self.user)
        return build_raw(view.get(made.path), view).data.decode()


class ShareTests(WorldCase):
    """share и mnt: игрок раздаёт папку своего дома, другой подключает её к себе в дом по имени и коду."""

    def setUp(self):
        super().setUp()
        from filesystem.machine_view import MachineView
        from machines.access.groups import principal_for

        MachineView(self.main, self.user, principal_for(self.home)).put_text("/home/ivan/drop/note.txt", "note of ivan")

    def remove(self, path):
        self.run_command(f"del {path}")
        return self.answer("y")

    def as_petr(self):
        self.client.logout()
        self.client.force_login(self.other)

    def shared(self, *flags):
        result = self.run_command(" ".join(("share", *flags, "/home/ivan/drop")))
        self.assertEqual(result["exit_code"], 0, result["output"])
        return Share.objects.get(name="ivan-drop").code

    def test_without_the_privilege_nothing_is_shared_or_mounted(self):
        self.assertIn("Operation not permitted", self.run_command("share /home/ivan/drop")["output"])
        self.assertIn("Operation not permitted", self.run_command("mnt --token x aether-main:ivan-drop /home/ivan/n")["output"])
        self.assertFalse(Share.objects.exists())

    def test_a_shared_folder_is_mounted_by_another_player_only_for_him(self):
        self.allow("mount")
        code = self.shared()
        self.assertIn("ivan-drop", self.run_command("share")["output"])
        self.as_petr()
        result = self.run_command(f"mnt --token {code} aether-main:ivan-drop /home/petr/ivan")
        self.assertEqual(result["exit_code"], 0, result["output"])
        self.assertIn("note of ivan", self.run_command("txtx /home/petr/ivan/note.txt")["output"])
        self.assertIn("aether-main:ivan-drop on /home/petr/ivan type share (ro)", self.run_command("mnt")["output"])
        self.assertIn("Read-only file system", self.remove("/home/petr/ivan/note.txt")["output"])
        self.client.logout()
        self.client.force_login(self.user)
        self.assertIn("mounted by: petr", self.run_command("share")["output"])
        self.assertNotIn("note.txt", self.run_command("ls /home/petr/ivan")["output"])          # подключение — только у petr

    def test_drop_lets_put_new_files_and_remove_only_own(self):
        self.allow("mount")
        code = self.shared("-m", "drop")
        self.as_petr()
        self.run_command(f"mnt --token {code} aether-main:ivan-drop /home/petr/ivan")
        self.assertEqual(self.run_command("cp /home/petr/ivan/note.txt /home/petr/ivan/mine.txt")["exit_code"], 0)
        self.assertIn("Operation not permitted", self.remove("/home/petr/ivan/note.txt")["output"])
        self.assertEqual(self.remove("/home/petr/ivan/mine.txt")["exit_code"], 0)

    def test_a_wrong_code_a_point_outside_home_and_an_old_address_mount_nothing(self):
        self.allow("mount")
        code = self.shared()
        self.as_petr()
        self.assertIn("wrong code", self.run_command("mnt --token nope aether-main:ivan-drop /home/petr/ivan")["output"])
        self.assertIn("inside your home", self.run_command(f"mnt --token {code} aether-main:ivan-drop /mnt/ivan")["output"])
        self.assertIn("inside your home", self.run_command(f"mnt --token {code} aether-main:ivan-drop /home/petr")["output"])
        self.assertIn("only shared folders", self.run_command("mnt --token t reader@aether-core:/srv/harbor /home/petr/h")["output"])
        self.assertFalse(PlayerMount.objects.exists())
        self.assertIn("only folders of your home", self.run_command("share /srv")["output"])

    def test_unshare_and_umnt_take_it_away_but_not_a_disk_of_the_machine(self):
        self.allow("mount")
        code = self.shared()
        self.as_petr()
        self.run_command(f"mnt --token {code} aether-main:ivan-drop /home/petr/ivan")
        MachineMount.objects.create(machine=self.main, mode="remote", host=self.core, host_path="/srv/harbor", mount_path="/mnt/own", account=self.reader)
        self.assertIn("Operation not permitted", self.run_command("umnt /mnt/own")["output"])
        self.assertIn("unmounted", self.run_command("umnt /home/petr/ivan")["output"])
        self.run_command(f"mnt --token {code} aether-main:ivan-drop /home/petr/ivan")
        self.client.logout()
        self.client.force_login(self.user)
        self.assertIn("closed", self.run_command("unshare ivan-drop")["output"])
        self.assertFalse(PlayerMount.objects.exists())
