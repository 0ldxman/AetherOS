"""Админка объектов, томов, размещений, монтирований и типов систем."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import get_script_prefix, reverse, set_script_prefix

from assets.models import Asset
from filesystem.models import FileFormat, Item, Placement, Volume
from machines.models import Machine, MachineMount, Place, SystemType


def post_item(client, **fields):
    data = {
        "slug": "x", "name": "x", "format": "", "body": "", "url": "", "access": "{}", "state": "", "meta": "",
        "keys-TOTAL_FORMS": "0", "keys-INITIAL_FORMS": "0", "keys-MIN_NUM_FORMS": "0", "keys-MAX_NUM_FORMS": "1000",
        "signatures-TOTAL_FORMS": "0", "signatures-INITIAL_FORMS": "0", "signatures-MIN_NUM_FORMS": "0", "signatures-MAX_NUM_FORMS": "1000",
    }
    data.update(fields)
    return client.post(reverse("admin:filesystem_item_add"), data)


class AdminCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_superuser("boss", "b@example.com", "pw")
        FileFormat.objects.update_or_create(name="txt", defaults={"extension": ".txt", "content": "text_asset", "page": False})
        FileFormat.objects.update_or_create(name="rec", defaults={"extension": ".rec", "content": "text", "page": True})
        FileFormat.objects.update_or_create(name="png", defaults={"extension": ".png", "content": "link_asset"})
        FileFormat.objects.update_or_create(name="key", defaults={"extension": ".key", "content": "text"})

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.boss)


class ItemAdminTests(AdminCase):
    def test_the_pages_open(self):
        for name in ("item", "volume", "placement"):
            self.assertEqual(self.client.get(reverse(f"admin:filesystem_{name}_changelist")).status_code, 200, name)
            self.assertEqual(self.client.get(reverse(f"admin:filesystem_{name}_add")).status_code, 200, name)

    def test_the_form_has_the_editor_a_format_list_and_the_table_of_formats(self):
        page = self.client.get(reverse("admin:filesystem_item_add"))
        self.assertContains(page, "wiki/editor.js")
        self.assertContains(page, "item_admin.js")
        self.assertContains(page, 'id="wp-split"')
        self.assertContains(page, 'value="rec"')
        table = page.context["formats"]
        self.assertEqual(table["rec"]["page"], True)
        self.assertEqual(table["png"]["content"], "link_asset")

    def test_a_text_object_is_saved_with_its_author(self):
        response = post_item(self.client, slug="notes", name="Notes", format="txt", body="hello")
        self.assertEqual(response.status_code, 302)
        item = Item.objects.get(slug="notes")
        self.assertEqual((item.body, item.created_by, item.updated_by), ("hello", self.boss, self.boss))

    def test_the_content_is_checked_by_the_format(self):
        response = post_item(self.client, slug="pic", name="pic", format="png")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нужно указать содержимое")
        ok = post_item(self.client, slug="pic", name="pic", format="png", url="https://example.com/a.png")
        self.assertEqual(ok.status_code, 302)
        bad = post_item(self.client, slug="p2", name="p2", format="png", body="text")
        self.assertContains(bad, "это поле не используется")

    def test_an_asset_is_chosen_with_a_search_and_an_add_link(self):
        asset = Asset.objects.create(name="Harbor photo", file_id="9", slug="harbor")
        page = self.client.get(reverse("admin:filesystem_item_add"))
        self.assertContains(page, "autocomplete")
        found = self.client.get(reverse("admin:autocomplete"), {"term": "Harbor", "app_label": "filesystem", "model_name": "item", "field_name": "asset"})
        self.assertEqual(found.status_code, 200)
        self.assertEqual([row["id"] for row in found.json()["results"]], [str(asset.pk)])

    def test_the_condition_editor_offers_the_keys_that_are_objects(self):
        Item.objects.create(slug="alpha", name="Alpha key", format="key", body="k")
        Item.objects.create(slug="plain", name="Plain", format="txt")
        page = self.client.get(reverse("admin:filesystem_item_add"))
        keys = [row["slug"] for row in json.loads(page.context["adminform"].form.fields["access"].widget.get_context("access", "{}", {})["widget"]["attrs"]["data-keys"])]
        self.assertEqual(keys, ["alpha"])
        self.assertContains(page, "data-condition-editor")

    def test_a_key_and_a_signature_are_chosen_only_among_keys(self):
        Item.objects.create(slug="alpha", name="Alpha", format="key", body="k")
        Item.objects.create(slug="plain", name="Plain", format="txt")
        item = Item.objects.create(slug="doc", name="doc", format="txt")
        page = self.client.get(reverse("admin:filesystem_item_change", args=[item.pk]))
        for inline in page.context["inline_admin_formsets"]:
            self.assertEqual([obj.slug for obj in inline.formset.empty_form.fields["key"].queryset], ["alpha"])

    def test_the_preview_renders_a_page_as_a_wiki_page_and_other_formats_as_text(self):
        url = reverse("admin:filesystem_item_preview")
        page = self.client.post(url, json.dumps({"type": "rec", "title": "T", "body": "# Heading\n\ntext", "infobox": ""}), content_type="application/json")
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.json()["ok"])
        self.assertIn("Heading", page.json()["body"])
        plain = self.client.post(url, json.dumps({"type": "txt", "title": "T", "body": "<b>raw</b>", "infobox": ""}), content_type="application/json")
        self.assertIn("&lt;b&gt;raw&lt;/b&gt;", plain.json()["body"])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_the_preview_needs_a_login(self):
        self.client.logout()
        response = self.client.post(reverse("admin:filesystem_item_preview"), "{}", content_type="application/json")
        self.assertEqual(response.status_code, 302)

    def test_the_list_shows_what_each_object_holds(self):
        Item.objects.create(slug="empty", name="e", format="txt")
        Item.objects.create(slug="text", name="t", format="txt", body="abc")
        page = self.client.get(reverse("admin:filesystem_item_changelist"))
        self.assertContains(page, "текст, 3 зн.")
        self.assertContains(page, "пусто")


class VolumeAdminTests(AdminCase):
    def setUp(self):
        super().setUp()
        self.volume = Volume.objects.create(slug="harbor", name="Harbor disk", label="Archive")
        self.item = Item.objects.create(slug="report", name="Report", format="rec", body="x")
        etc = Placement.objects.create(volume=self.volume, kind="folder", name="etc")
        Placement.objects.create(volume=self.volume, kind="item", item=self.item, parent=etc, hidden=True)
        Placement.objects.create(volume=self.volume, kind="item", item=self.item, name="top.rec")

    def test_the_change_form_has_the_mounts_and_a_link_to_the_tree(self):
        page = self.client.get(reverse("admin:filesystem_volume_change", args=[self.volume.pk]))
        self.assertContains(page, reverse("admin:filesystem_volume_tree", args=[self.volume.pk]))
        self.assertContains(page, "mount_path")

    def test_the_tree_shows_folders_first_and_the_flags(self):
        page = self.client.get(reverse("admin:filesystem_volume_tree", args=[self.volume.pk]))
        content = page.content.decode()
        self.assertLess(content.index("etc"), content.index("top.rec"))
        self.assertContains(page, "Report.rec")
        self.assertContains(page, "скрыт")
        self.assertContains(page, "+ сюда")
        self.assertContains(page, "report")                                          # объект, на который ссылается размещение

    def test_a_missing_volume_is_a_404(self):
        self.assertEqual(self.client.get(reverse("admin:filesystem_volume_tree", args=[999])).status_code, 404)

    def test_the_list_counts_placements(self):
        page = self.client.get(reverse("admin:filesystem_volume_changelist"))
        self.assertContains(page, "harbor")
        self.assertEqual(list(page.context["cl"].result_list)[0]._placements, 3)

    def test_a_placement_is_added_into_a_folder_from_the_tree_and_named_after_the_object(self):
        folder = Placement.objects.create(volume=self.volume, kind="folder", name="docs")
        add = reverse("admin:filesystem_placement_add")
        page = self.client.get(add, {"volume": self.volume.pk, "parent": folder.pk})
        self.assertEqual(page.context["adminform"].form.initial["parent"], str(folder.pk))
        response = self.client.post(add, {
            "volume": self.volume.pk, "parent": folder.pk, "kind": "item", "item": self.item.pk, "name": "",
            "access_mode": "inherit", "access": "{}", "state_mode": "inherit", "state": "",
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        self.assertTrue(Placement.objects.filter(parent=folder, name="Report.rec").exists())

    def test_a_name_that_is_taken_is_a_form_error_not_a_crash(self):
        folder = Placement.objects.get(name="etc")                                     # в etc уже лежит Report.rec
        response = self.client.post(reverse("admin:filesystem_placement_add"), {
            "volume": self.volume.pk, "parent": folder.pk, "kind": "item", "item": self.item.pk, "name": "",
            "access_mode": "inherit", "access": "{}", "state_mode": "inherit", "state": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Placement.objects.filter(parent=folder).count(), 1)

    def test_the_parent_choices_are_the_folders_of_the_chosen_volume(self):
        other = Volume.objects.create(slug="other")
        Placement.objects.create(volume=other, kind="folder", name="elsewhere")
        page = self.client.get(reverse("admin:filesystem_placement_add"), {"volume": self.volume.pk})
        names = [folder.name for folder in page.context["adminform"].form.fields["parent"].queryset]
        self.assertEqual(names, ["etc"])


class MachineAdminTests(AdminCase):
    def setUp(self):
        super().setUp()
        self.machine = Machine.objects.create(name="Gateway", hostname="gw-02")
        self.base = Volume.objects.create(slug="aether-base")
        self.own = Volume.objects.create(slug="gw-own")
        hosts = Item.objects.create(slug="hosts", name="hosts", format="txt", body="base")
        motd = Item.objects.create(slug="motd", name="motd", format="txt", body="hello")
        Placement.objects.create(volume=self.base, kind="item", item=hosts, name="hosts")
        Placement.objects.create(volume=self.base, kind="item", item=motd, name="motd")
        Placement.objects.create(volume=self.own, kind="item", item=Item.objects.create(slug="hosts2", name="hosts2", format="txt", body="own"), name="hosts")
        Placement.objects.create(volume=self.own, kind="item", item=Item.objects.create(slug="extra", name="extra", format="txt"), name="extra")
        Placement.objects.create(volume=self.own, kind="whiteout", name="motd")
        MachineMount.objects.create(machine=self.machine, volume=self.base, mount_path="/", order=0)
        MachineMount.objects.create(machine=self.machine, volume=self.own, mount_path="/", order=1)

    def test_the_machine_page_has_mounts_places_and_a_link_to_the_files(self):
        page = self.client.get(reverse("admin:machines_machine_change", args=[self.machine.pk]))
        self.assertContains(page, "mount_path")
        self.assertContains(page, "places-TOTAL_FORMS")
        self.assertContains(page, reverse("admin:machines_machine_files", args=[self.machine.pk]))

    def test_the_system_is_chosen_from_the_registered_types(self):
        SystemType.objects.create(code="WIN", name="Windows", path_style="windows")
        field = self.client.get(reverse("admin:machines_machine_change", args=[self.machine.pk])).context["adminform"].form.fields["system"]
        self.assertEqual({code for code, _ in field.choices}, {"AETHER", "WIN"})

    def test_the_files_page_marks_where_each_file_comes_from(self):
        page = self.client.get(reverse("admin:machines_machine_files", args=[self.machine.pk]))
        rows = {row["path"]: row for row in page.context["rows"]}
        self.assertEqual((rows["/hosts"]["volume"], rows["/hosts"]["mark"]), ("gw-own", "перекрывает"))
        self.assertEqual((rows["/extra"]["volume"], rows["/extra"]["mark"]), ("gw-own", "добавлен"))
        self.assertNotIn("/motd", rows)                                              # скрыт надгробием
        self.assertEqual(page.context["hidden"], [{"path": "/motd", "volume": "gw-own"}])
        self.assertContains(page, "Скрыто надгробиями")

    def test_a_lone_layer_has_no_marks(self):
        machine = Machine.objects.create(name="Plain", hostname="plain")
        MachineMount.objects.create(machine=machine, volume=self.base, mount_path="/")
        page = self.client.get(reverse("admin:machines_machine_files", args=[machine.pk]))
        self.assertEqual({row["mark"] for row in page.context["rows"]}, {""})

    def test_a_missing_machine_is_a_404(self):
        self.assertEqual(self.client.get(reverse("admin:machines_machine_files", args=[999])).status_code, 404)

    def test_the_system_type_page_has_its_places(self):
        aether = SystemType.objects.get(code="AETHER")
        Place.objects.create(system_type=aether, name="secrets", path="{home}/.keys")
        page = self.client.get(reverse("admin:machines_systemtype_change", args=[aether.pk]))
        self.assertContains(page, "{home}/.keys")
        self.assertEqual(self.client.get(reverse("admin:machines_systemtype_changelist")).status_code, 200)
