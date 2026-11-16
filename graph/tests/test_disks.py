"""Диски в графе: «Диск», «Машина: Диск», «Машина: Изменить диск»."""
from django.test import TestCase

from filesystem.machine_view import MachineView
from filesystem.models import Volume
from filesystem.testing import make_file
from graph import runtime
from graph.tests.test_data import f
from graph.tests.test_runtime import make, node, wire
from machines.models import Export, Machine, MachineMount, MachineProfile
from machines.world import disks


class DiskNodesTests(TestCase):
    def setUp(self):
        self.port = Machine.objects.create(name="Port", hostname="port")
        self.vault = Machine.objects.create(name="Vault", hostname="vault")
        self.archive = Volume.objects.create(slug="archive", name="backup")
        make_file(self.vault, "/srv/logs/a.log", body="лог")
        Export.objects.create(machine=self.vault, path="/srv")
        MachineProfile.objects.create(machine=self.vault, login="guest", name="guest", freq=1)

    def act(self, **fields):
        self.n = getattr(self, "n", 0) + 1
        graph = make([node("m", "manual"), node("a", "act:machine.disk", **fields)], [wire("m", "fire", "a")], slug=f"d{self.n}")
        runtime.start_manual(graph, "m", None)
        return graph

    def test_attach_remote_and_detach(self):
        self.act(variant="attach", machine="port", volume="archive", point="/mnt/archive")
        self.assertEqual(disks.of_machine(self.port), ["port:/mnt/archive"])
        self.assertEqual(disks.where(self.archive), ["port:/mnt/archive"])
        self.act(variant="remote", machine="port", host="vault", path="/srv/logs", point="/mnt/logs")
        self.assertTrue(MachineView(self.port, None).exists("/mnt/logs/a.log"))
        found = disks.props("port:/mnt/logs")
        self.assertEqual((found["type"], found["host"], found["account"]), ("сетевой", "vault", "guest@vault"))
        self.act(variant="remote", machine="port", host="vault", path="/etc", point="/mnt/etc")      # не отдаётся
        self.assertIsNone(disks.props("port:/mnt/etc"))
        self.act(variant="detach", mount="port:/mnt/logs")
        self.act(variant="detach", machine="port", volume="archive")
        self.assertEqual(MachineMount.objects.filter(machine=self.port).count(), 0)

    def test_entities_read_mount_and_volume(self):
        disks.attach(self.port, self.archive, "/mnt/archive", "docs")
        graph = make([node("m", "manual"), node("d", "ent:mount", machine="port", point="/mnt/archive"), node("v", "ent:volume"),
                      node("t", "act:tag", variant="on", owner="world")],
                     [wire("m", "fire", "t"), f("d", "volume", "v", "volume"), f("v", "name", "t", "name")])
        runtime.start_manual(graph, "m", None)
        from engine import values

        self.assertTrue(values.on("world", 0, "backup"))
        self.assertEqual(disks.props("port:/mnt/archive")["path"], "/docs")
        self.assertIsNone(disks.props("port:/nowhere"))

    def test_a_read_only_disk_refuses_a_player_but_not_the_scenario(self):
        from django.contrib.auth import get_user_model

        from filesystem.machine_view.entries import ReadOnly
        from machines.access.groups import principal_for

        make_file(self.port, "/home/x.txt", body="x")
        disks.attach_remote(self.port, self.vault, "/srv/logs", None, "/mnt/logs", read_only=True)
        self.act(variant="attach", machine="port", volume="archive", point="/mnt/archive", read_only=True)
        self.assertTrue(disks.props("port:/mnt/archive")["read_only"])
        root = MachineProfile.objects.create(machine=self.port, login="root", name="root", freq=3, root=True)
        view = MachineView(self.port, get_user_model().objects.create_user("ivan"), principal_for(root))
        for write in (lambda: view.put_text("/mnt/archive/n.txt", "n"), lambda: view.remove("/mnt/logs/a.log")):
            with self.assertRaises(ReadOnly):
                write()
        view.put_text("/home/y.txt", "y")                                                  # остальная машина пишется
        MachineView(self.port, None).put_text("/mnt/archive/n.txt", "n")                   # сценарий пишет
