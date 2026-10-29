"""Архивы, подписи и слои с ключами.

Запуск: python manage.py test terminal.tests.test_archives
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import key_item, make_app, make_file
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class ArchiveTests(TerminalClient, TestCase):
    """Архив это файл с расширением, под путём которого лежат другие файлы: pak l, pak x, pak pass."""

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
        for path, state, extra in (
            ("/home/plain.txt", "", {}),
            ("/home/pack.zip/README.txt", "", {}),
            ("/home/pack.zip/notes/a.txt", "", {}),
            ("/home/pack.zip/inner.7z/key.txt", "", {}),
            ("/home/lock.zip", "> encrypted hunter2 attempts=2", {"url": ""}),
            ("/home/lock.zip/x.txt", "", {}),
            ("/home/bad.zip", "> damaged", {"url": ""}),
            ("/home/bad.zip/y.txt", "", {}),
            ("/home/stuff.old", "", {"file_type": "DIRECTORY", "url": ""}),
            ("/home/stuff.old/f.txt", "", {}),
        ):
            make_file(cls.main, path, state=state, **({"url": url} | extra))

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def raw(self, path):
        return self.client.get(reverse("fsview:content") + f"?path={path}").content

    def test_an_archive_is_a_file_in_ls_and_cd_cannot_enter_it(self):
        listing = self.run_command("ls /home")["output"]
        self.assertIn("pack.zip", listing)
        self.assertNotIn("pack.zip/", listing)                                          # файл, не папка
        self.assertIn("stuff.old/", listing)                                            # запись DIRECTORY: обычная папка
        self.assertIn("f.txt", self.run_command("ls /home/stuff.old")["output"])
        self.assertNotEqual(self.run_command("cd /home/pack.zip")["exit_code"], 0)
        self.assertNotEqual(self.run_command("ls /home/pack.zip/README.txt")["exit_code"], 0)
        self.assertNotEqual(self.run_command("cnt /home/pack.zip/README.txt")["exit_code"], 0)   # члены недоступны
        self.assertIn("no content", self.run_command("cnt /home/pack.zip")["output"])
        self.assertIn("PAK archive", self.run_command("ftyp /home/pack.zip")["output"])

    def test_pak_l_lists_the_members_without_the_content_of_nested_archives(self):
        data = self.run_command("pak l /home/pack.zip")
        self.assertEqual(data["exit_code"], 0, data["output"])
        for name in ("README.txt", "notes/", "a.txt", "inner.7z"):
            self.assertIn(name, data["output"])
        self.assertNotIn("key.txt", data["output"])                                     # вложенный раскрывается только после распаковки
        self.assertIn("3 files", data["output"])
        lines = data["output"].splitlines()
        self.assertEqual(lines[0], "pack.zip")                                          # дерево, а не пути
        self.assertEqual(lines[1].split()[:2], ["├──", "notes/"])                      # папки первыми
        self.assertTrue(lines[2].startswith("│   └── a.txt"))
        self.assertTrue(lines[-3].startswith("└── README.txt"))                          # последний на своём уровне с «└»
        self.assertNotIn("notes/a.txt", data["output"])

    def test_pak_x_unpacks_next_to_the_archive_and_refuses_to_overwrite(self):
        data = self.run_command("pak x /home/pack.zip")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("extracted 3 files to /home/pack", data["output"])
        self.assertIn("README.txt", self.run_command("ls /home/pack")["output"])
        self.assertIn("a.txt", self.run_command("ls /home/pack/notes")["output"])
        self.assertIn("exists", self.run_command("pak x /home/pack.zip")["output"])
        self.assertIn("pack.zip", self.run_command("ls /home")["output"])               # архив остался

    def test_pak_x_can_pick_members_and_a_folder(self):
        data = self.run_command("pak x /home/pack.zip notes -d /home/out")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertEqual(self.run_command("ls /home/out/notes")["output"].strip(), "a.txt")
        self.assertIn("Not found in archive", self.run_command("pak x /home/pack.zip nothing")["output"])

    def test_a_nested_archive_opens_only_after_the_outer_one_is_unpacked(self):
        self.assertNotEqual(self.run_command("pak l /home/pack.zip/inner.7z")["exit_code"], 0)       # по внутреннему пути не достать
        self.run_command("pak x /home/pack.zip")
        data = self.run_command("pak l /home/pack/inner.7z")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("key.txt", data["output"])
        self.assertEqual(self.run_command("pak x /home/pack/inner.7z")["exit_code"], 0)
        self.assertIn("key.txt", self.run_command("ls /home/pack/inner")["output"])

    def test_a_password_archive_needs_pak_pass_and_ward_does_not_open_it(self):
        self.assertIn("password required", self.run_command("pak l /home/lock.zip")["output"])
        self.assertIn("password required", self.run_command("pak x /home/lock.zip")["output"])
        self.assertIn("no valid data found", self.run_command("ward /home/lock.zip hunter2")["output"])
        self.assertIn("incorrect password", self.run_command("pak pass /home/lock.zip nope")["output"])
        self.assertEqual(self.run_command("pak pass /home/lock.zip hunter2")["exit_code"], 0)
        self.assertIn("x.txt", self.run_command("pak l /home/lock.zip")["output"])
        self.assertIn("not password protected", self.run_command("pak pass /home/lock.zip hunter2")["output"])

    def test_a_damaged_archive_cannot_be_read_until_it_is_repaired(self):
        self.assertIn("Unexpected EOF", self.run_command("pak l /home/bad.zip")["output"])
        self.assertEqual(self.run_command("rpr /home/bad.zip")["exit_code"], 0)
        self.assertIn("y.txt", self.run_command("pak l /home/bad.zip")["output"])

    def test_pak_refuses_what_is_not_an_archive_and_bad_usage(self):
        self.assertIn("not an archive", self.run_command("pak l /home/plain.txt")["output"])
        self.assertIn("not an archive", self.run_command("pak pass /home/plain.txt x")["output"])
        self.assertIn("No such file", self.run_command("pak l /home/none.zip")["output"])
        self.assertIn("Is a directory", self.run_command("pak l /home/stuff.old")["output"])
        for command in ("pak", "pak l", "pak z /home/pack.zip", "pak pass /home/lock.zip"):
            self.assertEqual(self.run_command(command)["exit_code"], 2, command)

    def test_the_bytes_of_an_archive_are_a_table_and_the_data_of_its_members(self):
        from filesystem.content.rawview import formats

        data = self.raw("/home/pack.zip")
        self.assertTrue(data.startswith(formats.magic("pak")))
        for name in ("README.txt", "notes/a.txt", "inner.7z"):
            self.assertIn(name.encode(), data)
        self.assertIn(b"Cargo manifest altered.", data)
        size = int(self.run_command("ls -l /home/pack.zip")["output"].split()[0])
        self.assertEqual(size, len(data))
        locked = self.raw("/home/lock.zip")
        self.assertNotIn(b"x.txt", locked)                                              # под паролем только шум
        self.assertNotIn(b"Cargo", locked)

    def test_files_cannot_be_put_into_an_archive(self):
        self.assertNotEqual(self.run_command("cp /home/plain.txt /home/pack.zip/new.txt")["exit_code"], 0)


@override_settings(FORCE_SCRIPT_NAME=None)
class SignatureTests(TerminalClient, TestCase):
    """Подписи: блоки в байтах файла (ward verify) и подпись игрока ключом из /home/.secrets (ward sign)."""

    BODY = "Cargo manifest altered.\n\nRef A-113."

    @classmethod
    def setUpTestData(cls):
        import datetime

        from filesystem.models import ItemSignature
        from filesystem.testing import make_file, key_item
        from machines.models import MachineProfile
        from filesystem.testing import key_item
        from filesystem.testing import make_page

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        make_page("Harbor/Report", "rec", cls.BODY)
        cls.director = key_item("director")
        cls.other = key_item("other")
        url = "apps/wiki/Harbor/Report"

        def make(path, state="", signed=()):
            item = make_file(cls.main, path, url=url, state=state)
            for key, valid, date in signed:
                ItemSignature.objects.create(item=item.item, key=key_item(key.slug), valid=valid, date=date)
            return item

        make("/home/plain.rec")
        make("/home/memo.rec", signed=[(cls.director, True, datetime.date(2026, 10, 26))])
        make("/home/forged.rec", signed=[(cls.director, False, None)])
        make("/home/co.rec", signed=[(cls.director, True, None), (cls.other, False, None)])
        make("/home/vault.rec", "> encrypted hunter2", signed=[(cls.director, True, None)])

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def raw(self, path):
        return self.client.get(reverse("fsview:content") + f"?path={path}").content

    def give_key(self, slug):
        from django.test import RequestFactory

        from filesystem.testing import give_key_to_session
        from machines.current import active_session

        self.run_command("pwd")                                                      # сессия игрока появляется при первой команде
        request = RequestFactory().get("/")
        request.session = self.client.session
        request.user = self.user
        give_key_to_session(active_session(request), slug)

    def test_a_signed_file_carries_a_block_after_its_content_and_verifies(self):
        data = self.raw("/home/memo.rec")
        self.assertIn(b"-----BEGIN SIGNATURE-----\nKeyname: director\nDate: 2026-10-26\n", data)
        self.assertTrue(data.startswith("§rec".encode()))
        good = self.run_command("ward verify /home/memo.rec")
        self.assertEqual(good["exit_code"], 0, good["output"])
        self.assertIn("Signature made 2026-10-26 using key director", good["output"])
        self.assertIn("Good signature from director", good["output"])
        self.assertEqual(int(self.run_command("ls -l /home/memo.rec")["output"].split()[0]), len(data))

    def test_a_forged_signature_and_an_unsigned_file_do_not_verify(self):
        bad = self.run_command("ward verify /home/forged.rec")
        self.assertEqual(bad["exit_code"], 1)
        self.assertIn("BAD signature from director", bad["output"])
        none = self.run_command("ward verify /home/plain.rec")
        self.assertEqual(none["exit_code"], 1)
        self.assertIn("no signature found", none["output"])
        both = self.run_command("ward verify /home/co.rec")                          # две подписи: одна верна, вторая нет
        self.assertEqual(both["exit_code"], 1)
        self.assertIn("Good signature from director", both["output"])
        self.assertIn("BAD signature from other", both["output"])

    def test_any_change_of_the_content_breaks_the_signature(self):
        self.run_command("blk /home/memo.rec start=2")                               # вырезка без первых байтов, подпись осталась
        self.assertIn("BAD signature from director", self.run_command("ward verify /home/memo.rec.prt.2")["output"])
        self.run_command("blk /home/memo.rec start=0 end=40")                        # вырезка до подписи
        self.assertIn("no signature found", self.run_command("ward verify /home/memo.rec.prt.0")["output"])

    def test_a_layer_hides_the_signature(self):
        self.assertNotIn(b"SIGNATURE", self.raw("/home/vault.rec"))
        self.assertIn("no signature found", self.run_command("ward verify /home/vault.rec")["output"])

    def test_ward_sign_makes_a_detached_signature_with_a_key_from_the_secrets_folder(self):
        self.assertIn("no secret key", self.run_command("ward sign -k director /home/plain.rec")["output"])
        self.give_key("director")
        data = self.run_command("ward sign -k director /home/plain.rec")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("/home/plain.rec.sig", data["output"])
        self.assertTrue(self.raw("/home/plain.rec.sig").startswith(b"-----BEGIN SIGNATURE-----\nKeyname: director\n"))
        self.assertIn("SIG detached signature", self.run_command("ftyp /home/plain.rec.sig")["output"])
        good = self.run_command("ward verify /home/plain.rec.sig /home/plain.rec")
        self.assertEqual(good["exit_code"], 0, good["output"])
        self.assertIn("Good signature from director", good["output"])
        self.assertIn("BAD signature", self.run_command("ward verify /home/plain.rec.sig /home/memo.rec")["output"])   # подпись чужого файла
        self.assertIn("exists", self.run_command("ward sign -k director /home/plain.rec")["output"])
        self.assertEqual(self.run_command("ward sign -k director /home/none")["exit_code"], 2)

    def test_ward_verify_and_sign_usage_and_a_missing_file(self):
        for command in ("ward verify", "ward verify a b c", "ward sign", "ward sign -k director"):
            self.assertEqual(self.run_command(command)["exit_code"], 2, command)
        self.assertEqual(self.run_command("ward verify /home/none")["exit_code"], 2)

    def test_a_signed_mail_attachment_verifies_after_it_is_saved_into_the_session(self):
        from filesystem import keystore
        from filesystem.models import ItemSignature, PlayerFile
        from filesystem.testing import make_file, key_item
        from machines.models import Session

        self.run_command("pwd")
        attachment = make_file(self.main, "/mail/att.rec", url="apps/wiki/Harbor/Report",
                                                delivered_only=True)
        ItemSignature.objects.create(item=attachment.item, key=key_item(self.director.slug), valid=True)
        from filesystem.machine_view import MachineView

        MachineView(self.main, self.user).put_item("/home/att.rec", attachment.item)
        self.assertIn("Good signature from director", self.run_command("ward verify /home/att.rec")["output"])


@override_settings(FORCE_SCRIPT_NAME=None)
class WardKeyTests(TerminalClient, TestCase):
    """ward расшифровывает паролем или ключом из /home/.secrets; зашифрованный файл в байтах выглядит как PGP."""

    BODY = "Cargo manifest altered.\n\nRef A-113."

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile
        from filesystem.testing import key_item
        from filesystem.testing import make_page

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        make_page("Harbor/Report", "rec", cls.BODY)
        key_item("director", name="Director of the harbor office")
        key_item("other")
        url = "apps/wiki/Harbor/Report"
        for path, state in (
            ("/home/pass.rec", "> encrypted hunter2"),
            ("/home/keyed.rec", "> encrypted key=director attempts=2"),
            ("/home/both.rec", "> encrypted hunter2 key=director"),
        ):
            make_file(cls.main, path, state=state, url=url)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def raw(self, path):
        return self.client.get(reverse("fsview:content") + f"?path={path}").content

    def give_key(self, slug):
        from django.test import RequestFactory

        from filesystem.testing import give_key_to_session
        from machines.current import active_session

        self.run_command("pwd")
        request = RequestFactory().get("/")
        request.session = self.client.session
        request.user = self.user
        give_key_to_session(active_session(request), slug)

    def test_an_encrypted_file_looks_like_a_pgp_packet_and_ftyp_says_so(self):
        from filesystem.content.rawview import keys

        pw = self.raw("/home/pass.rec")
        self.assertTrue(pw.startswith(b"\x8c\x0d\x04\x09\x03\x08"))
        self.assertNotIn(b"Cargo", pw)
        self.assertIn("PGP symmetric key encrypted data", self.run_command("ftyp /home/pass.rec")["output"])
        pk = self.raw("/home/keyed.rec")
        self.assertTrue(pk.startswith(b"\x85\x01\x0c\x03" + keys.key_id("director")))      # в файле ID ключа получателя
        self.assertIn("PGP public-key encrypted data", self.run_command("ftyp /home/keyed.rec")["output"])
        self.assertEqual(len(pw), len(self.raw("/home/pass.rec")))

    def test_the_password_is_reported_the_way_gpg_does(self):
        bad = self.run_command("ward /home/pass.rec nope")
        self.assertEqual(bad["exit_code"], 1)
        self.assertIn("ward: decryption failed: Bad session key", bad["output"])
        good = self.run_command("ward /home/pass.rec hunter2")
        self.assertEqual(good["exit_code"], 0)
        self.assertIn("ward: encrypted with 1 passphrase", good["output"])

    def test_a_key_decrypts_what_is_encrypted_for_it(self):
        self.assertIn("no secret key 'director'", self.run_command("ward -k director /home/keyed.rec")["output"])
        self.give_key("other")
        wrong = self.run_command("ward -k other /home/keyed.rec")
        self.assertEqual(wrong["exit_code"], 1)
        self.assertIn("decryption failed: No secret key", wrong["output"])                # не тот ключ: попытка потрачена
        self.give_key("director")
        good = self.run_command("ward -k director /home/keyed.rec")
        self.assertEqual(good["exit_code"], 0, good["output"])
        self.assertIn("encrypted with RSA key, ID", good["output"])
        self.assertIn('"director"', good["output"])
        self.assertTrue(self.raw("/home/keyed.rec").startswith("§rec".encode()))        # слой снят

    def test_a_file_with_a_password_and_a_key_opens_with_either(self):
        self.give_key("director")
        self.assertEqual(self.run_command("ward -k director /home/both.rec")["exit_code"], 0)
        self.assertEqual(self.run_command("ward /home/pass.rec hunter2")["exit_code"], 0)
        self.assertNotEqual(self.run_command("ward /home/keyed.rec hunter2")["exit_code"], 0)     # у ключевого пароля нет

    def test_a_wrong_key_spends_an_attempt_and_the_fail_hook_fires(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/trap.rec", url="apps/wiki/Harbor/Report",
                                   state="> encrypted key=director attempts=1\non fail: say \"alarm\"")
        self.give_key("other")
        data = self.run_command("ward -k other /home/trap.rec")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("alarm", data["output"])

    def test_ward_keys_lists_the_keys_with_their_ids(self):
        from filesystem.content.rawview import keys

        self.assertIn("no keys", self.run_command("ward keys")["output"])
        self.give_key("director")
        data = self.run_command("ward keys")
        self.assertEqual(data["exit_code"], 0)
        self.assertIn(keys.key_id("director").hex().upper(), data["output"])
        self.assertIn("director", data["output"])
        self.assertIn("Director of the harbor office", data["output"])

    def test_the_keyname_is_the_content_not_the_file_name(self):
        self.give_key("director")
        self.run_command("mv /home/.secrets/director /home/.secrets/id_rsa")
        data = self.run_command("ward keys")
        self.assertIn("id_rsa", data["output"])                                   # имя файла и keyname рядом
        self.assertIn("director", data["output"])
        self.assertEqual(self.run_command("ward -k director /home/keyed.rec")["exit_code"], 0)      # ключ назван по keyname
        self.assertIn("no secret key", self.run_command("ward -k id_rsa /home/both.rec")["output"])

    def test_a_key_file_placed_on_the_machine_counts_once_it_lies_in_the_secrets(self):
        from filesystem import keystore
        from filesystem.testing import make_file
        from django.test import RequestFactory
        from machines.current import active_session

        self.run_command("pwd")
        make_file(self.main, "/home/.secrets/badge", url="keys/director")
        request = RequestFactory().get("/")
        request.session = self.client.session
        request.user = self.user
        self.assertIn("director", __import__("filesystem.keystore", fromlist=["x"]).slugs_of(active_session(request)))
        self.assertEqual(self.run_command("ward -k director /home/keyed.rec")["exit_code"], 0)
        self.assertEqual(self.run_command("del -f /home/.secrets/badge")["exit_code"], 0)
        self.assertNotIn("director", __import__("filesystem.keystore", fromlist=["x"]).slugs_of(active_session(request)))

    def test_cnt_opens_a_key_as_text(self):
        self.give_key("director")
        data = self.run_command("cnt /home/.secrets/director")
        self.assertEqual(data["exit_code"], 0, data["output"])
        window = data["window"]
        self.assertIn("/view/fs/text/", window["url"])
        body = self.client.get(window["url"]).content.decode()
        self.assertIn("-----BEGIN ACCESS KEY-----", body)
        self.assertIn("Keyname: director", body)

    def test_ward_k_usage(self):
        for command in ("ward -k", "ward -k director", "ward -k a b c"):
            self.assertEqual(self.run_command(command)["exit_code"], 2, command)
