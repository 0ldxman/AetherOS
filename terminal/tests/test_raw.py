"""Команды сырых байтов: ftyp, txtx, blk, cvt, rpr, kex.

Запуск: python manage.py test terminal.tests.test_raw
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import embed_key, make_app, make_file
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class RawCommandTests(TerminalClient, TestCase):
    """blk, txtx и cvt работают с настоящими данными файла (запись вики) и слоями поверх них."""

    BODY = "Cargo manifest altered.\n\nRef A-113."

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile
        from filesystem.testing import make_page

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        make_page("Harbor/Report", "rec", cls.BODY)
        url = "apps/wiki/Harbor/Report"
        for path, state in (
            ("/home/report.rec", ""),
            ("/home/skin.dat", "> disguised scan"),
            ("/home/wide.dat", "> binary utf16"),
            ("/home/vault.dat", "> encrypted hunter2"),
            ("/home/slice.img", "> shifted skip=2 count=5"),
        ):
            make_file(cls.main, path, state=state, url=url)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def test_txtx_prints_the_real_text_of_the_record(self):
        data = self.run_command("txtx /home/report.rec")
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("Cargo manifest altered.", data["output"])
        self.assertRegex(data["output"], r"^0x[0-9a-f]+  who: ")                       # со смещением, как strings -t x

    def test_txtx_finds_nothing_readable_under_a_cipher_or_a_wide_encoding(self):
        self.assertEqual(self.run_command("txtx /home/vault.dat")["output"].count("Cargo"), 0)
        self.assertNotIn("Cargo", self.run_command("txtx /home/wide.dat")["output"])      # UTF-16: ASCII-строк нет
        self.assertIn("Cargo manifest", self.run_command("txtx /home/skin.dat")["output"])  # контейнер scan: текст в блоке OCR

    def raw(self, path):
        return self.client.get(reverse("fsview:content") + f"?path={path}").content

    def test_blk_cuts_a_window_into_a_new_file_like_dd(self):
        whole = self.raw("/home/report.rec")
        data = self.run_command("blk /home/report.rec start=0 end=16")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("0+1 records in", data["output"])
        self.assertIn("16 bytes copied", data["output"])
        self.assertIn("/home/report.rec.prt.0", data["output"])                                 # имя: исходное, .prt, начало в hex
        self.assertEqual(self.raw("/home/report.rec.prt.0"), whole[:16])
        self.assertIn("report.rec.prt.0", self.run_command("ls /home")["output"])
        self.assertEqual(self.raw("/home/report.rec"), whole)                                    # исходник цел

        again = self.run_command("blk /home/report.rec.prt.0 start=4 end=10")                    # вырезка из вырезки
        self.assertEqual(again["exit_code"], 0)
        self.assertEqual(self.raw("/home/report.rec.prt.0.prt.4"), whole[4:10])

    def test_blk_in_blocks_reads_to_the_end_of_a_short_file(self):
        whole = self.raw("/home/report.rec")
        blocks = self.run_command("blk /home/report.rec skip=0 count=1")
        self.assertEqual(self.raw("/home/report.rec.prt.0"), whole)                              # блок длиннее файла: до конца
        self.assertIn(f"{len(whole)} bytes copied", blocks["output"])

    def test_blk_without_an_end_scans_for_it_and_shows_the_address(self):
        data = self.run_command("blk /home/report.rec start=8")
        text = " ".join(str(v) for step in data["scene"] for v in step.values())
        self.assertIn("scanning for EOF", text)
        self.assertIn(f"EOF at 0x{len(self.raw('/home/report.rec')):x}", text)
        named = self.run_command("blk /home/report.rec start=9 end=12")
        self.assertNotIn("scanning for EOF", " ".join(str(v) for step in named["scene"] for v in step.values()))

    def test_blk_refuses_what_dd_would_not_do_quietly(self):
        self.run_command("blk /home/report.rec start=0")
        for command, text in (
            ("blk /home/report.rec start=0", "exists"),
            ("blk /home/none start=0", "No such file"),
            ("blk /home/report.rec start=99999", "beyond the end"),
            ("blk /home/report.rec start=5 end=5", "end must be after start"),
            ("blk /home/report.rec skip=0 start=1", "not both"),
            ("blk /home/report.rec skip=x", "invalid skip"),
            ("blk /home/report.rec", "usage: blk"),
            ("blk -i /home/report.rec -o /home/z start=1", "usage: blk"),
            ("blk skip=1", "usage: blk"),
        ):
            data = self.run_command(command)
            self.assertNotEqual(data["exit_code"], 0, command)
            self.assertIn(text, data["output"], command)
        self.assertNotIn("prt.5", self.run_command("ls /home")["output"])

    def test_blk_cuts_what_the_player_sees_so_a_cipher_gives_noise(self):
        self.run_command("blk /home/vault.dat start=0")
        self.assertNotIn(b"Cargo", self.raw("/home/vault.dat.prt.0"))
        self.assertEqual(len(self.raw("/home/vault.dat.prt.0")), len(self.raw("/home/vault.dat")))

    def test_blk_reports_an_io_error_on_a_damaged_block(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/dmg.dat", state="> damaged", url="apps/wiki/Harbor/Report")
        data = self.run_command("blk /home/dmg.dat start=0")
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("I/O error at block 0", data["output"])
        text = " ".join(str(v) for step in data["scene"] for v in step.values())
        self.assertIn("I/O error at block 0", text)

    def test_blk_cut_at_the_data_of_a_shifted_file_is_the_real_file_and_any_other_is_junk(self):
        whole = self.raw("/home/report.rec")
        junk = self.run_command("blk /home/slice.img skip=1")
        self.assertEqual(junk["exit_code"], 0, junk["output"])
        self.assertIn("/home/slice.img.prt.200", junk["output"])                                  # неверно: .prt и начало в hex
        self.assertNotEqual(self.raw("/home/slice.img.prt.200")[:4], "§rec".encode()[:4])
        self.assertIn("no content", self.run_command("cnt /home/slice.img.prt.200")["output"])
        short = self.run_command("blk /home/slice.img start=0x400 end=0x410")                    # данные обрезаны
        self.assertIn("/home/slice.img.prt.400", short["output"])

        real = self.run_command("blk /home/slice.img skip=2")
        self.assertEqual(real["exit_code"], 0, real["output"])
        self.assertIn("/home/slice.img.out", real["output"])                                      # в слое нет out=: <имя>.out
        self.assertEqual(self.raw("/home/slice.img.out"), whole)                                  # настоящий файл без шума
        self.assertIn(f"{len(whole)} bytes copied", real["output"])
        opened = self.run_command("cnt /home/slice.img.out")
        self.assertEqual(opened["exit_code"], 0, opened["output"])
        self.assertIsNotNone(opened["window"])
        self.assertIn("exists", self.run_command("blk /home/slice.img start=0x400")["output"])    # слой на исходнике остался, имя занято
        self.run_command("del -f /home/slice.img.out")
        self.assertEqual(self.run_command("blk /home/slice.img start=0x400 end=0x9999")["exit_code"], 0)
        self.assertEqual(self.raw("/home/slice.img.out"), whole)

    def test_a_shifted_layer_names_the_real_file_with_out(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/dump.img", state="> shifted skip=2 out=photo.jpg",
                                   url="apps/wiki/Harbor/Report")
        make_file(self.main, "/home/dump2.img", state="> shifted skip=2 out=/home/deep.bin",
                                   url="apps/wiki/Harbor/Report")
        self.assertIn("/home/dump.img.prt.200", self.run_command("blk /home/dump.img skip=1")["output"])
        self.assertIn("/home/photo.jpg", self.run_command("blk /home/dump.img skip=2")["output"])
        self.assertTrue(self.raw("/home/photo.jpg").startswith("§rec".encode()))
        self.assertIn("/home/deep.bin", self.run_command("blk /home/dump2.img skip=2")["output"])

    def test_ftyp_names_a_file_by_the_start_of_its_bytes_when_no_layer_answers(self):
        self.run_command("blk /home/slice.img skip=2")
        self.run_command("blk /home/slice.img skip=1")
        self.assertIn("REC record", self.run_command("ftyp /home/slice.img.out")["output"])
        self.assertIn(": data", self.run_command("ftyp /home/slice.img.prt.200")["output"])      # шум: никакого формата
        self.assertIn("REC record", self.run_command("ftyp /home/report.rec")["output"])

    def test_blk_cut_of_a_key_block_can_be_given_to_kex(self):
        self.keyed_file()
        offset = int(self.offset_of_block("/home/keyed.rec"), 16)
        self.run_command(f"blk /home/keyed.rec start={offset}")
        data = self.run_command(f"kex /home/keyed.rec.prt.{offset:x} 0")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("key secret_a", data["output"])

    def test_cvt_names_the_container_and_the_error_shows_the_real_header(self):
        data = self.run_command("cvt ext /home/skin.dat /home/skin.pdf")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("cannot read as pdf", data["output"])
        self.assertIn("unexpected header: 9e 53 43 41 4e 0d 0a 1b", data["output"])        # то, что лежит в начале на самом деле
        self.assertEqual(self.raw("/home/skin.dat")[:8], b"\x9eSCAN\r\n\x1b")

        ok = self.run_command("cvt ext /home/skin.dat /home/skin.SCAN")                    # регистр не важен
        self.assertEqual((ok["exit_code"], ok["output"]), (0, "cvt: /home/skin.dat: converted\n  /home/skin.SCAN"))
        self.assertTrue(self.raw("/home/skin.SCAN").startswith("§rec".encode()))                       # копия стала записью rec
        self.assertEqual(self.raw("/home/skin.dat")[:4], b"\x9eSCA")                                    # у исходника слой остался

    def test_cvt_ext_with_only_an_extension_converts_the_file_in_place(self):
        data = self.run_command("cvt ext /home/skin.dat .scan")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("/home/skin.dat -> /home/skin.scan", data["output"])
        self.assertIn("No such file", self.run_command("txtx /home/skin.dat")["output"])
        self.assertTrue(self.raw("/home/skin.scan").startswith("§rec".encode()))

    def test_cvt_ext_refuses_an_existing_output_and_a_wrong_copy_does_not_free_the_original(self):
        self.run_command("cvt ext /home/skin.dat /home/a.scan")
        self.assertIn("exists", self.run_command("cvt ext /home/skin.dat /home/a.scan")["output"])
        self.run_command("cvt ext /home/skin.dat /home/b.pdf")
        self.assertEqual(self.raw("/home/skin.dat")[:4], b"\x9eSCA")                                    # неудача копии не снимает слой с исходника

    def test_cvt_ext_takes_an_alias_and_a_zip_format_lists_its_files(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/pic.dat", state="> disguised jpg", url="apps/wiki/Harbor/Report")
        self.assertEqual(self.run_command("cvt ext /home/pic.dat /home/pic.jpeg")["exit_code"], 0)
        data = self.run_command("cvt ext /home/pic.dat .JPG")                                              # у исходника слой остался
        self.assertIn("/home/pic.dat -> /home/pic.jpg", data["output"])
        make_file(self.main, "/home/word.dat", state="> disguised docx", url="apps/wiki/Harbor/Report")
        data = self.run_command("cvt ext /home/word.dat /home/word.docx")
        self.assertEqual(data["exit_code"], 0, data["output"])
        text = " ".join(str(v) for step in data["scene"] for v in step.values())
        self.assertIn("reading central directory", text)
        self.assertIn("document.xml", text)

    def keyed_file(self, path="/home/keyed.rec", state=""):
        from filesystem.testing import make_file
        from filesystem.testing import key_item

        item = make_file(self.main, path, url="apps/wiki/Harbor/Report", state=state)
        embed_key(item.item, "secret_a")
        return item

    def offset_of_block(self, path):
        runs = self.run_command(f"txtx {path}")["output"].splitlines()
        return next(line.split()[0] for line in runs if "-----BEGIN ACCESS KEY-----" in line)

    def test_kex_extracts_the_key_found_by_txtx_into_the_hidden_secrets_folder(self):
        self.keyed_file()
        offset = self.offset_of_block("/home/keyed.rec")
        data = self.run_command(f"kex /home/keyed.rec {offset}")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("key secret_a extracted to /home/.secrets/secret_a", data["output"])
        self.assertNotIn(".secrets", self.run_command("ls /home")["output"])                 # папка скрыта
        self.assertIn(".secrets", self.run_command("ls -a /home")["output"])
        self.assertIn("secret_a", self.run_command("ls /home/.secrets")["output"])
        self.assertIn("Keyname: secret_a", self.run_command("txtx /home/.secrets/secret_a")["output"])
        again = self.run_command(f"kex /home/keyed.rec {offset}")
        self.assertIn("already in /home/.secrets/secret_a", again["output"])

    def test_kex_needs_the_exact_place_and_an_open_file_and_a_real_key(self):
        self.keyed_file()
        self.keyed_file("/home/closed.rec", "> encrypted hunter2")
        offset = int(self.offset_of_block("/home/keyed.rec"), 16)
        self.assertEqual(self.run_command(f"kex /home/keyed.rec {offset + 40}")["exit_code"], 1)
        self.assertEqual(self.run_command(f"kex /home/keyed.rec {offset - 3}")["exit_code"], 0)    # txtx может склеить блок с байтами перед ним
        denied = self.run_command(f"kex /home/closed.rec {offset}")
        self.assertIn("no key at", denied["output"])                                             # под шифром по смещению шум
        self.assertEqual([s for s in denied["scene"] if s["op"] == "dots"][-1]["status"], "FAIL")
        from filesystem.models import Item, ItemKey

        ItemKey.objects.filter(key__slug="secret_a").delete()
        Item.objects.filter(slug="secret_a").delete()
        self.assertIn("no key at", self.run_command(f"kex /home/report.rec 0")["output"])
        for command in ("kex", "kex /home/keyed.rec", "kex /home/keyed.rec x"):
            self.assertEqual(self.run_command(command)["exit_code"], 2, command)

    def test_a_key_in_the_secrets_folder_opens_what_needs_it_and_deleting_the_file_takes_it_back(self):
        from filesystem.models import Volume
        from machines.models import MachineMount, Session
        from wiki.testing import make_document, make_namespace

        from filesystem.testing import wiki_sections

        section = make_namespace("Section")
        make_document(section, "Gated", type="rec", body="x", access={"all": ["secret_a"]})
        wiki_sections(self.main, [section.volume])
        self.keyed_file()
        offset = self.offset_of_block("/home/keyed.rec")
        session = Session.objects.get(user=self.user)
        stored = self.client.session
        stored["machine_session_id"] = session.pk
        stored.save()
        self.assertEqual(self.client.get("/apps/wiki/Section/Gated").status_code, 403)
        self.run_command(f"kex /home/keyed.rec {offset}")
        opened = self.client.get("/apps/wiki/Section/Gated", follow=True)
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.redirect_chain[0][0].split("?")[0].rsplit("/view/", 1)[1], "doc/")       # открывается окно документа
        self.run_command("del -f /home/.secrets/secret_a")
        self.assertEqual(self.client.get("/apps/wiki/Section/Gated").status_code, 403)

    def test_cvt_needs_one_of_its_two_forms(self):
        for command in ("cvt", "cvt /home/skin.dat pdf", "cvt ext /home/skin.dat", "cvt enc utf16"):
            data = self.run_command(command)
            self.assertEqual(data["exit_code"], 2, command)
            self.assertIn("usage: cvt ext file out | cvt enc encoding file", data["output"])

    def test_cvt_decodes_a_binary_layer_by_its_encoding(self):
        wrong = self.run_command("cvt enc rot13 /home/wide.dat")
        self.assertEqual(wrong["exit_code"], 1)
        self.assertIn("unexpected header: a7 00 72 00", wrong["output"])
        self.assertEqual(self.run_command("cvt enc utf16 /home/wide.dat")["exit_code"], 0)
        self.assertIn("Cargo manifest", self.run_command("txtx /home/wide.dat")["output"])   # теперь текст читается

    def test_cvt_on_a_file_without_such_layers_and_the_scenes_give_nothing_away(self):
        self.assertIn("nothing to convert", self.run_command("cvt ext /home/report.rec .pdf")["output"])
        self.assertIn("nothing to decode", self.run_command("cvt enc rot13 /home/report.rec")["output"])
        scene = self.run_command("cvt ext /home/skin.dat /home/s.pdf")["scene"]
        self.assertEqual([s for s in scene if s["op"] == "dots"][-1]["status"], "FAIL")
        self.assertNotIn("bars", [s["op"] for s in scene])                                  # до чтения потоков не дошли
        good = self.run_command("cvt ext /home/skin.dat /home/s.scan")["scene"]
        self.assertIn("bars", [s["op"] for s in good])                                       # у скана по полосе на блок IMG, OCR, CONF

    def test_cvt_enc_scene_fails_at_the_stream_check_and_shows_no_decoding(self):
        data = self.run_command("cvt enc rot13 /home/wide.dat")
        self.assertIn("cannot decode as rot13", data["output"])
        scene = data["scene"]
        self.assertEqual([s for s in scene if s["op"] == "dots"][-1]["status"], "FAIL")
        self.assertNotIn("bar", [s["op"] for s in scene])

    def test_cvt_scene_speaks_the_language_of_the_format(self):
        from terminal.scenes.shell import convert_scene, decode_scene

        def text(fmt, kind="disguised"):
            steps = convert_scene("/a", 400, fmt, True, "/b") if kind == "disguised" else decode_scene("/a", 400, fmt, True)
            return " ".join(str(v) for step in steps for v in step.values())

        self.assertIn("pages", text("pdf"))
        self.assertIn("fields", text("rec"))
        self.assertIn("nodes", text("snp"))
        self.assertNotIn("pages", text("rec"))
        self.assertIn("reading part table", text("doc"))
        self.assertIn("reading chunk table", text("scan"))
        self.assertIn("OCR", text("scan"))
        self.assertIn("code units", text("utf16", "binary"))
        self.assertIn("checking byte order", text("utf16", "binary"))
        self.assertIn("checking code page", text("cp1251", "binary"))
        self.assertNotIn("byte order", text("cp1251", "binary"))
        self.assertIn("checking digit pairs", text("hex", "binary"))
        self.assertIn("splitting dots and dashes", text("morse", "binary"))
        self.assertNotIn("decoding streams", text("rot13", "binary"))                       # у кодировки своя сцена, не про формат
        self.assertIn("/b", text("pdf"))
        self.assertNotIn("checking", text("pdf"))

    def test_the_size_in_ls_is_the_length_of_the_bytes_that_blk_cuts(self):
        size = int(self.run_command("ls -l /home/report.rec")["output"].split()[0])
        data = self.run_command("blk /home/report.rec skip=0")
        self.assertIn(f"{size} bytes copied", data["output"])
        self.assertEqual(int(self.run_command("ls -l /home/report.rec.prt.0")["output"].split()[0]), size)
        self.assertIn(f"{size} bytes)", self.run_command("cnt /home/report.rec")["output"])

    def test_cnt_r_opens_the_raw_viewer_with_the_same_bytes(self):
        data = self.run_command("cnt -r /home/skin.dat")
        self.assertEqual(data["exit_code"], 0, data["output"])
        window = data["window"]
        self.assertEqual(window["title"], "skin.dat [raw]")
        self.assertIn("/view/fs/raw/?path=%2Fhome%2Fskin.dat", window["url"])
        page = self.client.get(window["url"])
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-raw-viewer")
        self.assertContains(page, "/view/fs/raw/content/?path=%2Fhome%2Fskin.dat")

    def test_the_raw_content_is_served_in_ranges_like_an_asset(self):
        url = reverse("fsview:content") + "?path=/home/skin.dat"
        size = int(self.run_command("ls -l /home/skin.dat")["output"].split()[0])
        head = self.client.head(url)
        self.assertEqual((head.status_code, head["Content-Length"]), (200, str(size)))

        first = self.client.get(url, HTTP_RANGE="bytes=0-7")
        self.assertEqual(first.status_code, 206)
        self.assertEqual(first.content, b"\x9eSCAN\r\n\x1b")                                    # то же, что видит txtx
        self.assertEqual(first["Content-Range"], f"bytes 0-7/{size}")
        self.assertEqual(len(self.client.get(url, HTTP_RANGE="bytes=-4").content), 4)
        self.assertEqual(self.client.get(url, HTTP_RANGE=f"bytes={size + 10}-").status_code, 416)
        self.assertEqual(len(self.client.get(url).content), size)

    def test_the_raw_viewer_shows_only_the_players_own_files(self):
        missing = reverse("fsview:content") + "?path=/home/none.dat"
        self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.client.get(reverse("fsview:content") + "?path=/home").status_code, 404)   # папка
        self.client.logout()
        self.assertEqual(self.client.get(reverse("fsview:content") + "?path=/home/skin.dat").status_code, 403)
