"""Что лежит в файле и какое окно открывает cnt: каждый вид содержимого по тому, что есть в объекте (или у самого игрока)."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from assets.models import Asset
from filesystem.content.window import resolve_content
from filesystem.machine_view import MachineView
from filesystem.models import FileFormat, Item
from filesystem.content.rawview import build_raw, formats
from filesystem.content.sources import payload_for, source_for
from filesystem.testing import embed_key, make_file
from machines.models import Machine


@override_settings(FORCE_SCRIPT_NAME=None)
class SourceKindTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        cls.user = get_user_model().objects.create_user("marsh", password="x")
        cls.asset = Asset.objects.create(name="pic", file_id="1", size=11)
        FileFormat.objects.update_or_create(name="rec", defaults={"extension": ".rec", "content": "text", "markup": True})

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def entry(self, path, **fields):
        made = make_file(self.machine, path, **fields)
        return MachineView(self.machine, self.user).get(made.path)

    def kind(self, path, **fields):
        return source_for(self.entry(path, **fields)).name

    def window(self, entry):
        return resolve_content(entry, entry.path, "name")

    # --- какой вид ---------------------------------------------------------------------------------------------

    def test_each_kind_is_chosen_by_what_the_object_holds(self):
        self.assertEqual(self.kind("/blank"), "blank")
        self.assertEqual(self.kind("/text", body="hello"), "text")
        self.assertEqual(self.kind("/key", key="alpha"), "key")
        self.assertEqual(self.kind("/link", url="apps/terminal/"), "link")
        self.assertEqual(self.kind("/asset", url=f"view/{self.asset.public_id}/"), "asset")

    def test_a_map_and_a_letter_come_from_their_records(self):
        from django.utils import timezone

        from mail.models import Message
        from map.models import MapScene

        MapScene.objects.create(slug="harbor", title="Harbor", features=[])
        Message.objects.create(sender="a@b", recipients="*", subject="S", body="B", slug="m1", sent_at=timezone.now())
        self.assertEqual(self.kind("/map", url="apps/map/?scene=harbor"), "map")
        self.assertEqual(self.kind("/mail", url="apps/mail/?message=m1"), "mail")

    def test_an_archive_is_an_object_with_members(self):
        made = make_file(self.machine, "/pack.zip/a.txt")
        entry = MachineView(self.machine, self.user).get("/pack.zip")
        self.assertTrue(entry.archive)
        self.assertEqual(source_for(entry).name, "archive")
        self.assertTrue(build_raw(entry, MachineView(self.machine, self.user)).data.startswith(formats.magic("pak")))

    def test_a_signature_and_a_slice_are_the_players_own_files(self):
        view = MachineView(self.machine, self.user)
        make_file(self.machine, "/home/keep")                                          # корень есть
        view.put_text("/home/a.sig", "-----BEGIN-----")
        view.put_data("/home/part.bin", b"\x00\x01\x02")
        for path, body in (("/home/a.sig", b"-----BEGIN-----"), ("/home/part.bin", b"\x00\x01\x02")):
            entry = view.get(path)
            self.assertEqual(source_for(entry).name, "own")
            self.assertEqual(build_raw(entry, view).data, body)

    # --- байты -------------------------------------------------------------------------------------------------

    def test_a_key_is_the_block_of_its_slug_when_it_has_no_text(self):
        from filesystem.content.rawview import keys

        data = payload_for(self.entry("/k", key="alpha")).body
        self.assertEqual(data, keys.armor("alpha", "store:alpha"))
        self.assertEqual(payload_for(self.entry("/k2", key="beta", body="own text")).body, b"own text")

    def test_a_text_object_is_a_container_of_its_format(self):
        data = build_raw(self.entry("/r", format="rec", body="Manifest.")).data
        self.assertTrue(data.startswith("§rec\n".encode()))
        self.assertIn(b"Manifest.", data)
        self.assertEqual(build_raw(self.entry("/plain", body="as is")).data, b"as is")      # без формата: текст как есть

    def test_the_edit_of_a_player_is_what_is_read(self):
        view = MachineView(self.machine, self.user)
        make_file(self.machine, "/home/n.txt", body="base")
        view.edit_text("/home/n.txt", "mine")
        self.assertEqual(build_raw(view.get("/home/n.txt"), view).data, b"mine")

    def test_the_same_object_gives_the_same_bytes_wherever_it_lies(self):
        first = self.entry("/a", size=700)
        view = MachineView(self.machine, self.user)
        view.copy("/a", "/b")
        self.assertEqual(build_raw(view.get("/b"), view).data, build_raw(first, view).data)
        self.assertEqual(len(build_raw(first).data), 700)

    def test_an_external_link_never_downloads_anything(self):
        entry = self.entry("/link", url="apps/x/", size=300)
        self.assertEqual(len(build_raw(entry).data), 300)                                # байты выдуманы, размер из поля

    def test_closed_text_gives_noise_of_the_same_length(self):
        entry = self.entry("/c", body="Secret text", format="rec")
        item = Item.objects.get(slug__startswith="c")
        item.access = "k1"
        item.save()
        entry = MachineView(self.machine, self.user).get("/c")
        closed, opened = build_raw(entry).data, build_raw(entry, keys=frozenset({"k1"})).data
        self.assertNotIn(b"Secret text", closed)
        self.assertIn(b"Secret text", opened)
        self.assertEqual(len(closed), len(opened))

    # --- окно cnt ----------------------------------------------------------------------------------------------

    def test_the_window_of_each_kind(self):
        self.assertEqual(self.window(self.entry("/asset", url=f"view/{self.asset.public_id}/")).url, f"/view/{self.asset.public_id}/")
        self.assertEqual(self.window(self.entry("/link", url="apps/x/")).url, "https://example.com/x")
        self.assertIn("/text/?path=%2Ftext", self.window(self.entry("/text", body="hello")).url)
        self.assertIn("/text/?path=%2Fkey", self.window(self.entry("/key", key="alpha")).url)
        self.assertEqual(self.window(self.entry("/blank")).error, "empty")

    def test_an_archive_has_no_window_and_a_closed_layer_locks(self):
        make_file(self.machine, "/pack.zip/a.txt")
        view = MachineView(self.machine, self.user)
        self.assertEqual(self.window(view.get("/pack.zip")).error, "empty")
        locked = self.entry("/door", state="> encrypted hunter2", body="x")
        self.assertEqual(self.window(locked).error, "locked")

    def test_a_new_kind_is_one_class_in_the_registry(self):
        from unittest import mock

        from filesystem.content import sources
        from filesystem.content.sources.base import Content, Payload, Source

        class Note(Source):
            name = "note"

            def accepts(self, entry):
                return entry.name == "note"

            def payload(self, entry, view, keys, reader, viewer):
                return Payload(kind="note", layout="raw", body=b"hello", stamp="note:1")

            def window(self, entry):
                return Content(url="/note-window/")

        with mock.patch.object(sources, "SOURCES", (Note(), *sources.SOURCES)):
            entry = self.entry("/note")
            self.assertEqual(build_raw(entry).data, b"hello")
            self.assertEqual(resolve_content(entry, "/note", "note").url, "/note-window/")
