"""Вид машины для игрока: тома, смонтированные на неё, и личный слой игрока поверх (docs/storage-spec.md, раздел 3)."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from filesystem.machine_view import DATA_LIMIT, MachineView, Occupied
from filesystem.models import FileFormat, Item, PlayerFile, Placement, Volume, VolumeInstance
from machines.models import Machine, MachineMount


def item(slug, body="", **fields):
    return Item.objects.create(slug=slug, name=slug, body=body, **fields)


def place(volume, path, thing=None, **fields):
    """Положить объект (или папку, если объекта нет) в том по пути, недостающие папки создаются."""
    parts = path.strip("/").split("/")
    parent = None
    for name in parts[:-1]:
        parent, _ = Placement.objects.get_or_create(volume=volume, parent=parent, name=name, defaults={"kind": "folder"})
    kind = fields.pop("kind", "item" if thing else "folder")
    return Placement.objects.create(volume=volume, parent=parent, name=parts[-1], kind=kind, item=thing, **fields)


def mount(machine, volume, point, order=0, mode="local", volume_path=""):
    return MachineMount.objects.create(machine=machine, volume=volume, mount_path=point, order=order, mode=mode, volume_path=volume_path)


class ViewCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ivan", password="x")
        cls.other = get_user_model().objects.create_user("petr", password="x")
        cls.machine = Machine.objects.create(name="A", hostname="a")
        cls.second = Machine.objects.create(name="B", hostname="b")

    def view(self, machine=None, user=None):
        return MachineView(machine or self.machine, user or self.user)


class BuildTests(ViewCase):
    def setUp(self):
        self.root = Volume.objects.create(slug="root")
        mount(self.machine, self.root, "/")
        self.hosts = item("hosts", "127.0.0.1")
        place(self.root, "etc/hosts", self.hosts)
        place(self.root, "home/ivan/notes.txt", item("notes", "hello"))
        place(self.root, "home/ivan/.secrets/alpha", item("alpha", "k", format="key"))

    def test_the_root_and_its_folders_exist(self):
        view = self.view()
        self.assertTrue(view.is_directory("/"))
        self.assertTrue(view.is_directory("/etc"))
        self.assertTrue(view.exists("/etc/hosts"))
        self.assertFalse(view.is_directory("/etc/hosts"))
        self.assertFalse(view.exists("/etc/nothing"))

    def test_a_listing_puts_folders_first_and_sorts_by_name(self):
        place(self.root, "zeta", item("z"))
        place(self.root, "Alpha", item("a2"))
        names = [entry.name for entry in self.view().children("/")]
        self.assertEqual(names, ["etc", "home", "Alpha", "zeta"])

    def test_the_object_of_a_file_is_reachable_with_its_body(self):
        found = self.view().get("/home/ivan/notes.txt")
        self.assertEqual((found.item.slug, found.body), ("notes", "hello"))

    def test_paths_are_cleaned(self):
        self.assertTrue(self.view().exists("etc//hosts/"))

    def test_a_folder_of_a_volume_mounts_at_a_point(self):
        machine = Machine.objects.create(name="C", hostname="c")
        mount(machine, self.root, "/mnt/home", volume_path="home/ivan")
        view = self.view(machine)
        self.assertTrue(view.exists("/mnt/home/notes.txt"))
        self.assertFalse(view.exists("/mnt/home/home"))
        self.assertTrue(view.is_directory("/mnt"))                     # недостающие папки до точки существуют

    def test_a_deeper_mount_hides_what_lay_under_it(self):
        library = Volume.objects.create(slug="library")
        place(library, "report", item("report"))
        place(self.root, "mnt/old", item("old"))
        mount(self.machine, library, "/mnt")
        view = self.view()
        self.assertTrue(view.exists("/mnt/report"))
        self.assertFalse(view.exists("/mnt/old"))

    def test_a_drive_is_a_mount_point(self):
        win = Machine.objects.create(name="W", hostname="w")
        disk = Volume.objects.create(slug="disk")
        place(disk, "Users/ivan/doc", item("doc"))
        mount(win, disk, "C:\\")
        view = self.view(win)
        self.assertTrue(view.exists("/C:/Users/ivan/doc"))
        self.assertEqual([entry.name for entry in view.children("/")], ["C:"])

    def test_a_volume_mounted_without_a_point_is_not_in_the_file_system(self):
        extra = Volume.objects.create(slug="extra")
        place(extra, "x", item("x"))
        mount(self.machine, extra, "")
        self.assertFalse(self.view().exists("/x"))


class StackTests(ViewCase):
    """Образ системы снизу, отличия машины сверху."""

    def setUp(self):
        self.base = Volume.objects.create(slug="aether-base")
        self.own = Volume.objects.create(slug="a-own")
        place(self.base, "etc/hosts", item("hosts", "base"))
        place(self.base, "etc/motd", item("motd", "hello"))
        place(self.base, "bin/ls", item("ls"))
        mount(self.machine, self.base, "/", order=0)
        mount(self.machine, self.own, "/", order=1)

    def test_an_upper_file_replaces_the_lower_one_of_the_same_path(self):
        place(self.own, "etc/hosts", item("hosts2", "own"))
        self.assertEqual(self.view().get("/etc/hosts").body, "own")

    def test_a_whiteout_hides_a_lower_file(self):
        place(self.own, "etc/motd", kind="whiteout")
        view = self.view()
        self.assertFalse(view.exists("/etc/motd"))
        self.assertTrue(view.exists("/etc/hosts"))

    def test_a_whiteout_of_a_folder_hides_everything_under_it(self):
        place(self.own, "bin", kind="whiteout")
        view = self.view()
        self.assertFalse(view.exists("/bin"))
        self.assertFalse(view.exists("/bin/ls"))

    def test_an_added_file_appears_next_to_the_lower_ones(self):
        place(self.own, "etc/extra", item("extra"))
        self.assertEqual([entry.name for entry in self.view().children("/etc")], ["extra", "hosts", "motd"])

    def test_the_lower_layer_alone_gives_the_plain_image(self):
        other = Machine.objects.create(name="C", hostname="c")
        mount(other, self.base, "/")
        self.assertEqual(self.view(other).get("/etc/hosts").body, "base")

    def test_the_order_decides_who_is_above(self):
        place(self.own, "etc/hosts", item("hosts2", "own"))
        MachineMount.objects.filter(volume=self.base).update(order=5)
        self.assertEqual(self.view().get("/etc/hosts").body, "base")

    def test_two_mounts_of_one_point_can_be_in_any_id_order(self):
        place(self.own, "etc/hosts", item("hosts2", "own"))
        self.assertEqual(MachineMount.objects.filter(machine=self.machine).count(), 2)
        self.assertEqual(self.view().get("/etc/hosts").layer.mount.volume.slug, "a-own")


class PropertyTests(ViewCase):
    def setUp(self):
        self.root = Volume.objects.create(slug="root")
        mount(self.machine, self.root, "/")

    def test_a_file_is_hidden_by_the_flag_or_by_a_dot_in_the_name(self):
        place(self.root, "a", item("a"), hidden=True)
        place(self.root, ".b", item("b"))
        place(self.root, "c", item("c"))
        view = self.view()
        self.assertTrue(view.get("/a").hidden)
        self.assertTrue(view.get("/.b").hidden)
        self.assertFalse(view.get("/c").hidden)

    def test_a_system_file_is_marked(self):
        place(self.root, "s", item("s"), system=True)
        self.assertTrue(self.view().get("/s").system)

    def test_layers_and_access_of_the_object_are_used_unless_the_place_changes_them(self):
        thing = item("t", state="encrypted", access="alpha")
        place(self.root, "inherit", thing)
        place(self.root, "replace", thing, state_mode="replace", state="binary", access_mode="replace", access="beta")
        place(self.root, "off", thing, state_mode="none", access_mode="none")
        view = self.view()
        self.assertEqual((view.get("/inherit").state, view.get("/inherit").access), ("encrypted", "alpha"))
        self.assertEqual((view.get("/replace").state, view.get("/replace").access), ("binary", "beta"))
        self.assertEqual((view.get("/off").state, view.get("/off").access), ("", {}))

    def test_the_conditions_are_the_volume_the_folders_and_the_file(self):
        self.root.access = "vol"
        self.root.save()
        place(self.root, "secret/inside/file", item("f", access="own"))
        Placement.objects.filter(name="secret").update(access="outer")
        Placement.objects.filter(name="inside").update(access={"any": ["x", "y"]})
        found = self.view().get("/secret/inside/file")
        self.assertEqual(found.conditions, ("vol", "outer", {"any": ["x", "y"]}, "own"))

    def test_a_folder_carries_its_own_condition(self):
        place(self.root, "d/file", item("f"))
        Placement.objects.filter(name="d").update(access="gate")
        self.assertEqual(self.view().get("/d").conditions, ("gate",))
        self.assertEqual(self.view().get("/d/file").conditions, ("gate",))


class PlayerLayerTests(ViewCase):
    def setUp(self):
        self.root = Volume.objects.create(slug="root")
        mount(self.machine, self.root, "/")
        self.note = item("note", "base text")
        place(self.root, "home/note.txt", self.note)
        place(self.root, "home/other.txt", item("other", "o"))

    def test_nothing_is_changed_in_the_base(self):
        view = self.view()
        view.remove("/home/note.txt")
        view.edit_text("/home/other.txt", "mine")
        self.assertEqual(Placement.objects.filter(volume=self.root).count(), 3)
        self.assertEqual(Item.objects.get(slug="other").body, "o")

    def test_a_deleted_file_is_gone_for_the_player_only(self):
        self.view().remove("/home/note.txt")
        self.assertFalse(self.view().exists("/home/note.txt"))
        self.assertTrue(self.view(user=self.other).exists("/home/note.txt"))

    def test_deleting_a_folder_removes_everything_under_it(self):
        count = self.view().remove("/home")
        self.assertEqual(count, 2)
        self.assertFalse(self.view().exists("/home"))
        self.assertFalse(self.view().exists("/home/other.txt"))

    def test_an_edit_keeps_the_object_and_changes_the_text_for_the_player(self):
        self.view().edit_text("/home/note.txt", "my text")
        found = self.view().get("/home/note.txt")
        self.assertEqual((found.item.slug, found.body, found.text_override), ("note", "my text", "my text"))
        self.assertEqual(self.view(user=self.other).get("/home/note.txt").body, "base text")

    def test_progress_over_layers_is_kept_per_player_without_changing_the_file(self):
        self.view().set_progress("/home/note.txt", "step1")
        found = self.view().get("/home/note.txt")
        self.assertEqual((found.progress, found.item.slug, found.body), ("step1", "note", "base text"))
        self.assertEqual(self.view(user=self.other).get("/home/note.txt").progress, "")

    def test_a_copy_has_its_own_progress_and_the_same_object(self):
        view = self.view()
        view.set_progress("/home/note.txt", "step1")
        view.copy("/home/note.txt", "/home/copy.txt")
        view = self.view()
        self.assertEqual((view.get("/home/copy.txt").item.slug, view.get("/home/copy.txt").progress), ("note", "step1"))
        view.set_progress("/home/copy.txt", "step2")
        self.assertEqual(self.view().get("/home/note.txt").progress, "step1")

    def test_a_move_leaves_nothing_behind(self):
        self.view().move("/home/note.txt", "/home/moved.txt")
        view = self.view()
        self.assertFalse(view.exists("/home/note.txt"))
        self.assertEqual(view.get("/home/moved.txt").body, "base text")

    def test_a_folder_moves_with_its_files(self):
        self.view().move("/home", "/stash")
        view = self.view()
        self.assertTrue(view.exists("/stash/note.txt"))
        self.assertTrue(view.exists("/stash/other.txt"))
        self.assertFalse(view.exists("/home"))

    def test_a_new_file_of_the_player_is_removed_without_a_trace(self):
        view = self.view()
        view.put_item("/home/new", self.note)
        self.assertTrue(view.exists("/home/new"))
        view.remove("/home/new")
        self.assertFalse(self.view().exists("/home/new"))
        self.assertFalse(PlayerFile.objects.filter(path="home/new").exists())

    def test_a_signature_is_a_file_with_its_own_text(self):
        self.view().put_text("/home/note.sig", "-----SIGNATURE-----")
        found = self.view().get("/home/note.sig")
        self.assertEqual((found.item, found.own_text, found.body), (None, "-----SIGNATURE-----", "-----SIGNATURE-----"))

    def test_a_slice_is_a_file_with_its_own_bytes(self):
        self.view().put_data("/home/part.bin", b"\x00\x01\x02")
        self.assertEqual(self.view().get("/home/part.bin").own_data, b"\x00\x01\x02")
        with self.assertRaises(ValueError):
            self.view().put_data("/home/big.bin", b"x" * (DATA_LIMIT + 1))

    def test_a_file_put_over_a_deleted_one_comes_back(self):
        view = self.view()
        view.remove("/home/note.txt")
        view.put_item("/home/note.txt", self.note)
        self.assertEqual(self.view().get("/home/note.txt").body, "base text")

    def test_a_lower_file_does_not_shine_through_a_deleted_override(self):
        base = Volume.objects.create(slug="base")
        place(base, "etc/hosts", item("lower", "lower"))
        MachineMount.objects.filter(volume=self.root).update(order=1)
        mount(self.machine, base, "/", order=0)
        view = self.view()
        view.put_text("/etc/hosts", "mine")                                 # перекрыл системный файл своим
        self.assertEqual(self.view().get("/etc/hosts").body, "mine")
        view.remove("/etc/hosts")
        self.assertFalse(self.view().exists("/etc/hosts"))

    def test_a_machine_without_a_root_gets_one_with_its_first_file_and_a_mount_point_is_never_written_over(self):
        machine = Machine.objects.create(name="C", hostname="c")
        library = Volume.objects.create(slug="lib")
        mount(machine, library, "/mnt")
        view = self.view(machine)
        view.put_text("/elsewhere", "x")                                              # корня не было: появился
        self.assertEqual(MachineMount.objects.get(machine=machine, mount_path="/").order, 0)
        self.assertEqual(self.view(machine).get("/elsewhere").own_text, "x")
        with self.assertRaises(Occupied):
            self.view(machine).put_text("/mnt", "x")

    def test_a_new_file_goes_to_the_topmost_layer_covering_the_path(self):
        base = Volume.objects.create(slug="base")
        MachineMount.objects.filter(volume=self.root).update(order=1)
        mount(self.machine, base, "/", order=0)
        view = self.view()
        view.put_text("/newfile", "x")
        instance = VolumeInstance.objects.get(player_files__path="newfile")
        self.assertEqual(instance.volume, self.root)


class InstanceTests(ViewCase):
    def setUp(self):
        self.shared = Volume.objects.create(slug="harbor")
        place(self.shared, "doc", item("doc", "base"))

    def test_a_remote_mount_shares_the_state_with_the_host(self):
        mount(self.machine, self.shared, "/mnt/h", mode="local")
        mount(self.second, self.shared, "/mnt/x", mode="remote")
        self.view(self.second).edit_text("/mnt/x/doc", "from B")
        self.assertEqual(self.view(self.machine).get("/mnt/h/doc").body, "from B")
        self.view(self.machine).remove("/mnt/h/doc")
        self.assertFalse(self.view(self.second).exists("/mnt/x/doc"))

    def test_two_local_mounts_are_independent(self):
        mount(self.machine, self.shared, "/mnt/h", mode="local")
        mount(self.second, self.shared, "/mnt/h", mode="local")
        self.view(self.machine).edit_text("/mnt/h/doc", "only A")
        self.assertEqual(self.view(self.second).get("/mnt/h/doc").body, "base")

    def test_the_layer_of_one_player_is_not_seen_by_another_on_a_shared_volume(self):
        mount(self.machine, self.shared, "/mnt/h", mode="local")
        mount(self.second, self.shared, "/mnt/x", mode="remote")
        self.view(self.second).edit_text("/mnt/x/doc", "ivan's")
        self.assertEqual(self.view(self.machine, self.other).get("/mnt/h/doc").body, "base")

    def test_without_a_host_a_remote_volume_is_one_external_instance(self):
        mount(self.machine, self.shared, "/mnt/x", mode="remote")
        mount(self.second, self.shared, "/mnt/y", mode="remote")
        self.view(self.machine).edit_text("/mnt/x/doc", "shared")
        self.assertEqual(self.view(self.second).get("/mnt/y/doc").body, "shared")
        self.assertIsNone(VolumeInstance.objects.get(volume=self.shared).host)


class KeysTests(ViewCase):
    def setUp(self):
        FileFormat.objects.update_or_create(name="key", defaults={"extension": ".key", "content": "text"})

    def test_keys_in_the_secrets_folder_are_held_including_those_from_a_mounted_volume(self):
        root = Volume.objects.create(slug="root")
        place(root, "home/ivan/.secrets/own", item("own", "k", format="key"))
        place(root, "home/ivan/readme", item("readme"))
        mount(self.machine, root, "/")
        server = Volume.objects.create(slug="keys")
        place(server, "from-server", item("shared", "k", format="key"))
        place(server, "not-a-key", item("plain"))
        mount(self.machine, server, "/home/ivan/.secrets", order=0)
        self.assertEqual(self.view().held_keys("/home/ivan/.secrets"), {"shared"})        # смонтированный том закрыл папку целиком

    def test_a_key_in_the_own_folder_is_held(self):
        root = Volume.objects.create(slug="root")
        place(root, "home/ivan/.secrets/own", item("own", "k", format="key"))
        place(root, "home/ivan/.secrets/text", item("text"))
        mount(self.machine, root, "/")
        self.assertEqual(self.view().held_keys("/home/ivan/.secrets"), {"own"})

    def test_a_key_received_by_the_player_is_held(self):
        root = Volume.objects.create(slug="root")
        mount(self.machine, root, "/")
        key = item("beta", "k", format="key")
        self.view().put_item("/home/ivan/.secrets/beta", key)
        self.assertEqual(self.view().held_keys("/home/ivan/.secrets"), {"beta"})

    def test_a_key_is_lost_when_the_volume_is_unmounted(self):
        server = Volume.objects.create(slug="keys")
        place(server, "k", item("shared", "k", format="key"))
        link = mount(self.machine, server, "/home/ivan/.secrets")
        self.assertEqual(self.view().held_keys("/home/ivan/.secrets"), {"shared"})
        link.delete()
        self.assertEqual(self.view().held_keys("/home/ivan/.secrets"), set())


class QueryTests(ViewCase):
    def build(self, files):
        root = Volume.objects.create(slug=f"root{files}")
        for index in range(files):
            place(root, f"d{index % 5}/f{index}", item(f"s{files}-{index}"))
        mount(self.machine, root, "/", order=files)
        PlayerFile.objects.all().delete()

    def count(self):
        view = self.view()
        with CaptureQueriesContext(connection) as queries:
            view.entries
            view.children("/")
        return len(queries)

    def test_the_number_of_queries_does_not_grow_with_the_number_of_files(self):
        self.build(5)
        small = self.count()
        self.build(60)
        large = self.count()
        self.assertEqual(small, large)
        self.assertLessEqual(large, 6)
