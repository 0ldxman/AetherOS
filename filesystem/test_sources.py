"""Что означает адрес содержимого файла (MachineFile.url): байты, которые читаются из него, и окно, которое открывает cnt.

Тесты держат поведение каждого вида адреса неизменным, пока код разбора переезжает в реестр источников.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from assets.models import Asset
from filesystem.content import resolve_content
from filesystem.models import MachineFile
from filesystem.rawview import build_raw, formats
from filesystem.sources import resolve_payload
from machines.models import Machine
from wiki.models import Document, Namespace


@override_settings(FORCE_SCRIPT_NAME=None)
class SourceKindTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        user = get_user_model().objects.create_user("marsh", password="x")
        space = Namespace.objects.create(name="Harbor")
        cls.doc = Document.objects.create(namespace=space, title="Report", type="rec", body="Manifest.", created_by=user, direct_link="rep")
        cls.closed = Document.objects.create(namespace=space, title="Closed", type="rec", body="Hidden.", access={"all": ["k1"]})
        cls.asset = Asset.objects.create(name="pic", file_id="1", size=11)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def make(self, path, url="", **extra):
        return MachineFile.objects.create(machine=self.machine, path=path, url=url, **extra)

    def payload(self, url, **extra):
        return resolve_payload(self.make(f"/p{MachineFile.objects.count()}", url, **extra), frozenset())

    def content(self, url, **extra):
        file = self.make(f"/c{MachineFile.objects.count()}", url, **extra)
        return resolve_content(file, None, file.path, "name")

    # --- байты ---------------------------------------------------------------------------------------------

    def test_a_file_without_an_address_has_no_payload(self):
        found = self.payload("")
        self.assertEqual((found.kind, found.body, found.locked), ("none", b"", False))

    def test_a_key_is_the_block_of_its_slug(self):
        from filesystem.rawview import keys

        found = self.payload("keys/alpha")
        self.assertEqual((found.kind, found.stamp), ("key", "key:alpha"))
        self.assertEqual(found.body, keys.armor("alpha", "store:alpha"))
        self.assertEqual(self.payload("keys/alpha/extra").kind, "none")

    def test_a_signature_is_the_block_under_a_hash(self):
        from filesystem.rawview import signatures

        found = self.payload("sig/alpha/abcd")
        self.assertEqual((found.kind, found.stamp), ("signature", "sig:alpha:abcd"))
        self.assertEqual(found.body, signatures.block("alpha", "abcd", "sig:alpha"))
        self.assertEqual(self.payload("sig/alpha").kind, "none")

    def test_a_wiki_record_by_path_and_by_direct_link(self):
        by_path = self.payload("apps/wiki/Harbor/Report")
        self.assertEqual((by_path.kind, by_path.fmt, by_path.locked, by_path.body), ("wiki", "rec", False, b"Manifest."))
        self.assertTrue(by_path.stamp.startswith(f"wiki:{self.doc.pk}:"))
        self.assertEqual(self.payload("apps/wiki/go/rep").body, b"Manifest.")
        self.assertTrue(self.payload("apps/wiki/Harbor/Closed").locked)
        self.assertEqual(self.payload("apps/wiki/Harbor/Missing").kind, "none")
        self.assertEqual(self.payload("apps/wiki").kind, "none")

    def test_an_asset_keeps_its_size_and_a_bad_id_is_nothing(self):
        found = self.payload(f"view/{self.asset.public_id}/")
        self.assertEqual((found.kind, found.size), ("asset", 11))
        self.assertEqual(self.payload("view/not-a-uuid/").kind, "none")

    def test_a_map_by_scene(self):
        from map.models import MapScene

        MapScene.objects.create(slug="harbor", title="Harbor", features=[])
        found = self.payload("apps/map/?scene=harbor")
        self.assertEqual((found.kind, found.fmt), ("map", "map"))
        self.assertEqual(self.payload("apps/map/?scene=nowhere").kind, "none")

    def test_a_mail_message_or_a_plain_app(self):
        from django.utils import timezone

        from mail.models import Message

        Message.objects.create(sender="a@b", recipients="*", subject="S", body="B", slug="m1", sent_at=timezone.now())
        found = self.payload("apps/mail/?message=m1")
        self.assertEqual((found.kind, found.locked), ("mail", True))                    # читателя нет
        for url in ("apps/mail/?message=missing", "apps/terminal/", "apps/"):
            app = self.payload(url)
            self.assertEqual((app.kind, app.stamp, app.meta["path"]), ("app", f"app:{url}", url))

    def test_a_leading_slash_and_an_unknown_prefix(self):
        self.assertEqual(self.payload("/keys/alpha").kind, "key")
        self.assertEqual(self.payload("other/place").kind, "none")

    def test_an_archive_has_no_address_but_files_below_it(self):
        archive = self.make("/pack.zip")
        self.make("/pack.zip/a.txt")
        found = resolve_payload(archive, frozenset())
        self.assertEqual(found.kind, "archive")
        self.assertTrue(found.stamp.startswith(f"archive:{archive.pk}:"))
        self.assertTrue(build_raw(archive).data.startswith(formats.magic("pak")))

    def test_a_slice_reads_a_window_of_its_source(self):
        from filesystem.models import FileSlice

        source = self.make("/src")
        holder = self.make("/.slices/x", "slice", delivered_only=True)
        FileSlice.objects.create(file=holder, source=source, state="", start=2, end=9)
        found = resolve_payload(holder, frozenset())
        self.assertEqual(found.kind, "slice")
        self.assertEqual(found.body, build_raw(source).data[2:9])
        self.assertEqual(resolve_payload(self.make("/.slices/y", "slice"), frozenset()).kind, "none")      # вырезки нет

    # --- окно cnt ------------------------------------------------------------------------------------------

    def test_the_window_of_each_address(self):
        self.assertEqual(self.content("apps/wiki/Harbor/Report").url, "/apps/wiki/Harbor/Report")
        self.assertEqual(self.content(f"view/{self.asset.public_id}/").url, f"/view/{self.asset.public_id}/")
        self.assertEqual(self.content("  apps/map/?scene=harbor  ").url, "/apps/map/?scene=harbor")

    def test_a_key_and_a_signature_open_as_text(self):
        for url in ("keys/alpha", "sig/alpha/abcd"):
            found = self.content(url)
            self.assertIn("/text/?path=%2Fc", found.url)

    def test_what_has_no_window(self):
        for url in ("", "   ", "slice"):
            self.assertEqual(self.content(url).error, "empty")

    def test_only_internal_addresses_open(self):
        for url in ("http://x/y", "//x/y", "/abs", "a\\b"):
            self.assertEqual(self.content(url).error, "bad_path")

    # --- реестр --------------------------------------------------------------------------------------------

    def test_the_first_kind_in_the_registry_owns_an_address(self):
        from filesystem.sources import Address, source_for

        expected = {
            "keys/a": "key", "sig/a/b": "signature", "slice": "slice", "view/x": "asset", "apps/wiki/A/B": "wiki",
            "apps/map/?scene=x": "map", "apps/mail/?message=m": "mail", "apps/other": "app", "other/place": None,
        }
        for url, name in expected.items():
            found = source_for(Address.parse(url))
            self.assertEqual(found.name if found else None, name, url)

    def test_a_new_kind_is_one_class_in_the_registry(self):
        from unittest import mock

        from filesystem import sources
        from filesystem.sources.base import Content, Payload, Source

        class Note(Source):
            name = "note"

            def accepts(self, address):
                return address.parts[:1] == ["note"]

            def payload(self, machine_file, address, keys, reader, viewer):
                return Payload(kind="note", layout="raw", body=b"hello", stamp="note:1")

            def shows(self, url):
                return url.startswith("note/")

            def window(self, url, path):
                return Content(url="/note-window/")

        with mock.patch.object(sources, "SOURCES", (Note(), *sources.SOURCES)):
            file = self.make("/n", "note/1")
            self.assertEqual(build_raw(file).data, b"hello")
            self.assertEqual(resolve_content(file, None, "/n", "n").url, "/note-window/")
