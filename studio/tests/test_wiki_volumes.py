import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.models import Placement
from machines.models import Export, Machine, MachineMount, MachineProfile
from wiki.testing import make_document, make_namespace


@override_settings(FORCE_SCRIPT_NAME=None)
class WikiVolumesApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True)
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.host = Machine.objects.create(name="Archive", hostname="archive-srv")
        MachineProfile.objects.create(machine=cls.host, login="reader", name="Reader", freq=1)
        archive = make_namespace("Архив порта")
        make_document(archive, "Манифест", body="груз")
        closed = make_document(archive, "Закрытая", body="тайна")
        Placement.objects.filter(pk=closed.placement.pk).update(owner="root", mode="600")
        MachineMount.objects.create(machine=cls.host, volume=archive.volume, mount_path="/srv/harbor")
        Export.objects.create(machine=cls.host, path="/srv/harbor")
        empty = make_namespace("Пустой")
        MachineMount.objects.create(machine=cls.host, volume=empty.volume, mount_path="/srv/empty")
        Export.objects.create(machine=cls.host, path="/srv/empty")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        cache.clear()
        self.client.force_login(self.boss)

    def check(self, *lines, machine=None):
        response = self.client.post("/studio/api/wiki-volumes/check", data=json.dumps({"lines": list(lines), "machine": machine}), content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_the_hosts_come_with_their_exports_and_accounts(self):
        found = {h["hostname"]: h for h in self.client.get("/studio/api/wiki-volumes/hosts").json()}
        self.assertEqual(sorted(found["archive-srv"]["exports"]), ["/srv/empty", "/srv/harbor"])
        self.assertEqual([a["login"] for a in found["archive-srv"]["accounts"]], ["reader"])

    def test_a_good_line_says_how_many_pages_open_and_how_many_are_closed_by_rights(self):
        [result] = self.check({"host": "archive-srv", "path": "/srv/harbor", "title": "Harbor", "user": "reader"})
        self.assertEqual((result["ok"], result["title"], result["pages"], result["closed"]), (True, "Harbor", 1, 1))

    def test_every_refusal_names_its_reason(self):
        lines = [
            {"host": "nowhere", "path": "/srv/harbor"},
            {"host": "archive-srv", "path": "/srv/harbor", "user": "stranger"},
            {"host": "archive-srv", "path": "/etc", "user": "reader"},
            {"host": "archive-srv", "path": "/srv/harbor/none", "user": "reader"},
            {"host": "archive-srv", "path": "/srv/empty", "user": "reader"},
        ]
        self.assertEqual([r["reason"] for r in self.check(*lines)], ["no_host", "no_account", "not_exported", "no_folder", "empty"])
        self.assertTrue(all(r["message"] for r in self.check(*lines)))

    def test_the_own_machine_needs_a_machine_to_check_on_and_a_duplicate_title_is_flagged(self):
        [result] = self.check({"path": "/home"})
        self.assertEqual(result["reason"], "no_machine")
        a, b = self.check({"host": "archive-srv", "path": "/srv/harbor", "title": "Same", "user": "reader"}, {"host": "archive-srv", "path": "/srv/harbor", "title": "same", "user": "reader"})
        self.assertEqual((a["duplicate"], b["duplicate"]), (True, True))
        [one] = self.check({"host": "archive-srv", "path": "/srv/harbor", "user": "reader"})
        self.assertEqual((one["title"], one["duplicate"]), ("harbor", False))
