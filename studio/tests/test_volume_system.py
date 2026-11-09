"""Том отличий машины: один на машину, выбирается на вкладке «Тома»; тома отличий в списке томов отмечены системными.

Запуск: python manage.py test studio.tests.test_volume_system
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.manager import overlay
from filesystem.models import Volume
from machines.models import Machine, MachineMount


@override_settings(FORCE_SCRIPT_NAME=None)
class MachineOverlayApiTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True))
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.edge = Machine.objects.create(name="Edge", hostname="edge")
        self.base = Volume.objects.create(slug="base")
        MachineMount.objects.create(machine=self.core, volume=self.base, mount_path="/", order=0)
        MachineMount.objects.create(machine=self.edge, volume=self.base, mount_path="/", order=0)

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"/studio/api/{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_the_overlay_is_chosen_and_sits_on_top_of_the_root(self):
        mine = Volume.objects.create(slug="core-diff")
        status, disks = self.call("put", f"machines/{self.core.pk}/overlay", {"volume": mine.pk})
        self.assertEqual((status, disks["overlay"]["id"]), (200, mine.pk))
        flags = [(m["volume"]["id"], m["overlay"]) for m in disks["mounts"]]
        self.assertEqual(flags, [(self.base.pk, False), (mine.pk, True)])
        self.core.refresh_from_db()
        self.assertEqual(self.core.overlay, mine)

    def test_changing_the_choice_unmounts_the_old_volume_but_keeps_it(self):
        first, second = Volume.objects.create(slug="one"), Volume.objects.create(slug="two")
        self.call("put", f"machines/{self.core.pk}/overlay", {"volume": first.pk})
        disks = self.call("put", f"machines/{self.core.pk}/overlay", {"volume": second.pk})[1]
        self.assertEqual([m["volume"]["id"] for m in disks["mounts"]], [self.base.pk, second.pk])
        self.assertTrue(Volume.objects.filter(pk=first.pk).exists())
        disks = self.call("put", f"machines/{self.core.pk}/overlay", {"volume": None})[1]
        self.assertEqual((disks["overlay"], [m["volume"]["id"] for m in disks["mounts"]]), (None, [self.base.pk]))

    def test_a_volume_that_is_busy_elsewhere_cannot_be_the_overlay(self):
        MachineMount.objects.create(machine=self.edge, volume=self.base, mount_path="/mnt/b", order=0)
        taken = Volume.objects.create(slug="taken")
        MachineMount.objects.create(machine=self.edge, volume=taken, mount_path="/", order=1)
        theirs = Volume.objects.create(slug="theirs")
        self.call("put", f"machines/{self.edge.pk}/overlay", {"volume": theirs.pk})
        for volume in (self.base, taken, theirs):
            self.assertEqual(self.call("put", f"machines/{self.core.pk}/overlay", {"volume": volume.pk})[0], 400, volume.slug)
        choices = self.call("get", f"machines/{self.core.pk}/disks")[1]["overlay_choices"]
        self.assertEqual([c["id"] for c in choices], [])

    def test_the_overlay_mount_is_not_edited_by_hand(self):
        mine = Volume.objects.create(slug="core-diff")
        disks = self.call("put", f"machines/{self.core.pk}/overlay", {"volume": mine.pk})[1]
        mount = next(m for m in disks["mounts"] if m["overlay"])
        body = {"mode": "local", "volume": mine.pk, "mount_path": "/x", "order": 3}
        self.assertEqual(self.call("put", f"machines/{self.core.pk}/mounts/{mount['id']}", body)[0], 400)
        self.assertEqual(self.call("delete", f"machines/{self.core.pk}/mounts/{mount['id']}")[0], 400)
        self.assertEqual(self.call("post", f"machines/{self.core.pk}/mounts", {**body, "mount_path": "/y"})[0], 400)

    def test_the_volume_list_marks_the_overlays_of_machines_as_system(self):
        mine = Volume.objects.create(slug="core-diff")
        Volume.objects.create(slug="harbor")
        self.call("put", f"machines/{self.core.pk}/overlay", {"volume": mine.pk})
        rows = {r["slug"]: (r["system"], r["overlay_of"]) for r in self.call("get", "volumes")[1]}
        self.assertEqual(rows, {"base": (False, ""), "core-diff": (True, "core"), "harbor": (False, "")})

    def test_the_first_change_makes_the_volume_and_it_becomes_the_overlay(self):
        overlay.new_folder(self.core, "/", "srv")
        self.core.refresh_from_db()
        self.assertEqual(self.core.overlay.slug, "core-own")
        rows = {r["slug"]: r["system"] for r in self.call("get", "volumes")[1]}
        self.assertTrue(rows["core-own"])
