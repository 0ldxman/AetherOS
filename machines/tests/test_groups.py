"""Группы и привилегии записи.

Запуск: python manage.py test machines.tests.test_groups
"""
from django.test import TestCase

from machines.access.groups import effective, principal_for
from machines.models import Group, Machine, MachineProfile, SystemType


class GroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = SystemType.objects.create(code="ZED", name="Zed")
        cls.machine = Machine.objects.create(name="Z", hostname="z1", system="ZED")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, login="ivan", name="Ivan", freq=1)

    def test_without_any_group_the_default_one_lets_everyone_cross_bridges_and_transfer(self):
        principal = principal_for(self.profile)
        self.assertEqual(principal.groups, {"users"})
        self.assertTrue(principal.has("bridge") and principal.has("transfer"))
        self.assertFalse(principal.has("backup"))

    def test_the_groups_of_the_system_type_apply_and_the_machine_replaces_or_disables_them(self):
        Group.objects.create(system_type=self.system, name="users", privileges=["transfer"], everyone=True)
        Group.objects.create(system_type=self.system, name="ops", privileges=["clock", "backup"])
        self.profile.groups = ["ops", "ghost"]
        self.assertEqual(principal_for(self.profile).privileges, {"transfer", "clock", "backup"})   # ghost не существует

        Group.objects.create(machine=self.machine, name="ops", privileges=["mount"])
        self.assertEqual(principal_for(self.profile).privileges, {"transfer", "mount"})

        Group.objects.create(machine=self.machine, name="users", disabled=True)
        principal = principal_for(self.profile)
        self.assertEqual((principal.groups, principal.privileges), ({"ops"}, {"mount"}))
        self.assertEqual(set(effective(self.machine)), {"ops"})

    def test_root_has_every_privilege(self):
        self.profile.root = True
        principal = principal_for(self.profile)
        self.assertTrue(principal.has("clock") and principal.has("chown"))
