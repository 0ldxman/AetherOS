import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from assets.models import Asset
from dataclasses import replace
from types import SimpleNamespace

from filesystem.machine_view import MachineView
from filesystem.models import Item
from filesystem.testing import embed_key, make_file, make_page
from filesystem.rawview import build_raw, encodings, formats
from filesystem.size import file_size
from machines.models import Machine

BODY = "Cargo manifest altered.\n\nRef A-113."


class RawViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        user = get_user_model().objects.create_user("marsh", password="x")
        cls.doc = make_page("Harbor/Report", "rec", BODY, created_by=user)
        cls.scan_doc = make_page("Harbor/Page", "scan", BODY)
        cls.web_doc = make_page("Harbor/Site", "web", BODY)
        cls.word_doc = make_page("Harbor/Letter", "doc", BODY)
        cls.closed = make_page("Harbor/Closed", "rec", BODY, access={"all": ["k1"]})
        cls.asset = Asset.objects.create(name="pic", file_id="1", size=11)

    def setUp(self):
        from filesystem.rawview.registry import invalidate

        invalidate()                                  # откат транзакции теста не сбрасывает запомненный реестр
        self.addCleanup(invalidate)

    def make(self, path, url="", state="", **extra):
        return make_file(self.machine, path, url=url, state=state, **extra)

    def entry(self, made, progress=""):
        """Файл вида машины; progress: прогресс игрока по слоям (JSON), если нужен."""
        found = MachineView(self.machine, None).get(made.path)
        if progress:
            found = replace(found, player=SimpleNamespace(state=progress, content=None, data=None, pk=0))
        return found

    def raw(self, file, session_state="", keys=frozenset(), reader=None, viewer=None):
        return build_raw(self.entry(file, session_state), None, keys, reader, viewer)

    def test_widgets_leave_no_wiki_syntax_in_the_file(self):
        text = "Intro.\n\n::map scene=outer caption=\"Outer\"\n::\n\n::stamp SECRET tone=red\n"
        for kind, title, expected in (
            ("rec", "W1", b"[map: Outer]"),
            ("web", "W2", b'<figure data-kind="map"><figcaption>Outer</figcaption></figure>'),
            ("doc", "W3", b'{object map "Outer"}'),
            ("scan", "W4", b"Outer"),
        ):
            make_page(f"Harbor/{title}", kind, text)
            data = self.raw(self.make(f"/w/{title}", f"apps/wiki/Harbor/{title}")).data
            self.assertIn(expected, data)
            self.assertNotIn(b"::map", data)
            self.assertNotIn(b"::stamp", data)

    def test_closed_record_hides_every_view_of_its_body(self):
        Item.objects.filter(pk=self.closed.pk).update(body="Secret.\n\n::map scene=x caption=\"Hidden place\"\n::\n")
        data = self.raw(self.make("/cl", "apps/wiki/Harbor/Closed")).data
        self.assertNotIn(b"Hidden place", data)
        self.assertNotIn(b"Secret.", data)

    def test_a_wiki_record_becomes_the_container_of_its_type_with_the_real_text(self):
        data = self.raw(self.make("/a", "apps/wiki/Harbor/Report")).data
        self.assertTrue(data.startswith("§rec\nwho: marsh\n".encode()))
        self.assertIn(BODY.encode(), data)

        scan = self.raw(self.make("/b", "apps/wiki/Harbor/Page")).data
        self.assertTrue(scan.startswith(formats.magic("scan")))
        self.assertIn(b"OCR " + BODY.encode(), scan[:-5])

        snp = self.raw(self.make("/c", "apps/wiki/Harbor/Site")).data
        self.assertTrue(snp.startswith(b"<!--SNP\nsrc:  file://Site"))
        self.assertIn(b"<!--@seal ", snp)

        doc = self.raw(self.make("/d", "apps/wiki/Harbor/Letter")).data
        self.assertTrue(doc.startswith(formats.magic("doc") + b"\x00\x03body"))
        self.assertIn(BODY.encode(), doc)

    def test_the_disguised_layer_wins_over_the_type_of_the_record(self):
        raw = self.raw(self.make("/a", "apps/wiki/Harbor/Report", "> disguised scan"))
        self.assertEqual(raw.format, "scan")
        self.assertTrue(raw.data.startswith(formats.magic("scan")))
        self.assertIn(BODY.encode(), raw.data)                                   # настоящий текст внутри, в блоке OCR

    def test_a_record_closed_by_keys_gives_noise_of_the_same_length(self):
        file = self.make("/a", "apps/wiki/Harbor/Closed")
        closed, opened = self.raw(file), self.raw(file, keys=frozenset({"k1"}))
        self.assertNotIn(b"Cargo", closed.data)
        self.assertIn(BODY.encode(), opened.data)
        self.assertEqual(closed.size, opened.size)

    def test_layers_change_the_view(self):
        url = "apps/wiki/Harbor/Report"
        plain = self.raw(self.make("/p", url)).data

        based = self.raw(self.make("/b", url, "> binary base64")).data
        self.assertEqual(based, encodings.wrap_base64(plain))
        self.assertNotIn(b"Cargo", based)                                        # закодировано

        secret = self.raw(self.make("/s", url, "> encrypted hunter2")).data
        self.assertEqual(len(secret), len(plain))
        self.assertNotIn(b"Cargo", secret)

        wide = self.raw(self.make("/w", url, "> binary utf16")).data
        self.assertIn("Cargo".encode("utf-16-le"), wide)
        self.assertNotIn(b"Cargo", wide)

        hurt = self.raw(self.make("/h", url, "> damaged")).data
        self.assertEqual(len(hurt), len(plain))
        self.assertNotEqual(hurt, plain)

    def test_a_removed_layer_stops_changing_the_view(self):
        from filesystem.states.stack import Progress, canonical_hash

        file = self.make("/a", "apps/wiki/Harbor/Report", "> binary base64")
        done = Progress(canonical_hash=canonical_hash("> binary base64"), removed=1).dump()
        self.assertIn(b"Cargo", self.raw(file, done).data)

    def test_an_asset_gives_its_real_bytes_and_a_wrapper_only_under_a_layer(self):
        url = f"view/{self.asset.public_id}/"
        read = lambda asset: b"hello world"
        self.assertEqual(self.raw(self.make("/a", url), reader=read).data, b"hello world")

        wrapped = self.raw(self.make("/b", url, "> disguised scan"), reader=read).data
        self.assertTrue(wrapped.startswith(formats.magic("scan")))
        self.assertIn(b"IMG hello world"[4:], wrapped)                         # картинка (байты ассета) лежит в блоке IMG

        # Nextcloud недоступен: вместо падения шум нужного размера
        def broken(asset):
            raise OSError("down")
        self.assertEqual(self.raw(self.make("/c", url), reader=broken).size, 11)

    def test_files_that_lead_nowhere_are_noise_with_a_stable_size(self):
        file = self.make("/a", "", size=700)
        self.assertEqual(self.raw(file).size, 700)
        self.assertEqual(self.raw(file).data, self.raw(file).data)
        other = self.make("/b", "")
        self.assertEqual(self.raw(other).size, file_size(self.entry(other)))
        self.assertEqual(self.raw(self.make("/c", "", "> disguised pdf")).data[:5], b"%PDF-")   # формат виден и у шума

    def test_a_map_and_an_unknown_app(self):
        from map.models import MapScene

        MapScene.objects.create(slug="harbor", title="Harbor", features=[{"type": "marker", "key": "k9", "title": "secret"}])
        data = self.raw(self.make("/m", "apps/map/?scene=harbor")).data
        self.assertIn(b'"title": "Harbor"', data)
        self.assertNotIn(b"secret", data)                                         # пометка за ключом не утекает

    def test_the_size_of_an_asset_without_layers_needs_no_download(self):
        file = self.make("/a", f"view/{self.asset.public_id}/")
        self.assertEqual(file_size(self.entry(file)), 11)                                     # Asset.size, без чтения из Nextcloud

    def test_broken_layer_text_does_not_break_the_view(self):
        file = self.make("/a", "", "> binary")                                    # у слоя нет обязательной кодировки
        self.assertTrue(self.raw(file).size > 0)

    def test_known_encodings(self):
        self.assertEqual(encodings.encode("rot13", b"Harbor"), b"Uneobe")
        self.assertEqual(encodings.encode("hex", b"Hi"), b"48 69")
        self.assertEqual(encodings.encode("morse", b"sos"), b"... --- ...")
        self.assertTrue(encodings.encode("gzip", b"x").startswith(b"\x1f\x8b"))
        self.assertEqual(encodings.encode("nothing", b"x"), b"x")

    def test_formats_come_from_the_registry_and_a_new_one_works_at_once(self):
        from filesystem.models import FileFormat, FormatPart

        FileFormat.objects.create(name="ledger", kind="package", magic="4c 47 52 00", extension=".led")
        self.assertNotIn(b"Cargo", self.raw(self.make("/a", "apps/wiki/Harbor/Report", "> disguised ledger")).data[:4])
        FormatPart.objects.create(format=FileFormat.objects.get(name="ledger"), name="body", source="body")
        data = self.raw(self.make("/b", "apps/wiki/Harbor/Report", "> disguised ledger")).data     # правка видна сразу, без перезапуска
        self.assertTrue(data.startswith(b"LGR\x00\x00\x01body"))
        self.assertIn(BODY.encode(), data)

    def test_the_type_of_a_wiki_record_finds_its_format_by_extension(self):
        from filesystem.models import FileFormat

        FileFormat.objects.filter(name="rec").update(template="REC:{body}")
        from filesystem.rawview.registry import invalidate

        invalidate()
        self.assertTrue(self.raw(self.make("/a", "apps/wiki/Harbor/Report")).data.startswith(b"REC:Cargo"))

    def test_a_new_encoding_is_a_registry_entry(self):
        from filesystem.models import FileEncoding

        FileEncoding.objects.create(name="shift3", kind="rot", param="3")
        FileEncoding.objects.create(name="mask", kind="xor", param="0x5a")
        self.assertEqual(encodings.encode("shift3", b"Harbor"), b"Kdueru")
        self.assertEqual(encodings.encode("mask", b"A"), bytes([0x41 ^ 0x5A]))
        self.assertEqual(encodings.encode("ebcdic", "A".encode()), "A".encode("cp500"))

    def test_viewer_formats_list_the_registry(self):
        import json

        from filesystem.rawview import viewer_formats

        listed = {item["name"]: item for item in json.loads(viewer_formats())}
        self.assertEqual(listed["SCAN image + OCR text"]["bytes"][:5], [0x9E, 0x53, 0x43, 0x41, 0x4E])
        self.assertEqual(listed["SNP page snapshot"]["prefix"], "<!--SNP\nsrc:  ")
        self.assertEqual(listed["REC record"]["prefix"], "\u00a7rec\nwho: ")

    def test_a_mail_message_becomes_the_text_of_a_letter(self):
        from django.utils import timezone

        from mail.models import Message

        Message.objects.create(sender="cmd@neweden.mail", recipients="*", subject="Cargo", body="Shipment 7 left.", slug="cargo",
                               sent_at=timezone.now())
        locked = self.raw(self.make("/m", "apps/mail/?message=cargo"))               # читателя нет: письмо закрыто шумом
        self.assertTrue(locked.data.startswith(b"From: cmd@neweden.mail\nTo: *\nSubject: Cargo"))
        self.assertNotIn(b"Shipment 7", locked.data)

        class Reader:                                                              # читатель, которому письмо видно
            address, keys, profile, user, session_key = "ivan@aether-main", frozenset(), None, None, ""

        from unittest import mock

        with mock.patch("mail.access.visible_messages", return_value=[object()]):
            opened = self.raw(self.make("/n", "apps/mail/?message=cargo"), viewer=Reader())
        self.assertIn(b"Shipment 7 left.", opened.data)
        self.assertEqual(opened.size, locked.size)                                  # размер не зависит от доступа



