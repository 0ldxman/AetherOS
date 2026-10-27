import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from assets.models import Asset
from filesystem.models import MachineFile
from filesystem.rawview import build_raw, encodings, formats
from filesystem.size import file_size
from machines.models import Machine
from wiki.models import Document, Namespace

BODY = "Cargo manifest altered.\n\nRef A-113."


class RawViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")
        user = get_user_model().objects.create_user("marsh", password="x")
        space = Namespace.objects.create(name="Harbor")
        cls.doc = Document.objects.create(namespace=space, title="Report", type="rec", body=BODY, created_by=user)
        cls.scan_doc = Document.objects.create(namespace=space, title="Page", type="scan", body=BODY)
        cls.web_doc = Document.objects.create(namespace=space, title="Site", type="web", body=BODY)
        cls.word_doc = Document.objects.create(namespace=space, title="Letter", type="doc", body=BODY)
        cls.closed = Document.objects.create(namespace=space, title="Closed", type="rec", body=BODY, access={"all": ["k1"]})
        cls.asset = Asset.objects.create(name="pic", file_id="1", size=11)

    def setUp(self):
        from filesystem.rawview.registry import invalidate

        invalidate()                                  # откат транзакции теста не сбрасывает запомненный реестр
        self.addCleanup(invalidate)

    def make(self, path, url="", state="", **extra):
        return MachineFile.objects.create(machine=self.machine, path=path, url=url, state=state, **extra)

    def raw(self, file, session_state="", keys=frozenset(), reader=None):
        return build_raw(file, session_state, keys, reader)

    def test_widgets_leave_no_wiki_syntax_in_the_file(self):
        text = "Intro.\n\n::map scene=outer caption=\"Outer\"\n::\n\n::stamp SECRET tone=red\n"
        space = Namespace.objects.get(name="Harbor")
        for kind, title, expected in (
            ("rec", "W1", b"[map: Outer]"),
            ("web", "W2", b'<figure data-kind="map"><figcaption>Outer</figcaption></figure>'),
            ("doc", "W3", b'{object map "Outer"}'),
            ("scan", "W4", b"Outer"),
        ):
            Document.objects.create(namespace=space, title=title, type=kind, body=text)
            data = self.raw(self.make(f"/w/{title}", f"apps/wiki/Harbor/{title}")).data
            self.assertIn(expected, data)
            self.assertNotIn(b"::map", data)
            self.assertNotIn(b"::stamp", data)

    def test_closed_record_hides_every_view_of_its_body(self):
        Document.objects.filter(pk=self.closed.pk).update(body="Secret.\n\n::map scene=x caption=\"Hidden place\"\n::\n")
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
        self.assertTrue(snp.startswith(b"<!--SNP\nsrc:  aether://Harbor/Site"))
        self.assertIn(b"<!--@seal ", snp)

        doc = self.raw(self.make("/d", "apps/wiki/Harbor/Letter")).data
        self.assertTrue(doc.startswith(formats.magic("doc") + b"\x00\x03body"))
        self.assertIn(BODY.encode(), doc)

    def test_a_direct_link_finds_the_same_document(self):
        Document.objects.filter(pk=self.doc.pk).update(direct_link="harbor-report")
        data = self.raw(self.make("/a", "apps/wiki/go/harbor-report/")).data
        self.assertIn(BODY.encode(), data)

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

        based = self.raw(self.make("/b", url, "> base64")).data
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

        packed = self.raw(self.make("/k", url, "> archive")).data
        self.assertTrue(packed.startswith(formats.magic("pak")))

    def test_a_removed_layer_stops_changing_the_view(self):
        from filesystem.states.stack import Progress, canonical_hash

        file = self.make("/a", "apps/wiki/Harbor/Report", "> base64")
        done = Progress(canonical_hash=canonical_hash("> base64"), removed=1).dump()
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
        self.assertEqual(self.raw(other).size, file_size(other))
        self.assertEqual(self.raw(self.make("/c", "", "> disguised pdf")).data[:5], b"%PDF-")   # формат виден и у шума

    def test_a_map_and_an_unknown_app(self):
        from map.models import MapScene

        MapScene.objects.create(slug="harbor", title="Harbor", features=[{"type": "marker", "key": "k9", "title": "secret"}])
        data = self.raw(self.make("/m", "apps/map/?scene=harbor")).data
        self.assertIn(b'"title": "Harbor"', data)
        self.assertNotIn(b"secret", data)                                         # пометка за ключом не утекает
        self.assertTrue(self.raw(self.make("/t", "apps/terminal/")).data.startswith(formats.magic("app")))

    def test_the_size_of_an_asset_without_layers_needs_no_download(self):
        file = self.make("/a", f"view/{self.asset.public_id}/")
        self.assertEqual(file_size(file), 11)                                     # Asset.size, без чтения из Nextcloud

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
        self.assertEqual(listed["Aether SCAN (image + OCR text)"]["bytes"][:5], [0x9E, 0x53, 0x43, 0x41, 0x4E])
        self.assertEqual(listed["Aether SNP (page snapshot)"]["prefix"], "<!--SNP\nsrc:  ")
        self.assertEqual(listed["Aether REC (record)"]["prefix"], "\u00a7rec\nwho: ")

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
            opened = build_raw(self.make("/n", "apps/mail/?message=cargo"), "", frozenset(), None, Reader())
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

        data = {"name": "x", "title": "", "extension": "", "kind": "signature", "magic": "", "template": "",
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
