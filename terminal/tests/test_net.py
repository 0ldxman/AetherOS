"""Сетевые команды nreq и nget.

Запуск: python manage.py test terminal.tests.test_net
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, set_script_prefix

from filesystem.testing import key_item, make_app, make_file
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class NetTests(TerminalClient, TestCase):
    """nreq и nget: внутриигровые серверы с узлами по путям, файлы приходят в сессию игрока."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile, NetNode, NetResource
        from filesystem.testing import key_item

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.server = Machine.objects.create(name="Archive", hostname="aether-archive")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        own = make_file(cls.main, "/home/own.txt", state="")
        ledger = make_file(cls.server, "/srv/ledger.dat", state="> encrypted hunter2")
        report = make_file(cls.server, "/srv/report.txt", state="")

        site = NetResource.objects.create(address="Apollo.com/", title="Apollo")
        cls.site = site
        NetNode.objects.create(resource=site, path="", response="APOLLO\n{listing}\nbye")
        NetNode.objects.create(resource=site, path="info")                                   # без текста: один список
        NetNode.objects.create(resource=site, path="info/file.pdf", item=ledger.item)
        NetNode.objects.create(resource=site, path="info/file2.png", item=report.item)
        NetNode.objects.create(resource=site, path="info/attachements/a.txt", item=report.item)    # папка только по пути
        NetNode.objects.create(resource=site, path="info/data", response="DATA SECTION")      # текст без {listing}
        NetNode.objects.create(resource=site, path="info/data/x.bin", item=report.item)
        NetNode.objects.create(resource=site, path="private", response="members", token="sesame")
        NetNode.objects.create(resource=site, path="info/own.txt", item=own.item)
        NetNode.objects.create(resource=site, path="info/hidden.txt", item=report.item, key_condition="nokey")
        key_item("nokey")

        radio = NetResource.objects.create(address="14.230")
        NetNode.objects.create(resource=radio, path="", response="RELAY")
        ftp = NetResource.objects.create(address="FTP://apollo.com")
        NetNode.objects.create(resource=ftp, path="", response="FTP READY")
        NetNode.objects.create(resource=ftp, path="pub/tool.bin", item=report.item)
        NetResource.objects.create(address="hidden.net", key_condition="nokey")
        NetResource.objects.create(address="vault.net", token="sesame")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def test_the_address_is_a_url_and_the_listing_tag_marks_the_place(self):
        data = self.run_command("nreq https://apollo.com")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertEqual(data["output"], "APOLLO\ninfo/\nprivate\nbye")                # {listing}: папка info, и узел private
        self.assertEqual(self.run_command("nreq apollo.com/")["output"], data["output"])
        self.assertEqual(self.run_command("nreq 14.230")["output"], "RELAY")             # без {listing} списка нет

    def test_a_node_without_text_prints_only_its_listing_folders_first(self):
        data = self.run_command("nreq https://apollo.com/info/")
        self.assertEqual(data["output"], "attachements/\ndata/\nfile.pdf\nfile2.png\nown.txt")   # hidden.txt по ключу не виден
        self.assertEqual(self.run_command("nreq apollo.com/info/data")["output"], "DATA SECTION")
        self.assertEqual(self.run_command("nreq apollo.com/info/attachements")["output"], "a.txt")   # папка, которой нет узлом

    def test_unknown_hidden_and_missing_look_right(self):
        for address in ("nowhere.net", "hidden.net"):
            data = self.run_command(f"nreq {address}")
            self.assertEqual(data["exit_code"], 1)
            self.assertIn("could not resolve host", data["output"])
        self.assertIn("404", self.run_command("nreq apollo.com/nothing")["output"])
        self.assertIn("404", self.run_command("nreq apollo.com/info/hidden.txt")["output"])

    def test_tokens_guard_a_server_and_a_node(self):
        self.assertIn("401", self.run_command("nreq vault.net")["output"])
        self.assertEqual(self.run_command("nreq --token sesame vault.net")["exit_code"], 0)
        self.assertIn("401", self.run_command("nreq apollo.com/private")["output"])
        self.assertEqual(self.run_command("nreq --token sesame apollo.com/private")["output"], "members")

    def test_nget_saves_a_fresh_copy_with_its_layers(self):
        data = self.run_command("nget https://apollo.com/info/file.pdf")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("file.pdf", self.run_command("ls /home")["output"])
        self.assertEqual(self.run_command("ward /home/file.pdf hunter2")["exit_code"], 0)
        self.assertEqual(self.run_command("nget apollo.com/info/file.pdf")["exit_code"], 0)    # скачать ещё раз: слой на месте
        self.assertIn("Bad session key", self.run_command("ward /home/file.pdf nope")["output"])

    def test_nget_output_path_and_errors(self):
        self.assertEqual(self.run_command("nget -o /home/copy.txt apollo.com/info/file2.png")["exit_code"], 0)
        self.assertIn("copy.txt", self.run_command("ls /home")["output"])
        self.assertIn("not a file", self.run_command("nget apollo.com/info")["output"])         # папка
        self.assertIn("404", self.run_command("nget apollo.com/info/none.txt")["output"])
        self.assertEqual(self.run_command("nget -o /nowhere/x apollo.com/info/file2.png")["exit_code"], 1)

    def test_a_file_of_the_own_machine_leaves_the_original_in_place(self):
        self.assertEqual(self.run_command("nget -o /home/own2.txt apollo.com/info/own.txt")["exit_code"], 0)
        listing = self.run_command("ls /home")["output"]
        self.assertIn("own.txt", listing)
        self.assertIn("own2.txt", listing)

    def test_addresses_are_normalised_on_save(self):
        from machines.models import normalize_address, split_url

        self.assertEqual(self.site.address, "apollo.com")
        self.assertEqual(normalize_address("HTTPS://Apollo.com/info/"), "https://apollo.com")
        self.assertEqual(normalize_address("Apollo.com/info/"), "apollo.com")
        self.assertEqual(
            split_url("https://apollo.com/info/attachements/?x=1#top"), ("https", "apollo.com", "info/attachements")
        )
        self.assertEqual(split_url("14.230"), ("", "14.230", ""))

    def test_the_scheme_is_part_of_the_address_when_the_server_has_one(self):
        self.assertEqual(self.run_command("nreq ftp://apollo.com")["output"], "FTP READY")          # точная схема
        self.assertEqual(self.run_command("nreq FTP://Apollo.com/pub")["output"], "tool.bin")
        self.assertEqual(self.run_command("nreq https://apollo.com")["output"].splitlines()[0], "APOLLO")   # сервер без схемы: любая
        self.assertEqual(self.run_command("nreq apollo.com")["output"].splitlines()[0], "APOLLO")           # и без схемы вовсе
        self.assertEqual(self.run_command("nreq ftp://apollo.com/info")["exit_code"], 1)            # на ftp нет страницы info
        self.assertEqual(self.run_command("nget ftp://apollo.com/pub/tool.bin")["exit_code"], 0)
        self.assertEqual(self.run_command("nget apollo.com/pub/tool.bin")["exit_code"], 1)          # у сервера без схемы такого узла нет
        self.assertIn("could not resolve", self.run_command("nreq http://hidden.net")["output"])
