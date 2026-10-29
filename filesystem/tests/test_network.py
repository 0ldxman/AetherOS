"""Сетевые диски: хост, путь, учётка, экспорт, цепочки.

Запуск: python manage.py test filesystem.tests.test_network
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem.machine_view import MachineView, ReadOnly
from filesystem.models import Item, Placement, Volume
from filesystem import rights
from machines.access.groups import principal_for
from machines.models import Export, Machine, MachineMount, MachineProfile


def item(slug, body="", **fields):
    return Item.objects.create(slug=slug, name=slug, body=body, **fields)


def place(volume, path, thing, **fields):
    parts = path.strip("/").split("/")
    parent = None
    for name in parts[:-1]:
        parent, _ = Placement.objects.get_or_create(volume=volume, parent=parent, name=name, defaults={"kind": "folder"})
    return Placement.objects.create(volume=volume, parent=parent, name=parts[-1], kind="item", item=thing, **fields)


def local(machine, volume, point):
    return MachineMount.objects.create(machine=machine, volume=volume, mount_path=point)


def remote(machine, host, host_path, point, account=None):
    return MachineMount.objects.create(machine=machine, mode="remote", host=host, host_path=host_path, mount_path=point, account=account)


class NetworkCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ivan", password="x")
        cls.other = get_user_model().objects.create_user("petr", password="x")
        cls.client_machine = Machine.objects.create(name="Client", hostname="client")
        cls.host = Machine.objects.create(name="Host", hostname="host")
        cls.reader = MachineProfile.objects.create(machine=cls.host, login="reader", name="Reader", freq=1)
        cls.boss = MachineProfile.objects.create(machine=cls.host, login="boss", name="Boss", freq=2, root=True)
        cls.volume = Volume.objects.create(slug="harbor")
        place(cls.volume, "docs/plan.txt", item("plan", "the plan"))
        place(cls.volume, "docs/open.txt", item("open", "open"))
        local(cls.host, cls.volume, "/srv/harbor")
        Export.objects.create(machine=cls.host, path="/srv/harbor")


class ConnectionTests(NetworkCase):
    def test_an_exported_path_shows_on_the_client_as_a_folder_of_its_own_tree(self):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        view = MachineView(self.client_machine, self.user)
        self.assertTrue(view.is_directory("/mnt/h/docs"))
        self.assertEqual(view.get("/mnt/h/docs/plan.txt").body, "the plan")
        self.assertIsNone(view.get("/srv"))                                       # вне подключённого поддерева ничего нет

    def test_a_path_the_host_does_not_export_does_not_connect(self):
        remote(self.client_machine, self.host, "/srv", "/mnt/h", self.reader)
        self.assertFalse(MachineView(self.client_machine, self.user).exists("/mnt/h/harbor"))
        Export.objects.all().delete()
        self.assertEqual(MachineView(self.client_machine, self.user).children("/mnt/h"), [])         # точка осталась, а за ней пусто

    def test_a_subfolder_of_an_export_connects(self):
        remote(self.client_machine, self.host, "/srv/harbor/docs", "/mnt/d", self.reader)
        self.assertEqual(MachineView(self.client_machine, self.user).get("/mnt/d/open.txt").body, "open")

    def test_without_an_account_the_guest_record_of_the_host_is_used_if_there_is_one(self):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h")
        self.assertFalse(MachineView(self.client_machine, self.user).exists("/mnt/h/docs"))
        MachineProfile.objects.create(machine=self.host, login="guest", name="Guest", freq=3)
        self.assertTrue(MachineView(self.client_machine, self.user).exists("/mnt/h/docs"))

    def test_the_state_is_the_state_of_the_host_for_this_player_only(self):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        MachineView(self.client_machine, self.user).edit_text("/mnt/h/docs/open.txt", "from the client")
        self.assertEqual(MachineView(self.host, self.user).get("/srv/harbor/docs/open.txt").body, "from the client")
        self.assertEqual(MachineView(self.host, self.other).get("/srv/harbor/docs/open.txt").body, "open")
        MachineView(self.host, self.user).remove("/srv/harbor/docs/open.txt")
        self.assertFalse(MachineView(self.client_machine, self.user).exists("/mnt/h/docs/open.txt"))

    def test_a_write_to_a_dropped_connection_is_refused(self):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        Export.objects.all().delete()
        with self.assertRaises(ReadOnly):
            MachineView(self.client_machine, self.user).put_text("/mnt/h/new.txt", "x")


class AccountRightsTests(NetworkCase):
    def setUp(self):
        Placement.objects.filter(item__slug="plan").update(owner="boss", mode="600")

    def check(self, account, action="r"):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", account)
        profile, _ = MachineProfile.objects.get_or_create(machine=self.client_machine, login="ivan", freq=1, defaults={"name": "I"})
        view = MachineView(self.client_machine, self.user, principal_for(profile))
        rights.check(view, view.principal, "/mnt/h/docs/plan.txt", action)

    def test_the_rights_are_those_of_the_account_of_the_connection_not_of_the_client_record(self):
        with self.assertRaises(rights.Denied):
            self.check(self.reader)
        MachineMount.objects.filter(machine=self.client_machine).delete()
        self.check(self.boss)                                                     # root хоста читает

    def test_writing_through_the_connection_is_checked_on_the_host_and_owned_by_the_account(self):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        view = MachineView(self.client_machine, self.user, principal_for(self.boss))      # у клиента всё можно, а у учётки reader
        view.put_text("/mnt/h/note.txt", "x")
        self.assertEqual(MachineView(self.host, self.user).get("/srv/harbor/note.txt").owner, "reader")


class ChainTests(NetworkCase):
    def setUp(self):
        self.third = Machine.objects.create(name="Third", hostname="third")
        self.account = MachineProfile.objects.create(machine=self.third, login="svc", name="Svc", freq=1)
        archive = Volume.objects.create(slug="archive")
        place(archive, "deep/doc.txt", item("deep", "from the third"))
        local(self.third, archive, "/data")
        Export.objects.create(machine=self.third, path="/data")
        remote(self.host, self.third, "/data", "/srv/harbor/archive", self.account)       # хост сам подключает архив внутри экспорта

    def test_the_content_of_a_network_disk_inside_an_export_reaches_the_client_through_the_host(self):
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        view = MachineView(self.client_machine, self.user)
        self.assertEqual(view.get("/mnt/h/archive/deep/doc.txt").body, "from the third")

    def test_the_rights_of_the_second_hop_are_those_of_the_account_of_the_host_mount(self):
        Placement.objects.filter(item__slug="deep").update(owner="root", mode="600")
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        view = MachineView(self.client_machine, self.user, principal_for(self.reader))
        with self.assertRaises(rights.Denied):
            rights.check(view, view.principal, "/mnt/h/archive/deep/doc.txt", "r")

    def test_a_loop_of_hosts_stops(self):
        guest = MachineProfile.objects.create(machine=self.client_machine, login="guest", name="G", freq=9)
        Export.objects.create(machine=self.client_machine, path="/mnt")
        remote(self.host, self.client_machine, "/mnt", "/srv/harbor/back", None)
        remote(self.client_machine, self.host, "/srv/harbor", "/mnt/h", self.reader)
        view = MachineView(self.client_machine, self.user)
        self.assertTrue(view.exists("/mnt/h/docs"))
        self.assertFalse(view.exists("/mnt/h/back/h"))                              # назад по цепочке не ходят
