"""Новая машина с нуля и по образцу, группы по умолчанию при первой своей группе.

Запуск: python manage.py test machines.tests.test_create
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase

from filesystem.models import Placement, Volume, VolumeTemplate
from filesystem.testing import make_file
from machines.access import groups
from machines.models import EntryPolicy, Export, Group, Machine, MachineMount, MachineProfile, Place, SystemType
from machines.world.create import clone_machine, create_machine


class CreateTests(TestCase):
    def test_a_machine_from_a_template_gets_its_own_root_with_the_folders(self):
        template = VolumeTemplate.objects.create(name="unix", folders="etc\nhome\nvar/log")
        machine = create_machine("gw-07", "Gate", "AETHER", root="template", template=template.pk)
        mount = machine.mounts.get(mount_path="/")
        self.assertEqual(sorted(Placement.objects.filter(volume=mount.volume).values_list("name", flat=True)), ["etc", "home", "log", "var"])
        self.assertTrue(machine.hid)

    def test_a_machine_on_an_existing_volume_shares_it(self):
        image = Volume.objects.create(slug="aether-base")
        machine = create_machine("gw-08", "", "AETHER", root="volume", volume=image.pk)
        self.assertEqual(machine.mounts.get().volume, image)
        self.assertEqual(machine.name, "gw-08")
        self.assertEqual(create_machine("gw-09", "", "AETHER").mounts.count(), 0)              # корень появится при первой записи


class CloneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.policy = EntryPolicy.objects.create(name="strict")
        cls.source = Machine.objects.create(name="Core", hostname="aether-core", entry_policy=cls.policy)
        cls.image = Volume.objects.create(slug="aether-base")
        MachineMount.objects.create(machine=cls.source, volume=cls.image, mount_path="/")
        Machine.objects.create(name="Other", hostname="other").mounts.create(volume=cls.image, mount_path="/")
        cls.own = Volume.objects.create(slug="aether-core-own", label="Отличия aether-core")
        MachineMount.objects.create(machine=cls.source, volume=cls.own, mount_path="/", order=1)
        make_file(cls.source, "/home/ops/plan.txt", body="план")                     # ложится в верхний том (свой)
        MachineProfile.objects.create(machine=cls.source, login="ops", name="Ops", freq=14, password_hash=make_password("pw"),
                                      groups=["ops"], key_condition={"all": ["card"]})
        player = get_user_model().objects.create_user("ivan")
        MachineProfile.objects.create(machine=cls.source, login="ivan", name="Ivan", freq=1, user=player)
        Group.objects.create(machine=cls.source, name="ops", privileges=["clock"])
        Place.objects.create(machine=cls.source, name="logs", path="/srv/logs")
        Export.objects.create(machine=cls.source, path="/srv")

    def test_the_copy_has_the_accounts_groups_places_exports_and_policy(self):
        copy = clone_machine(self.source, "aether-edge")
        ops = copy.profiles.get()
        self.assertEqual((ops.login, ops.groups, ops.key_condition, ops.mail), ("ops", ["ops"], {"all": ["card"]}, "ops@aether-edge"))
        self.assertEqual(ops.password_hash, self.source.profiles.get(login="ops").password_hash)
        self.assertEqual(list(copy.groups.values_list("name", "privileges")), [("ops", ["clock"])])
        self.assertIn(("logs", "/srv/logs"), list(copy.places.values_list("name", "path")))
        self.assertEqual(list(copy.exports.values_list("path", flat=True)), ["/srv"])
        self.assertEqual(copy.entry_policy, self.policy)

    def test_a_private_volume_is_copied_and_a_shared_one_stays_shared(self):
        copy = clone_machine(self.source, "aether-edge")
        volumes = {mount.order: mount.volume for mount in copy.mounts.all()}
        self.assertEqual(volumes[0], self.image)
        self.assertNotEqual(volumes[1], self.own)
        self.assertEqual(volumes[1].slug, "aether-edge-own")
        names = set(Placement.objects.filter(volume=volumes[1]).values_list("name", flat=True))
        self.assertIn("plan.txt", names)
        item = Placement.objects.get(volume=volumes[1], name="plan.txt").item
        self.assertEqual(item, Placement.objects.get(volume=self.own, name="plan.txt").item)          # тот же объект


class DefaultGroupsTests(TestCase):
    def test_the_first_own_group_keeps_the_defaults(self):
        machine = Machine.objects.create(name="Core", hostname="aether-core")
        self.assertIn("users", groups.effective(machine))
        groups.make_explicit(machine=machine)
        Group.objects.create(machine=machine, name="night", privileges=["backup"])
        found = groups._load(machine)
        self.assertEqual(set(found), {"users", "night"})
        self.assertIn("bridge", found["users"][0])

    def test_the_type_writes_the_defaults_once(self):
        system, _ = SystemType.objects.get_or_create(code="AETHER", defaults={"name": "Aether"})
        Group.objects.filter(system_type=system).delete()
        self.assertEqual([row["source"] for row in groups.type_table(system)], ["default"])
        groups.make_explicit(system_type=system)
        groups.make_explicit(system_type=system)
        self.assertEqual([(row["name"], row["source"]) for row in groups.type_table(system)], [("users", "system")])
