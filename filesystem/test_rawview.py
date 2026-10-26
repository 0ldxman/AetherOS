import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

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

    def make(self, path, url="", state="", **extra):
        return MachineFile.objects.create(machine=self.machine, path=path, url=url, state=state, **extra)

    def raw(self, file, session_state="", keys=frozenset(), reader=None):
        return build_raw(file, session_state, keys, reader)

    def test_a_wiki_record_becomes_the_container_of_its_type_with_the_real_text(self):
        data = self.raw(self.make("/a", "apps/wiki/Harbor/Report")).data
        self.assertTrue(data.startswith("§rec\nwho: marsh\n".encode()))
        self.assertIn(BODY.encode(), data)

        scan = self.raw(self.make("/b", "apps/wiki/Harbor/Page")).data
        self.assertTrue(scan.startswith(formats.SCAN_MAGIC))
        self.assertIn(b"OCR " + BODY.encode(), scan[:-5])

        snp = self.raw(self.make("/c", "apps/wiki/Harbor/Site")).data
        self.assertTrue(snp.startswith(b"<!--SNP\nsrc:  aether://Harbor/Site"))
        self.assertIn(b"<!--@seal ", snp)

        doc = self.raw(self.make("/d", "apps/wiki/Harbor/Letter")).data
        self.assertTrue(doc.startswith(formats.DOC_MAGIC + b"\x00\x03body"))
        self.assertIn(BODY.encode(), doc)

    def test_a_direct_link_finds_the_same_document(self):
        Document.objects.filter(pk=self.doc.pk).update(direct_link="harbor-report")
        data = self.raw(self.make("/a", "apps/wiki/go/harbor-report/")).data
        self.assertIn(BODY.encode(), data)

    def test_the_disguised_layer_wins_over_the_type_of_the_record(self):
        raw = self.raw(self.make("/a", "apps/wiki/Harbor/Report", "> disguised scan"))
        self.assertEqual(raw.format, "scan")
        self.assertTrue(raw.data.startswith(formats.SCAN_MAGIC))
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
        self.assertTrue(packed.startswith(formats.PAK_MAGIC))

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
        self.assertTrue(wrapped.startswith(formats.SCAN_MAGIC))
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
        self.assertTrue(self.raw(self.make("/t", "apps/terminal/")).data.startswith(formats.APP_MAGIC))

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
