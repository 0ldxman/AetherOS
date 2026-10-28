"""Типы систем, именованные места, диалект путей и монтирования."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from filesystem.models import Volume
from machines import places
from machines.dialect import to_canonical, to_display
from machines.models import Machine, MachineMount, Place, SystemType


class DialectTests(SimpleTestCase):
    def test_a_windows_path_becomes_canonical_and_back(self):
        self.assertEqual(to_canonical("C:\\Users\\ivan"), "/C:/Users/ivan")
        self.assertEqual(to_canonical("c:/Users"), "/C:/Users")
        self.assertEqual(to_canonical("D:"), "/D:")
        self.assertEqual(to_display("/C:/Users/ivan", "windows"), "C:\\Users\\ivan")
        self.assertEqual(to_display("/C:", "windows"), "C:\\")

    def test_a_unix_path_is_kept(self):
        self.assertEqual(to_canonical("/home//ivan/"), "/home/ivan")
        self.assertEqual(to_display("/home/ivan", "unix"), "/home/ivan")

    def test_substitutions_survive_the_conversion(self):
        self.assertEqual(to_canonical("C:\\Users\\{login}\\Desktop"), "/C:/Users/{login}/Desktop")
        self.assertEqual(to_canonical("{home}/.secrets"), "{home}/.secrets")


class PlaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.aether = SystemType.objects.get(code="AETHER")
        cls.windows = SystemType.objects.create(code="WIN", name="Win", path_style="windows")
        cls.unix_machine = Machine.objects.create(name="A", hostname="a", system="AETHER")
        cls.win_machine = Machine.objects.create(name="W", hostname="w", system="WIN")

    def test_the_aether_system_exists_after_migrations(self):
        self.assertEqual(self.aether.path_style, "unix")
        self.assertEqual(self.unix_machine.path_style, "unix")
        self.assertEqual(self.win_machine.path_style, "windows")

    def test_a_default_place_is_resolved_for_a_login(self):
        self.assertEqual(places.resolve(self.unix_machine, "home", "ivan"), "/home/ivan")
        self.assertEqual(places.resolve(self.unix_machine, "secrets", "ivan"), "/home/ivan/.secrets")
        self.assertEqual(places.resolve(self.unix_machine, "desktop", "admin"), "/home/admin/Desktop")
        self.assertEqual(places.resolve(self.unix_machine, "logs"), "/var/log")

    def test_a_place_with_a_login_needs_the_login(self):
        self.assertIsNone(places.resolve(self.unix_machine, "secrets"))
        self.assertTrue(places.per_login(self.unix_machine, "secrets"))
        self.assertFalse(places.per_login(self.unix_machine, "logs"))

    def test_two_logins_get_two_places(self):
        self.assertNotEqual(places.resolve(self.unix_machine, "secrets", "ivan"), places.resolve(self.unix_machine, "secrets", "admin"))

    def test_a_system_type_overrides_the_default_and_a_machine_overrides_the_system(self):
        Place.objects.create(system_type=self.windows, name="home", path="C:\\Users\\{login}")
        Place.objects.create(system_type=self.windows, name="secrets", path="{home}\\.keys")
        self.assertEqual(places.resolve(self.win_machine, "secrets", "ivan"), "/C:/Users/ivan/.keys")
        Place.objects.create(machine=self.win_machine, name="secrets", path="D:\\Keys\\{login}")
        self.assertEqual(places.resolve(self.win_machine, "secrets", "ivan"), "/D:/Keys/ivan")
        self.assertEqual(places.resolve(self.unix_machine, "secrets", "ivan"), "/home/ivan/.secrets")        # чужие не задеты

    def test_an_own_place_name_is_resolved_and_an_unknown_one_is_none(self):
        Place.objects.create(system_type=self.aether, name="temp-mystery", path="/var/.cache/{login}")
        self.assertEqual(places.resolve(self.unix_machine, "temp-mystery", "ivan"), "/var/.cache/ivan")
        self.assertIsNone(places.resolve(self.unix_machine, "nowhere", "ivan"))

    def test_a_loop_of_substitutions_gives_nothing(self):
        Place.objects.create(system_type=self.aether, name="a", path="{b}/x")
        Place.objects.create(system_type=self.aether, name="b", path="{a}/y")
        self.assertIsNone(places.resolve(self.unix_machine, "a", "ivan"))

    def test_a_place_belongs_to_a_system_or_to_a_machine_not_both(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Place.objects.create(system_type=self.aether, machine=self.unix_machine, name="x", path="/x")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Place.objects.create(name="x", path="/x")
        with self.assertRaises(ValidationError):
            Place(name="x", path="/x").full_clean()

    def test_a_place_name_is_unique_for_its_owner(self):
        Place.objects.create(machine=self.unix_machine, name="logs", path="/srv/logs")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Place.objects.create(machine=self.unix_machine, name="logs", path="/srv/other")


class MountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="A", hostname="a")
        cls.volume = Volume.objects.create(slug="v")
        cls.other = Volume.objects.create(slug="o")

    def mount(self, volume, path, order=0, **extra):
        return MachineMount.objects.create(machine=self.machine, volume=volume, mount_path=path, order=order, **extra)

    def test_paths_are_normalized(self):
        row = self.mount(self.volume, "mnt//harbor/", volume_path="/docs/")
        self.assertEqual((row.mount_path, row.volume_path), ("/mnt/harbor", "docs"))
        self.assertEqual(self.mount(self.other, "c:\\").mount_path, "/C:")

    def test_a_mount_without_a_point_stays_out_of_the_file_system(self):
        self.assertEqual(self.mount(self.volume, "").mount_path, "")
        self.mount(self.other, "")                                                    # без точки порядок не проверяется

    def test_two_volumes_on_one_point_need_different_orders(self):
        self.mount(self.volume, "/", order=0)
        self.mount(self.other, "/", order=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.mount(Volume.objects.create(slug="third"), "/", order=1)

    def test_a_drive_is_only_allowed_at_the_start(self):
        with self.assertRaises(ValidationError):
            MachineMount(machine=self.machine, volume=self.volume, mount_path="/mnt/C:").full_clean()

    def test_the_default_mode_is_local(self):
        self.assertEqual(self.mount(self.volume, "/").mode, "local")
