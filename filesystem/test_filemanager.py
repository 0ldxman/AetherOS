"""Файловый менеджер: операции над томом, правки машины (слой отличий) и их JSON-интерфейс."""
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem import filemanager, overlay
from filesystem.filemanager import FileManagerError
from filesystem.machine_view import MachineView
from filesystem.models import FileFormat, Item, ItemKey, Placement, Volume, VolumeTemplate
from machines.models import Machine, MachineMount


def fmt(name, extension, content="text_asset", **extra):
    FileFormat.objects.update_or_create(name=name, defaults={"extension": extension, "content": content, **extra})


def put(volume, path, body=None, **fields):
    """Положить файл (с телом) или папку (body=None) по пути, недостающие папки создаются."""
    parts = path.strip("/").split("/")
    parent = None
    for name in parts[:-1]:
        parent, _ = Placement.objects.get_or_create(volume=volume, parent=parent, name=name, defaults={"kind": "folder"})
    if body is None and fields.get("kind") != "whiteout":
        return Placement.objects.create(volume=volume, parent=parent, kind="folder", name=parts[-1])
    if fields.get("kind") == "whiteout":
        return Placement.objects.create(volume=volume, parent=parent, name=parts[-1], **fields)
    item = Item.objects.create(slug=f"{volume.slug}-{path.strip('/').replace('/', '-')}", name=parts[-1], body=body)
    return Placement.objects.create(volume=volume, parent=parent, kind="item", item=item, name=parts[-1], **fields)


class VolumeOpsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fmt("txt", ".txt")
        fmt("jpg", ".jpg", "link_asset", aliases="jpeg")

    def setUp(self):
        self.volume = Volume.objects.create(slug="v")

    def names(self, parent=None):
        return sorted(Placement.objects.filter(volume=self.volume, parent=parent).values_list("name", flat=True))

    def test_a_folder_is_made_and_a_taken_name_is_refused(self):
        filemanager.new_folder(self.volume, None, "docs")
        self.assertEqual(self.names(), ["docs"])
        with self.assertRaises(FileManagerError) as caught:
            filemanager.new_folder(self.volume, None, "docs")
        self.assertIn("уже есть", str(caught.exception))
        for bad in ("a/b", "", "  ", "a:b", ".."):
            with self.assertRaises(FileManagerError):
                filemanager.new_folder(self.volume, None, bad)

    def test_a_file_takes_its_format_from_the_extension(self):
        placement = filemanager.new_file(self.volume, None, "notes.txt")
        self.assertEqual((placement.name, placement.item.name, placement.item.format), ("notes.txt", "notes", "txt"))
        self.assertEqual(filemanager.new_file(self.volume, None, "photo.JPEG").item.format, "jpg")   # псевдоним и регистр
        plain = filemanager.new_file(self.volume, None, "README")
        self.assertEqual((plain.name, plain.item.format), ("README", ""))
        self.assertEqual(filemanager.new_file(self.volume, None, "archive.unknown").item.format, "")

    def test_a_chosen_format_adds_its_extension_once(self):
        self.assertEqual(filemanager.new_file(self.volume, None, "memo", "txt").name, "memo.txt")
        self.assertEqual(filemanager.new_file(self.volume, None, "memo2.txt", "txt").name, "memo2.txt")
        with self.assertRaises(FileManagerError):
            filemanager.new_file(self.volume, None, "x", "nope")

    def test_slugs_of_new_objects_are_unique(self):
        slugs = {filemanager.new_file(self.volume, None, f"a{n}.txt", "").item.slug for n in range(3)}
        self.assertEqual(len(slugs), 3)
        other = Volume.objects.create(slug="o")
        first = filemanager.new_file(self.volume, None, "same.txt").item.slug
        second = filemanager.new_file(other, None, "same.txt").item.slug
        self.assertNotEqual(first, second)
        self.assertEqual(filemanager.new_file(self.volume, None, "Отчёт.txt").item.slug[:4], "item")

    def test_a_file_goes_into_a_folder_of_this_volume_only(self):
        folder = filemanager.new_folder(self.volume, None, "docs")
        filemanager.new_file(self.volume, folder.pk, "a.txt")
        self.assertEqual(self.names(folder), ["a.txt"])
        elsewhere = Placement.objects.create(volume=Volume.objects.create(slug="o"), kind="folder", name="x")
        with self.assertRaises(FileManagerError):
            filemanager.new_file(self.volume, elsewhere.pk, "b.txt")

    def test_an_existing_object_is_put_into_a_folder_under_its_name(self):
        item = Item.objects.create(slug="shared", name="Shared", format="txt")
        filemanager.link(self.volume, None, item.pk)
        self.assertEqual(self.names(), ["Shared.txt"])
        with self.assertRaises(FileManagerError):
            filemanager.link(self.volume, None, item.pk)
        filemanager.link(self.volume, None, item.pk, "other.txt")
        self.assertEqual(item.placements.count(), 2)

    def test_a_rename_checks_the_siblings(self):
        a = filemanager.new_folder(self.volume, None, "a")
        filemanager.new_folder(self.volume, None, "b")
        with self.assertRaises(FileManagerError):
            filemanager.rename(self.volume, a.pk, "b")
        filemanager.rename(self.volume, a.pk, "a")                                    # то же имя можно
        self.assertEqual(filemanager.rename(self.volume, a.pk, "c").name, "c")

    def test_a_delete_takes_a_folder_with_its_content_but_keeps_the_objects(self):
        folder = filemanager.new_folder(self.volume, None, "docs")
        placement = filemanager.new_file(self.volume, folder.pk, "a.txt")
        filemanager.delete(self.volume, [folder.pk])
        self.assertEqual(self.names(), [])
        self.assertTrue(Item.objects.filter(pk=placement.item_id).exists())
        with self.assertRaises(FileManagerError):
            filemanager.delete(self.volume, [999999])

    def test_a_move_refuses_a_folder_into_itself_and_a_taken_name(self):
        a = filemanager.new_folder(self.volume, None, "a")
        b = filemanager.new_folder(self.volume, a.pk, "b")
        with self.assertRaises(FileManagerError):
            filemanager.move(self.volume, [a.pk], b.pk)
        with self.assertRaises(FileManagerError):
            filemanager.move(self.volume, [a.pk], a.pk)
        filemanager.new_folder(self.volume, None, "b")
        with self.assertRaises(FileManagerError):
            filemanager.move(self.volume, [b.pk], None)                                # «b» в корне занято
        moved = filemanager.new_file(self.volume, None, "f.txt")
        filemanager.move(self.volume, [moved.pk], b.pk)
        self.assertEqual(self.names(b), ["f.txt"])

    def test_a_copy_gets_a_copy_name_and_shares_the_objects(self):
        placement = filemanager.new_file(self.volume, None, "f.txt")
        filemanager.copy(self.volume, [placement.pk], None)
        filemanager.copy(self.volume, [placement.pk], None)
        self.assertEqual(self.names(), ["f - копия (2).txt", "f - копия.txt", "f.txt"])
        self.assertEqual(Item.objects.filter(slug__startswith="f").count(), 1)

    def test_a_folder_is_copied_with_its_content(self):
        folder = filemanager.new_folder(self.volume, None, "docs")
        filemanager.new_file(self.volume, folder.pk, "a.txt")
        self.assertEqual(filemanager.copy(self.volume, [folder.pk], None), 2)
        copy = Placement.objects.get(volume=self.volume, name="docs - копия")
        self.assertEqual(self.names(copy), ["a.txt"])
        with self.assertRaises(FileManagerError):
            filemanager.copy(self.volume, [folder.pk], folder.pk)

    def test_the_flags_are_set(self):
        placement = filemanager.new_file(self.volume, None, "f.txt")
        filemanager.set_flags(self.volume, placement.pk, hidden=True, system=True)
        placement.refresh_from_db()
        self.assertEqual((placement.hidden, placement.system), (True, True))

    def test_the_templates_make_the_folders_of_a_system(self):
        unix = VolumeTemplate.objects.get(name="Unix-подобная система")
        self.assertEqual(filemanager.apply_template(self.volume, unix), 9)
        log = Placement.objects.get(volume=self.volume, name="log")
        self.assertEqual(log.parent.name, "var")
        win = Volume.objects.create(slug="win")
        filemanager.apply_template(win, VolumeTemplate.objects.get(name="Windows-подобная система"))
        self.assertTrue(Placement.objects.filter(volume=win, name="System32", parent__name="Windows").exists())
        self.assertEqual(filemanager.apply_template(Volume.objects.create(slug="e"), None), 0)

    def test_a_template_is_edited_as_text_and_its_parents_are_implied(self):
        custom = VolumeTemplate.objects.create(name="Aether", folders="# система\nsys/core\nhome/\nsys/core\n", system=False)
        self.assertEqual(custom.paths(), ["home", "sys", "sys/core"])
        self.assertEqual(filemanager.apply_template(self.volume, custom), 3)
        self.assertFalse(Placement.objects.get(volume=self.volume, name="core").system)
        with self.assertRaises(ValidationError):
            VolumeTemplate(name="Bad", folders="a/b:c").full_clean()