@override_settings(FORCE_SCRIPT_NAME=None)
class RegistryAdminTests(TestCase):
    """Админка реестра форматов и кодировок: страницы открываются, ошибки видны сразу при сохранении."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser("boss", "b@example.com", "pw")

    def setUp(self):
        from filesystem.rawview.registry import invalidate

        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        invalidate()
        self.addCleanup(invalidate)
        self.client.force_login(self.staff)

    def test_the_pages_open_and_the_seeded_formats_are_there(self):
        from django.urls import reverse

        for name in ("fileformat", "fileencoding"):
            page = self.client.get(reverse(f"admin:filesystem_{name}_changelist"))
            self.assertEqual(page.status_code, 200)
        self.assertContains(self.client.get(reverse("admin:filesystem_fileformat_changelist")), "scan")
        self.assertContains(self.client.get(reverse("admin:filesystem_fileencoding_changelist")), "utf16")
        from filesystem.models import FileFormat

        scan = FileFormat.objects.get(name="scan")
        self.assertEqual(self.client.get(reverse("admin:filesystem_fileformat_change", args=[scan.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:filesystem_fileformat_add")).status_code, 200)

    def post_format(self, **fields):
        from django.urls import reverse

        data = {"name": "x", "title": "", "extension": "", "kind": "signature", "content": "text_asset", "magic": "", "template": "",
                "parts-TOTAL_FORMS": "0", "parts-INITIAL_FORMS": "0", "parts-MIN_NUM_FORMS": "0", "parts-MAX_NUM_FORMS": "1000"}
        data.update(fields)
        return self.client.post(reverse("admin:filesystem_fileformat_add"), data)

    def test_a_format_is_checked_when_saved(self):
        from filesystem.models import FileFormat

        self.assertContains(self.post_format(magic=""), "нужна сигнатура")
        self.assertContains(self.post_format(magic="zz 12"), "только hex-байты")
        self.assertContains(self.post_format(kind="text", template=""), "нужен шаблон")
        self.assertContains(self.post_format(kind="text", template="a {nothing} b"), "нет подстановки")
        self.assertContains(self.post_format(kind="text", template="a {body"), "не разбирается")
        self.assertContains(self.post_format(kind="chunks", magic="01 02"), "хотя бы одна часть")
        self.assertFalse(FileFormat.objects.filter(name="x").exists())

        done = self.post_format(magic="01 02 03")
        self.assertEqual(done.status_code, 302)
        self.assertTrue(FileFormat.objects.filter(name="x", magic="01 02 03").exists())

    def test_the_parts_of_a_chunked_format_are_checked(self):
        data = {"parts-TOTAL_FORMS": "1", "parts-0-order": "0", "parts-0-name": "TOOLONG", "parts-0-source": "body",
                "parts-0-value": ""}
        self.assertContains(self.post_format(kind="chunks", magic="01 02", **data), "ровно 4 символа")
        data.update({"parts-0-name": "DATA", "parts-0-source": "hex", "parts-0-value": "nothex"})
        self.assertContains(self.post_format(kind="chunks", magic="01 02", **data), "только hex-байты")
        data.update({"parts-0-source": "body", "parts-0-value": ""})
        self.assertEqual(self.post_format(kind="chunks", magic="01 02", **data).status_code, 302)

    def test_an_encoding_is_checked_when_saved(self):
        from django.urls import reverse

        add = reverse("admin:filesystem_fileencoding_add")
        self.assertContains(self.client.post(add, {"name": "bad", "title": "", "kind": "codec", "param": "no-such-codec"}), "нет такого кодека")
        self.assertContains(self.client.post(add, {"name": "bad", "title": "", "kind": "rot", "param": "many"}), "должен быть числом")
        self.assertEqual(self.client.post(add, {"name": "ok", "title": "", "kind": "reverse", "param": ""}).status_code, 302)

    def test_an_alias_cannot_take_a_name_or_extension_of_another_format(self):
        from filesystem.models import FileFormat

        self.assertContains(self.post_format(magic="01 02", aliases="jpg"), "уже занят форматом jpg")
        self.assertContains(self.post_format(magic="01 02", aliases="jpeg"), "уже занят форматом jpg")
        self.assertContains(self.post_format(magic="01 02", aliases=".pdf"), "уже занят форматом pdf")
        self.assertEqual(self.post_format(magic="01 02", aliases="xx, yy").status_code, 302)
        self.assertEqual(FileFormat.objects.get(name="x").aliases, "xx, yy")

    def test_a_zip_format_needs_parts(self):
        self.assertContains(self.post_format(kind="zip", magic=""), "хотя бы одна часть")


class MoreFormatsTests(TestCase):
    """Форматы и кодировки, заведённые вторым набором: псевдонимы, zip-контейнеры, текстовые шаблоны, новые кодировки."""

    SAMPLE = "Cargo <manifest> & \"altered\".\nRef A-113. Груз {7}."

    def setUp(self):
        from filesystem.rawview.registry import invalidate

        invalidate()
        self.addCleanup(invalidate)

    def test_aliases_find_the_same_format(self):
        from filesystem.rawview import registry

        self.assertEqual(registry.format_named("jpeg").name, "jpg")
        self.assertEqual(registry.format_named(".JPE").name, "jpg")
        self.assertEqual(registry.format_for_extension(".tif").name, "tiff")
        self.assertEqual(registry.format_for_extension(".htm").name, "html")
        self.assertEqual(registry.format_for_extension(".jpg").name, "jpg")
        self.assertIsNone(registry.format_named("nonsense"))

    def test_the_disguised_layer_accepts_an_alias_of_its_format(self):
        from filesystem.states.layers import Disguised

        self.assertEqual(Disguised.check_unlock({"format": "jpg"}, {"format": "jpeg"}), ())
        self.assertEqual(Disguised.check_unlock({"format": "jpeg"}, {"format": ".JPG"}), ())
        self.assertEqual(Disguised.check_unlock({"format": "jpg"}, {"format": "png"}), ("format",))

    def test_office_and_book_formats_are_real_zip_files_with_the_text_inside(self):
        import io
        import zipfile

        for name, inner in (("docx", "word/document.xml"), ("xlsx", "xl/worksheets/sheet1.xml"), ("pptx", "ppt/slides/slide1.xml"),
                            ("odt", "content.xml"), ("epub", "OEBPS/text.xhtml")):
            data = formats.build(name, self.SAMPLE.encode(), {"title": "T", "who": "w"})
            archive = zipfile.ZipFile(io.BytesIO(data))
            self.assertIsNone(archive.testzip(), name)
            self.assertIn(inner, archive.namelist())
            self.assertIn("Груз", archive.read(inner).decode(), name)
        self.assertIn("Cargo &lt;manifest&gt; &amp;", zipfile.ZipFile(io.BytesIO(formats.build("docx", self.SAMPLE.encode()))).read("word/document.xml").decode())
        for name in ("odt", "epub"):
            self.assertEqual(zipfile.ZipFile(io.BytesIO(formats.build(name, b"x"))).namelist()[0], "mimetype")   # mimetype первым
        self.assertTrue(formats.build("docx", b"x").startswith(b"PK\x03\x04"))

    def test_text_formats_carry_the_text_in_their_own_escaping(self):
        import json

        self.assertEqual(json.loads(formats.build("json", self.SAMPLE.encode(), {"title": "T"}))["text"], self.SAMPLE)
        self.assertIn('"Cargo <manifest> & ""altered"".', formats.build("csv", self.SAMPLE.encode()).decode())
        self.assertIn("\\u1043?", formats.build("rtf", self.SAMPLE.encode()).decode())              # Г как \u1043?
        self.assertIn("&amp;", formats.build("svg", self.SAMPLE.encode()).decode())
        self.assertTrue(formats.build("pem", self.SAMPLE.encode()).startswith(b"-----BEGIN CERTIFICATE-----\n"))
        self.assertTrue(formats.build("sh", b"x", {"title": "T"}).startswith(b"#!/bin/sh\n"))
        self.assertTrue(formats.build("map", b"{}", {"ref": "outer"}).startswith("§map\nscene: outer".encode()))
        for name in ("html", "xml", "txt", "md", "log", "eml", "pgp", "ssh", "py"):
            self.assertTrue(formats.build(name, self.SAMPLE.encode(), {"title": "T"}), name)

    def test_signature_formats_start_with_their_magic(self):
        for name, start in (("bmp", b"BM"), ("tiff", b"II*\x00"), ("webp", b"RIFF"), ("ogg", b"OggS"), ("flac", b"fLaC"),
                            ("mkv", b"\x1a\x45\xdf\xa3"), ("7z", b"7z\xbc\xaf"), ("rar", b"Rar!"), ("exe", b"MZ"),
                            ("elf", b"\x7fELF"), ("class", b"\xca\xfe\xba\xbe"), ("sqlite", b"SQLite format 3\x00"),
                            ("kdbx", b"\x03\xd9\xa2\x9a")):
            self.assertTrue(formats.build(name, b"tail").startswith(start), name)

    def test_a_locked_source_hides_every_escaped_form_of_the_body(self):
        found = formats.variants(b"a<b&c", {})
        self.assertIn(b"a&lt;b&amp;c", found)
        self.assertIn(b"YTxiJmM=", found)

    def test_every_new_encoding_changes_the_bytes_and_the_reversible_ones_come_back(self):
        import base64
        import binascii
        from urllib.parse import unquote_to_bytes

        data = "Cargo Ref A-113. Груз ~{}".encode()
        for name in ("utf32", "cp1251", "koi8r", "cp866", "utf7", "xor", "reverse", "base32", "rot47", "bin", "dec", "oct",
                     "url", "base85", "uu", "atbash"):
            self.assertTrue(encodings.known(name), name)
            self.assertTrue(encodings.encode(name, data), name)
        self.assertEqual(encodings.encode("rot47", encodings.encode("rot47", data)), data)
        self.assertEqual(encodings.encode("atbash", encodings.encode("atbash", b"Cargo Ref")), b"Cargo Ref")
        self.assertEqual(encodings.encode("xor", encodings.encode("xor", data)), data)
        self.assertEqual(encodings.encode("reverse", data)[::-1], data)
        self.assertEqual(encodings.encode("cp1251", data).decode("cp1251"), data.decode())
        self.assertEqual(encodings.encode("koi8r", data).decode("koi8-r"), data.decode())
        self.assertEqual(encodings.encode("utf7", data).decode("utf-7"), data.decode())
        self.assertEqual(bytes(int(x, 2) for x in encodings.encode("bin", data).split()), data)
        self.assertEqual(bytes(int(x) for x in encodings.encode("dec", data).split()), data)
        self.assertEqual(bytes(int(x, 8) for x in encodings.encode("oct", data).split()), data)
        self.assertEqual(unquote_to_bytes(encodings.encode("url", data).decode()), data)
        self.assertEqual(base64.b85decode(encodings.encode("base85", data)), data)
        self.assertEqual(base64.b32decode(encodings.encode("base32", data)), data)
        lines = encodings.encode("uu", data).decode().splitlines()
        self.assertEqual(lines[0], "begin 644 data")
        self.assertEqual(b"".join(binascii.a2b_uu(line) for line in lines[1:-2]), data)


def _jpeg():
    def seg(marker, payload):
        return b"\xff" + bytes([marker]) + (len(payload) + 2).to_bytes(2, "big") + payload

    return b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00") + seg(0xDB, bytes(65)) + \
        seg(0xDA, bytes(10)) + b"\x12\x34\x56" * 40 + b"\xff\xd9"


def _png():
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(52))) + chunk(b"IEND", b"")


class KeyBlockTests(TestCase):
    """Ключи файла лежат в его байтах блоками в стиле PEM, каждый в своём месте, и контейнер остаётся целым."""

    SLUGS = ["secret_a", "secret_b"]

    def setUp(self):
        from filesystem.rawview.registry import invalidate

        invalidate()
        self.addCleanup(invalidate)

    def found(self, data):
        from filesystem.rawview import keys

        return [(m.start(), keys.parse(data, m.start())) for m in __import__("re").finditer(rb"-----BEGIN ACCESS KEY-----", data)]

    def test_a_block_is_pem_like_with_the_keyname_in_the_header_and_has_no_system_name(self):
        from filesystem.rawview import keys

        block = keys.armor("secret_a", "seed")
        text = block.decode()
        self.assertTrue(text.startswith("-----BEGIN ACCESS KEY-----\nKeyname: secret_a\n\n"))
        self.assertTrue(text.endswith("-----END ACCESS KEY-----\n"))
        self.assertNotIn("aether", text.lower())
        self.assertEqual(block, keys.armor("secret_a", "seed"))                      # стабильно
        self.assertNotEqual(block, keys.armor("secret_a", "other"))
        self.assertEqual(keys.parse(b"xx" + block, 2), "secret_a")
        self.assertIsNone(keys.parse(b"xx" + block, 1))                              # только с начала блока

    def test_jpeg_keeps_its_structure_and_each_key_lies_in_a_comment_segment(self):
        from filesystem.rawview import keys

        data = keys.embed(_jpeg(), self.SLUGS, "s", real=True)
        self.assertEqual([slug for _, slug in self.found(data)], self.SLUGS if self.found(data)[0][1] == "secret_a" else self.SLUGS[::-1])
        pos, comments = 2, 0
        while data[pos + 1] != 0xDA:                                                    # сегменты до начала изображения целы
            self.assertEqual(data[pos], 0xFF)
            comments += data[pos + 1] == 0xFE
            pos += 2 + int.from_bytes(data[pos + 2:pos + 4], "big")
        self.assertEqual(comments, 2)
        self.assertTrue(data.endswith(b"\xff\xd9"))

    def test_png_chunks_keep_valid_checksums(self):
        import struct
        import zlib

        from filesystem.rawview import keys

        data = keys.embed(_png(), self.SLUGS, "s", real=True)
        pos, kinds = 8, []
        while pos < len(data):
            size = struct.unpack(">I", data[pos:pos + 4])[0]
            kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + size]
            self.assertEqual(struct.unpack(">I", data[pos + 8 + size:pos + 12 + size])[0], zlib.crc32(kind + body) & 0xFFFFFFFF)
            kinds.append(kind)
            pos += 12 + size
        self.assertEqual((kinds[0], kinds[-1], kinds.count(b"tEXt")), (b"IHDR", b"IEND", 2))

    def test_a_zip_gets_an_archive_comment_and_pdf_comments_after_eof(self):
        import io
        import zipfile

        from filesystem.rawview import keys

        archive = zipfile.ZipFile(io.BytesIO(keys.embed(formats.build("docx", b"text"), self.SLUGS, "s")))
        self.assertIsNone(archive.testzip())
        self.assertIn(b"Keyname: secret_a", archive.comment)
        pdf = keys.embed(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n", self.SLUGS, "s", real=True)
        self.assertTrue(pdf.startswith(b"%PDF-1.7\n1 0 obj"))
        self.assertIn(b"%Keyname: secret_b", pdf)

    def test_own_containers_take_the_key_as_their_own_part(self):
        from filesystem.rawview import keys

        scan = keys.embed(formats.build("scan", b"text", seed="x"), ["secret_a"], "s")
        self.assertIn(b"KEY -----BEGIN ACCESS KEY-----", scan)
        doc = keys.embed(formats.build("doc", b"text"), ["secret_a"], "s")
        self.assertIn(b"key.pem", doc)
        self.assertIn(b"Keyname: secret_a", doc)
        html = keys.embed(formats.build("snp", b"text", {"title": "T"}), ["secret_a"], "s").decode()
        self.assertIn("<!--\n-----BEGIN ACCESS KEY-----", html)
        self.assertLess(html.index("-----BEGIN"), html.index("</body>"))
        rec = keys.embed(formats.build("rec", b"text\n\nmore\n\nlines\n"), ["secret_a"], "s").decode()
        self.assertIn("-----BEGIN ACCESS KEY-----\nKeyname: secret_a", rec)
        self.assertTrue(rec.startswith("\u00a7rec\nwho:"))                               # шапка формата на месте
        spread = keys.embed(formats.build("snp", b"a\n\nb\n\nc\n", {"title": "T"}), ["k_one", "k_two", "k_three"], "s").decode()
        self.assertEqual(spread.count("-----BEGIN ACCESS KEY-----"), 3)

    def test_unknown_data_gets_the_block_at_the_end_when_real_and_inside_when_noise(self):
        from filesystem.rawview import keys
        from filesystem.rawview.noise import noise

        real = b"\x00\x01binary-asset" * 20
        self.assertTrue(keys.embed(real, ["secret_a"], "s", real=True).startswith(real))
        fake = noise("n", 2000)
        inside = keys.embed(fake, ["secret_a"], "s")
        at = inside.index(b"-----BEGIN")
        self.assertTrue(500 <= at <= 1500)

    def entry(self, machine, made):
        return MachineView(machine, None).get(made.path)

    def test_a_key_is_in_a_file_only_through_its_item_key_and_layers_hide_it(self):
        machine = Machine.objects.create(name="M", hostname="m1")
        make_page("Space/Note", "rec", BODY)
        plain = make_file(machine, "/a", url="apps/wiki/Space/Note")
        locked = make_file(machine, "/b", url="apps/wiki/Space/Note", state="> encrypted pw")
        for made in (plain, locked):
            for slug in self.SLUGS:
                embed_key(made.item, slug)
        data = build_raw(self.entry(machine, plain)).data
        self.assertEqual(sorted(slug for _, slug in self.found(data)), self.SLUGS)
        self.assertEqual(self.found(build_raw(self.entry(machine, locked)).data), [])             # зашифровано: ключей не видно
        free = make_file(machine, "/c", url="apps/wiki/Space/Note")
        self.assertEqual(self.found(build_raw(self.entry(machine, free)).data), [])
        self.assertEqual(file_size(self.entry(machine, plain)), len(data))                         # размер учитывает блоки

    def test_a_closed_source_shows_noise_in_place_of_the_blocks(self):
        machine = Machine.objects.create(name="M", hostname="m2")
        make_page("Space2/Hidden", "rec", BODY, access={"all": ["zz"]})
        made = make_file(machine, "/h", url="apps/wiki/Space2/Hidden")
        embed_key(made.item, "secret_a")
        entry = self.entry(machine, made)
        closed = build_raw(entry).data
        opened = build_raw(entry, keys=frozenset({"zz"})).data
        self.assertNotIn(b"secret_a", closed)
        self.assertIn(b"Keyname: secret_a", opened)
        self.assertEqual(len(closed), len(opened))


class SignatureBlockTests(TestCase):
    """Блоки подписей: хеш по содержимому, любая правка ломает, шум при закрытом источнике."""

    def test_a_block_checks_against_the_content_it_was_made_for(self):
        from filesystem.rawview import signatures

        content = b"Cargo manifest altered.\n"
        data = signatures.embed(content, [("director", None, True), ("other", None, False)], "s")
        found = signatures.find(data)
        self.assertEqual([item["slug"] for item in found], ["director", "other"])
        self.assertEqual(data[:found[0]["start"]], content)
        self.assertTrue(signatures.check(found[0], content))
        self.assertFalse(signatures.check(found[0], content + b"x"))                       # правка ломает
        self.assertFalse(signatures.check(found[1], content))                              # подделка
        self.assertEqual(data, signatures.embed(content, [("director", None, True), ("other", None, False)], "s"))

    def test_a_closed_source_shows_noise_of_the_same_length_and_no_blocks(self):
        from filesystem.rawview import signatures

        open_data = signatures.embed(b"text\n", [("director", None, True)], "s")
        closed = signatures.embed(b"text\n", [("director", None, True)], "s", locked=True)
        self.assertEqual(len(open_data), len(closed))
        self.assertEqual(signatures.find(closed), [])

    def test_base64_is_an_encoding_with_variants_and_the_old_layer_is_gone(self):
        import base64

        data = b"Cargo manifest altered. " * 6
        wrapped = encodings.encode("base64", data)
        self.assertTrue(wrapped.endswith(b"\n"))
        self.assertTrue(all(len(line) <= 76 for line in wrapped.splitlines()))
        self.assertEqual(base64.b64decode(wrapped), data)
        url = encodings.encode("base64url", b"\xfb\xff\xfe?>")
        self.assertNotIn(b"=", url)
        self.assertNotIn(b"+", url)
        self.assertNotIn(b"/", url)
        self.assertNotIn(b"\n", url)
        self.assertEqual(encodings.valid_param("base64", "url,nowrap"), None)
        self.assertIn("только", encodings.valid_param("base64", "gzip"))
        from filesystem.states.registry import registry

        self.assertIsNone(registry.get("base64"))                                    # слой base64 убран

