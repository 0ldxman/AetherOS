"""Часы машины в мире игрока и диски, которые игрок подключает сам.

Запуск: python manage.py test machines.test_clock_mounts
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix
from django.utils import timezone

from filesystem.models import Item, Placement, Volume
from filesystem.testing import make_app
from machines import clock
from terminal.testing import TerminalClient
from machines.models import EntryPolicy, Export, Group, LoginEvent, Machine, MachineMount, MachineProfile, PlayerMount


@override_settings(FORCE_SCRIPT_NAME=None)
class WorldCase(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.core = Machine.objects.create(name="Core", hostname="aether-core")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
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
        self.assertAlmostEqual((shown - timezone.localtime()).total_seconds(), 3 * 3600, delta=5)
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
        clock.set_offset(self.core, self.user, int((monday - timezone.now()).total_seconds()))
        self.assertEqual(self.run_command("rshell shift@aether-core")["exit_code"], 0)

    def test_the_journal_keeps_the_time_the_clock_showed_when_it_happened(self):
        from machines import entry

        clock.set_offset(self.core, self.user, 5 * 86400)
        event = entry.record(self.reader, self.user, "ok", "aether-main")
        clock.set_offset(self.core, self.user, 0)
        self.assertGreater((event.shown_at - event.at).total_seconds(), 4 * 86400)
        self.assertIn(timezone.localtime(event.shown_at).strftime("%Y-%m-%d"), self.log_text())

    def log_text(self):
        from filesystem.machine_view import MachineView
        from filesystem.rawview import build_raw
        from filesystem.testing import make_file

        made = make_file(self.core, "/var/log/auth.log", format="log")
        view = MachineView(self.core, self.user)
        return build_raw(view.get(made.path), view).data.decode()


class PlayerMountTests(WorldCase):
    def attach(self, command="mnt reader@aether-core:/srv/harbor /mnt/h", password="right"):
        first = self.run_command(command)
        if first.get("prompt"):
            return self.answer(password)
        return first

    def test_without_the_privilege_the_player_cannot_mount(self):
        self.assertIn("Operation not permitted", self.run_command("mnt reader@aether-core:/srv/harbor /mnt/h")["output"])
        self.assertFalse(PlayerMount.objects.exists())

    def test_a_disk_is_attached_under_the_account_and_listed(self):
        self.allow("mount")
        result = self.attach()
        self.assertEqual(result["exit_code"], 0, result["output"])
        self.assertIn("manifest.txt", self.run_command("ls /mnt/h")["output"])
        self.assertIn("cargo", self.run_command("txtx /mnt/h/manifest.txt")["output"])
        self.assertIn("aether-core:/srv/harbor on /mnt/h type net (reader)", self.run_command("mnt")["output"])
        self.assertEqual(LoginEvent.objects.filter(profile=self.reader, kind="ok").count(), 1)

    def test_a_wrong_password_a_missing_export_and_a_busy_point_attach_nothing(self):
        self.allow("mount")
        self.assertIn("Permission denied", self.attach(password="wrong")["output"])
        self.assertIn("not exported", self.attach("mnt reader@aether-core:/srv /mnt/h")["output"])
        self.assertIn("not exported", self.attach("mnt reader@aether-core:/srv/harbor/nothing /mnt/h")["output"])
        self.assertIn("mount point busy", self.attach("mnt reader@aether-core:/srv/harbor /")["output"])
        self.assertFalse(PlayerMount.objects.exists())

    def test_the_disk_belongs_to_the_player_and_goes_away_when_the_password_changes(self):
        self.allow("mount")
        self.attach()
        self.client.logout()
        self.client.force_login(self.other)
        self.assertNotIn("manifest.txt", self.run_command("ls /mnt/h")["output"])
        MachineProfile.objects.filter(pk=self.reader.pk).update(password_hash=make_password("changed"))
        self.client.logout()
        self.client.force_login(self.user)
        self.assertNotIn("manifest.txt", self.run_command("ls /mnt/h")["output"])

    def test_umnt_detaches_a_disk_of_the_player_but_not_one_of_the_machine(self):
        self.allow("mount")
        self.attach()
        MachineMount.objects.create(machine=self.main, mode="remote", host=self.core, host_path="/srv/harbor", mount_path="/mnt/own", account=self.reader)
        self.assertIn("Operation not permitted", self.run_command("umnt /mnt/own")["output"])
        self.assertIn("unmounted", self.run_command("umnt /mnt/h")["output"])
        self.assertFalse(PlayerMount.objects.exists())
        self.assertEqual(self.run_command("umnt /mnt/nothing")["exit_code"], 1)
        self.assertIn("manifest.txt", self.run_command("ls /mnt/own")["output"])
