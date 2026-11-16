from team.testing import full_role
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
        cls.boss = get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role())
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

    def test_a_guarded_account_needs_its_password_token_or_key(self):
        from machines.world import edits

        guarded = MachineProfile.objects.create(machine=self.host, login="keeper", name="Keeper", freq=2)
        edits.set_password(guarded, "s3cret")
        token = edits.create_token(guarded)
        base = {"host": "archive-srv", "path": "/srv/harbor", "user": "keeper"}
        results = self.check(base, {**base, "password": "wrong"}, {**base, "password": "s3cret"}, {**base, "token": token})
        self.assertEqual([r["reason"] or "ok" for r in results], ["no_entry", "no_entry", "ok", "ok"])
        edits.set_password(guarded, "")
        edits.set_keys(guarded, "cardkey")
        no_key, with_key = self.check(base, {**base, "key": "cardkey"})
        self.assertEqual((no_key["reason"], with_key["ok"]), ("no_entry", True))

    def test_the_line_keeps_its_way_in(self):
        from filesystem.appfile import parse_volume

        line = parse_volume("archive-srv:/srv/harbor as Порт и док user=keeper pass=s3cret")
        self.assertEqual((line.title, line.user, line.password, line.token), ("Порт и док", "keeper", "s3cret", ""))
        self.assertIsNone(parse_volume("archive-srv:/srv/harbor junk"))

    def test_a_player_share_opens_as_a_section_with_its_code(self):
        from machines.models import Share

        owner = MachineProfile.objects.create(machine=self.host, login="ivan", name="Ivan", freq=3)
        Share.objects.create(machine=self.host, profile=owner, name="ivan-harbor", path="/srv/harbor", code="ab12-cd34")
        good, bad, none = self.check({"host": "archive-srv", "path": "ivan-harbor", "token": "ab12-cd34", "title": "Порт"},
                                     {"host": "archive-srv", "path": "ivan-harbor", "token": "nope"},
                                     {"host": "archive-srv", "path": "nobody"})
        self.assertEqual((good["ok"], good["pages"]), (True, 1), good)
        self.assertEqual((bad["reason"], none["reason"]), ("no_share", "no_share"))
        machine = self.client.get(f"/studio/api/machines/{self.host.pk}/disks").json()
        self.assertEqual([(s["name"], s["owner"], s["code"]) for s in machine["shares"]], [("ivan-harbor", "ivan", "ab12-cd34")])
        self.client.delete(f"/studio/api/machines/{self.host.pk}/shares/{machine['shares'][0]['id']}")
        self.assertFalse(Share.objects.exists())