class OverlayTests(TestCase):
    """Правки машины: изменения лежат в её собственном томе, общий образ не трогается."""

    @classmethod
    def setUpTestData(cls):
        fmt("txt", ".txt")

    def setUp(self):
        self.machine = Machine.objects.create(name="Gateway", hostname="gw-02")
        self.other = Machine.objects.create(name="Other", hostname="other")
        self.base = Volume.objects.create(slug="base")
        put(self.base, "etc/hosts", "base hosts")
        put(self.base, "etc/motd", "hello")
        put(self.base, "bin/ls", "ls")
        MachineMount.objects.create(machine=self.machine, volume=self.base, mount_path="/", order=0)
        MachineMount.objects.create(machine=self.other, volume=self.base, mount_path="/", order=0)

    def view(self, machine=None):
        return MachineView(machine or self.machine, None)

    def test_the_own_volume_of_a_machine_is_made_on_the_first_change_and_mounted_on_top(self):
        self.assertEqual(Volume.objects.count(), 1)
        overlay.new_folder(self.machine, "/", "srv")
        own = Volume.objects.get(slug="gw-02-own")
        mount = MachineMount.objects.get(machine=self.machine, volume=own)
        self.assertEqual((mount.mount_path, mount.order), ("/", 1))
        overlay.new_folder(self.machine, "/", "tmp")                                  # второй раз тот же том
        self.assertEqual(Volume.objects.count(), 2)

    def test_a_shared_volume_is_never_changed_and_other_machines_do_not_see_the_changes(self):
        overlay.new_file(self.machine, "/etc", "extra.txt")
        self.assertTrue(self.view().exists("/etc/extra.txt"))
        self.assertFalse(self.view(self.other).exists("/etc/extra.txt"))
        self.assertEqual(Placement.objects.filter(volume=self.base).count(), 5)

    def test_a_new_file_is_checked_against_the_whole_view(self):
        with self.assertRaises(FileManagerError):
            overlay.new_file(self.machine, "/etc", "hosts")                           # такой уже есть в образе
        with self.assertRaises(FileManagerError):
            overlay.new_folder(self.machine, "/nowhere", "x")

    def test_a_new_file_deep_in_the_tree_makes_the_folders_in_the_own_volume(self):
        overlay.new_file(self.machine, "/etc", "extra.txt")
        own = Volume.objects.get(slug="gw-02-own")
        self.assertEqual(Placement.objects.get(volume=own, name="extra.txt").parent.name, "etc")

    def test_overriding_a_file_copies_the_object_and_leaves_the_image_alone(self):
        key = Item.objects.create(slug="alpha", name="alpha", format="key", body="k")
        original = Item.objects.get(slug="base-etc-hosts")
        ItemKey.objects.create(item=original, key=key)
        copy = overlay.override(self.machine, "/etc/hosts")
        self.assertNotEqual(copy.pk, original.pk)
        self.assertEqual((copy.body, copy.keys.count()), ("base hosts", 1))
        self.assertEqual(self.view().get("/etc/hosts").item.pk, copy.pk)
        self.assertEqual(self.view(self.other).get("/etc/hosts").item.pk, original.pk)
        self.assertEqual(overlay.override(self.machine, "/etc/hosts").pk, copy.pk)    # повторно: тот же объект

    def test_a_file_of_the_own_volume_is_edited_in_place(self):
        created = overlay.new_file(self.machine, "/", "mine.txt")
        self.assertEqual(overlay.override(self.machine, "/mine.txt").pk, created.item_id)

    def test_only_a_file_can_be_overridden(self):
        with self.assertRaises(FileManagerError):
            overlay.override(self.machine, "/etc")
        with self.assertRaises(FileManagerError):
            overlay.override(self.machine, "/nothing")

    def test_a_deleted_image_file_is_hidden_by_a_whiteout_and_can_be_restored(self):
        overlay.delete(self.machine, "/etc/motd")
        self.assertFalse(self.view().exists("/etc/motd"))
        self.assertTrue(self.view(self.other).exists("/etc/motd"))
        red = [row for row in overlay.machine_data(self.machine)["rows"] if row["kind"] == "deleted"]
        self.assertEqual([(row["path"], row["private"]) for row in red], [("/etc/motd", True)])
        overlay.restore(self.machine, "/etc/motd")
        self.assertTrue(self.view().exists("/etc/motd"))
        self.assertEqual([row for row in overlay.machine_data(self.machine)["rows"] if row["kind"] == "deleted"], [])

    def test_a_whiteout_that_hides_nothing_is_not_shown(self):
        own, _ = (lambda m: (m, None))(overlay.overlay_for(self.machine, "/"))
        Placement.objects.create(volume=own[1], kind="whiteout", name="ghost")
        self.assertEqual([row for row in overlay.machine_data(self.machine)["rows"] if row["kind"] == "deleted"], [])

    def test_a_whole_folder_of_the_image_is_hidden(self):
        overlay.delete(self.machine, "/bin")
        self.assertFalse(self.view().exists("/bin"))
        self.assertFalse(self.view().exists("/bin/ls"))

    def test_deleting_an_override_hides_the_image_file_below_too(self):
        overlay.override(self.machine, "/etc/hosts")
        overlay.delete(self.machine, "/etc/hosts")
        self.assertFalse(self.view().exists("/etc/hosts"))

    def test_deleting_a_file_that_exists_only_in_the_own_volume_leaves_no_whiteout(self):
        overlay.new_file(self.machine, "/", "temp.txt")
        overlay.delete(self.machine, "/temp.txt")
        self.assertFalse(self.view().exists("/temp.txt"))
        self.assertFalse(Placement.objects.filter(kind="whiteout").exists())

    def test_a_reset_brings_back_the_image_file(self):
        copy = overlay.override(self.machine, "/etc/hosts")
        overlay.reset(self.machine, "/etc/hosts")
        self.assertEqual(self.view().get("/etc/hosts").item.slug, "base-etc-hosts")
        with self.assertRaises(FileManagerError):
            overlay.reset(self.machine, "/etc/hosts")                                 # уже не менялся

    def test_a_restore_of_a_visible_file_is_refused(self):
        with self.assertRaises(FileManagerError):
            overlay.restore(self.machine, "/etc/hosts")

    def test_a_whiteout_in_a_shared_volume_cannot_be_restored_from_a_machine(self):
        put(self.base, "etc/old", "x")
        shared = Volume.objects.create(slug="shared")
        put(shared, "etc/old", kind="whiteout")
        MachineMount.objects.create(machine=self.machine, volume=shared, mount_path="/", order=1)
        MachineMount.objects.create(machine=self.other, volume=shared, mount_path="/", order=1)
        with self.assertRaises(FileManagerError) as caught:
            overlay.restore(self.machine, "/etc/old")
        self.assertIn("shared", str(caught.exception))

    def test_a_shared_top_layer_gets_a_private_layer_above_it(self):
        shared = Volume.objects.create(slug="shared")
        put(shared, "etc/extra", "x")
        MachineMount.objects.create(machine=self.machine, volume=shared, mount_path="/", order=1)
        MachineMount.objects.create(machine=self.other, volume=shared, mount_path="/", order=1)
        overlay.new_folder(self.machine, "/", "mine")
        own = MachineMount.objects.get(volume__slug="gw-02-own")
        self.assertEqual(own.order, 2)
        self.assertFalse(Placement.objects.filter(volume=shared, name="mine").exists())

    def test_a_mounted_library_is_overlaid_on_its_own_point(self):
        library = Volume.objects.create(slug="library")
        put(library, "report", "r")
        MachineMount.objects.create(machine=self.machine, volume=library, mount_path="/mnt/lib", order=0)
        MachineMount.objects.create(machine=self.other, volume=library, mount_path="/mnt/lib", order=0)
        copy = overlay.override(self.machine, "/mnt/lib/report")
        own = MachineMount.objects.get(volume__slug="gw-02-own")
        self.assertEqual((own.mount_path, own.order), ("/mnt/lib", 1))
        self.assertEqual(self.view().get("/mnt/lib/report").item.pk, copy.pk)
        self.assertEqual(self.view(self.other).get("/mnt/lib/report").item.slug, "library-report")

    def test_a_rename_of_an_image_file_hides_the_old_name_and_adds_the_new(self):
        overlay.rename(self.machine, "/etc/motd", "motd.old")
        view = self.view()
        self.assertFalse(view.exists("/etc/motd"))
        self.assertEqual(view.get("/etc/motd.old").item.slug, "base-etc-motd")
        self.assertTrue(self.view(self.other).exists("/etc/motd"))

    def test_a_rename_of_an_own_file_renames_it(self):
        overlay.new_file(self.machine, "/", "a.txt")
        overlay.rename(self.machine, "/a.txt", "b.txt")
        self.assertEqual([entry.name for entry in self.view().children("/") if entry.name.endswith(".txt")], ["b.txt"])
        self.assertFalse(Placement.objects.filter(kind="whiteout").exists())

    def test_a_folder_of_the_image_cannot_be_renamed(self):
        with self.assertRaises(FileManagerError):
            overlay.rename(self.machine, "/bin", "binary")
        with self.assertRaises(FileManagerError):
            overlay.rename(self.machine, "/etc/hosts", "motd")                        # имя занято

    def test_the_data_marks_the_layers_and_who_owns_the_volume(self):
        overlay.override(self.machine, "/etc/hosts")
        overlay.new_file(self.machine, "/etc", "extra.txt")
        rows = {row["path"]: row for row in overlay.machine_data(self.machine)["rows"]}
        self.assertEqual((rows["/etc/hosts"]["mark"], rows["/etc/hosts"]["private"]), ("override", True))
        self.assertEqual((rows["/etc/extra.txt"]["mark"], rows["/etc/motd"]["mark"], rows["/etc/motd"]["private"]), ("added", "base", False))
        self.assertEqual(rows["/etc/motd"]["item"]["used"], 1)

    def test_a_machine_without_mounts_gets_a_root_volume_on_the_first_file(self):
        bare = Machine.objects.create(name="Bare", hostname="bare")
        overlay.new_file(bare, "/", "first.txt")
        self.assertEqual(MachineMount.objects.get(machine=bare).mount_path, "/")
        self.assertTrue(MachineView(bare, None).exists("/first.txt"))


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fmt("txt", ".txt")
        cls.boss = get_user_model().objects.create_superuser("boss", "b@example.com", "pw")
        cls.reader = get_user_model().objects.create_user("reader", password="pw", is_staff=True)
        cls.reader.user_permissions.add(*Permission.objects.filter(codename__in=("view_volume", "view_machine", "view_item")))

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.volume = Volume.objects.create(slug="v")
        self.machine = Machine.objects.create(name="M", hostname="m")
        self.client.force_login(self.boss)

    def op(self, name, body, target="volume"):
        url = reverse("admin:filesystem_volume_files_op", args=[self.volume.pk]) if target == "volume" else reverse("admin:machines_machine_files_op", args=[self.machine.pk])
        return self.client.post(url, json.dumps({"op": name, **body}), content_type="application/json")

    def test_the_operations_answer_with_json(self):
        made = self.op("new_file", {"parent": None, "name": "a.txt", "format": ""}).json()
        self.assertTrue(made["ok"])
        self.assertTrue(Item.objects.filter(pk=made["item"]).exists())
        self.assertEqual(self.op("new_folder", {"parent": None, "name": "docs"}).json(), {"ok": True})

    def test_a_refusal_is_a_400_with_a_text_for_the_author(self):
        self.op("new_folder", {"parent": None, "name": "docs"})
        response = self.op("new_folder", {"parent": None, "name": "docs"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["ok"], False)
        self.assertIn("уже есть", response.json()["error"])

    def test_bad_requests_are_refused(self):
        self.assertEqual(self.op("nope", {}).status_code, 400)
        self.assertEqual(self.op("delete", {"ids": "all"}).status_code, 400)
        url = reverse("admin:filesystem_volume_files_op", args=[self.volume.pk])
        self.assertEqual(self.client.post(url, "{broken", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, "[1]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_a_reader_may_look_but_not_change(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse("admin:filesystem_volume_files", args=[self.volume.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:filesystem_volume_files_data", args=[self.volume.pk])).status_code, 200)
        self.assertEqual(self.op("new_folder", {"parent": None, "name": "x"}).status_code, 403)
        page = self.client.get(reverse("admin:filesystem_volume_files", args=[self.volume.pk]))
        self.assertEqual(page.context["config"]["canChange"], False)

    def test_an_anonymous_visitor_is_sent_to_the_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("admin:filesystem_volume_files_data", args=[self.volume.pk])).status_code, 302)
        self.assertEqual(self.op("new_folder", {"parent": None, "name": "x"}).status_code, 302)

    def test_the_machine_operations(self):
        made = self.op("new_file", {"parent": "/", "name": "a.txt"}, "machine").json()
        self.assertTrue(made["ok"])
        self.assertEqual(self.op("new_folder", {"parent": "/", "name": "srv"}, "machine").json(), {"ok": True})
        self.assertEqual(self.op("rename", {"path": "/a.txt", "name": "b.txt"}, "machine").json(), {"ok": True})
        self.assertEqual(self.op("delete", {"path": "/b.txt"}, "machine").json(), {"ok": True})
        refused = self.op("restore", {"path": "/b.txt"}, "machine")
        self.assertEqual(refused.status_code, 400)

    def test_override_returns_the_object_to_open(self):
        base = Volume.objects.create(slug="base")
        put(base, "hosts", "x")
        MachineMount.objects.create(machine=self.machine, volume=base, mount_path="/")
        MachineMount.objects.create(machine=Machine.objects.create(name="O", hostname="o"), volume=base, mount_path="/")
        made = self.op("override", {"path": "/hosts"}, "machine").json()
        self.assertTrue(Item.objects.get(pk=made["item"]).slug.endswith("-m"))
