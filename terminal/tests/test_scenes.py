"""Сцены вокруг ответа команд и размеры файлов в ls и cnt.

Запуск: python manage.py test terminal.tests.test_scenes
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app, make_file
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class TerminalSceneTests(TerminalClient, TestCase):
    """Сцены терминала: работа команды играет до ответа, приветствие приходит со страницей."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        make_file(cls.main, "/home/door.bin", state="> encrypted hunter2 attempts=3")
        make_file(cls.main, "/home/note.txt", state="> binary base64")
        make_file(cls.main, "/home/pack.zip/a.txt", state="")
        make_file(cls.main, "/home/blob.bin", state="> binary utf16")
        make_file(cls.main, "/home/slice.img", state="> shifted skip=2 count=5")
        make_file(cls.main, "/home/report.txt", state="> disguised pdf")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def ops(self, scene):
        return [step["op"] for step in scene]

    def test_a_wrong_password_plays_the_work_and_ends_with_a_failure(self):
        data = self.run_command("ward /home/door.bin nope")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("bar", self.ops(data["scene"]))
        failed = [step for step in data["scene"] if step["op"] == "dots"]
        self.assertEqual(failed[-1]["status"], "FAIL")
        self.assertIn("decryption failed: Bad session key", data["output"])      # текст ответа остаётся

    def test_the_right_password_ends_with_success(self):
        data = self.run_command("ward /home/door.bin hunter2")
        self.assertEqual(data["exit_code"], 0)
        done = [step for step in data["scene"] if step["op"] == "dots"]
        self.assertEqual(done[-1]["status"], "OK")
        self.assertIn("decrypted", data["output"])

    def test_each_layer_has_its_own_command(self):
        for command, expected in (
            ("cvt enc base64 /home/note.txt", "converted"),
            ("pak x /home/pack.zip", "extracted"),
            ("cvt enc utf16 /home/blob.bin", "converted"),
            ("blk /home/slice.img skip=2", "copied"),
            ("cvt ext /home/report.txt .PDF", "converted"),
        ):
            data = self.run_command(command)
            self.assertEqual(data["exit_code"], 0, command + ": " + data["output"])
            self.assertIn(expected, data["output"])
            self.assertIsNotNone(data["scene"])

    def test_the_wrong_values_do_not_open_the_layer(self):
        cut = self.run_command("blk /home/slice.img skip=1")                                         # не на данных: файл есть, слой на месте
        self.assertEqual(cut["exit_code"], 0)
        self.assertIn("copied", self.run_command("blk /home/slice.img skip=2")["output"])
        self.assertEqual(self.run_command("cvt ext /home/report.txt .docx")["exit_code"], 1)
        self.assertIn("not an archive", self.run_command("pak l /home/report.txt")["output"])

    def test_the_old_names_are_gone(self):
        for name in ("cph", "b256", "bridge"):
            self.assertIn("command not found", self.run_command(f"{name} /home/door.bin x")["output"])

    def test_on_read_can_open_a_window_while_the_layer_stays(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/photo.dat", url="apps/wiki/real/",
            state="> disguised scan\non read: open apps/wiki/go/decoy/",
        )
        data = self.run_command("cnt /home/photo.dat")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("opened", data["output"])
        self.assertEqual(
            [(e["op"], e["url"], e["title"]) for e in data["effects"]], [("open", "/apps/wiki/go/decoy/", "decoy")]
        )
        self.assertIsNone(data["window"])                                                  # настоящий адрес ещё закрыт
        self.assertIn("cannot read as png", self.run_command("cvt ext /home/photo.dat /home/photo.png")["output"])      # слой на месте
        self.assertEqual(self.run_command("cvt ext /home/photo.dat /home/photo.scan")["exit_code"], 0)
        real = self.run_command("cnt /home/photo.scan")
        self.assertEqual(real["window"]["url"], "https://example.com/wiki/real")                         # хука больше нет: открывается настоящее
        self.assertFalse(real["effects"])

    def test_on_read_without_open_still_says_the_file_is_locked(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/sealed.dat",
                                   state='> binary utf16\non read: say "Something rustles inside."')
        data = self.run_command("cnt /home/sealed.dat")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("content is locked", data["output"])
        self.assertIn("Something rustles inside.", data["output"])

    def test_the_open_action_checks_its_address(self):
        from filesystem.layers.compiler import StateError, compile_text

        for good in ("open apps/wiki/go/a/", 'open "apps/map/?scene=harbor"', "open view/0c1a/"):
            compile_text(f"> binary utf16\non read: {good}")
        for bad in ("open", "open /admin/", "open https://evil.example/", "open a b", "open ../x", 'open "a b"'):
            with self.assertRaises(StateError, msg=bad):
                compile_text(f"> binary utf16\non read: {bad}")

    def test_rpr_says_when_another_damaged_layer_waits_underneath(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/hurt.dat", state="> damaged\n> damaged", size=9000)
        first = self.run_command("rpr /home/hurt.dat")
        self.assertEqual(first["exit_code"], 0)
        self.assertIn("further repair required", first["output"])
        bars = [step for step in first["scene"] if step["op"] == "bars"][0]["rows"]
        self.assertTrue(2 <= len(bars) <= 9)
        self.assertTrue(any(row["status"] == "FAIL" and row["stop"] < 100 for row in bars))        # часть блоков не поддалась
        second = self.run_command("rpr /home/hurt.dat")
        self.assertEqual(second["output"], "rpr: /home/hurt.dat: repaired")
        done = [step for step in second["scene"] if step["op"] == "bars"][0]["rows"]
        self.assertTrue(all(row["status"] == "OK" and row["stop"] == 100 for row in done))         # в последний проход вылечились все
        self.assertTrue(any("18 blocks" in str(step) or "pass 1/4" in str(step) for step in second["scene"]))     # размер 9000 -> 18 блоков
        self.assertIn("nothing to repair", self.run_command("rpr /home/hurt.dat")["output"])

    def test_ftyp_and_cnt_play_a_short_scene_that_gives_nothing_away(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/leaflet.txt", state="", url="apps/wiki/")
        plain, locked = self.run_command("ftyp /home/leaflet.txt"), self.run_command("ftyp /home/door.bin")
        self.assertEqual(self.ops(plain["scene"]), self.ops(locked["scene"]))
        self.assertEqual(plain["output"], "/home/leaflet.txt: data")
        opened = self.run_command("cnt /home/leaflet.txt")
        self.assertEqual(opened["exit_code"], 0)
        self.assertEqual([s for s in opened["scene"] if s["op"] == "dots"][-1]["status"], "OK")
        blocked = self.run_command("cnt /home/door.bin")
        self.assertEqual([s for s in blocked["scene"] if s["op"] == "dots"][-1]["status"], "FAIL")
        self.assertEqual(len([s for s in blocked["scene"] if s["op"] == "dots"]), 1)     # закрыто слоем: дальше проверки доступа не идём
        self.assertIsNone(self.run_command("ftyp /home/missing")["scene"])               # ошибка до начала работы
        self.assertIsNone(self.run_command("ftyp /home")["scene"])                       # папка: работы нет

    def test_the_size_is_the_same_in_ls_cnt_and_a_copy(self):
        from filesystem.testing import make_file

        make_file(self.main, "/home/big.dat", state="", size=123456, url="apps/wiki/")
        make_file(self.main, "/home/docs/inner.txt", state="")
        self.assertEqual(self.run_command("ls -l /home/big.dat")["output"], "123456  -rwxrwxrwx - -  big.dat")
        listing = self.run_command("ls -l /home")["output"].splitlines()
        self.assertIn("123456  -rwxrwxrwx - -  big.dat", [line.strip() for line in listing])
        self.assertTrue(any(line.endswith("docs/") and line.strip().startswith("4096") for line in listing))      # папка 4096
        self.assertIn("123456 bytes", self.run_command("cnt /home/big.dat")["output"])
        self.assertIn("120K  -rwxrwxrwx - -  big.dat", [line.strip() for line in self.run_command("ls -lh /home")["output"].splitlines()])

        make_file(self.main, "/home/plain.txt", state="")
        generated = self.run_command("ls -l /home/plain.txt")["output"].split()[0]              # без указанного размера
        self.assertEqual(generated, self.run_command("ls -l /home/plain.txt")["output"].split()[0])
        self.assertTrue(180 <= int(generated) <= 48000)
        self.run_command("cp /home/plain.txt /home/copy.txt")
        self.assertEqual(self.run_command("ls -l /home/copy.txt")["output"].split()[0], generated)

    def test_ls_options(self):
        self.assertEqual(self.run_command("ls -x")["exit_code"], 2)
        self.assertIn("./", self.run_command("ls -la")["output"])
        self.assertEqual(self.run_command("ls -a")["output"].split()[:2], [".", ".."])

    def test_commands_without_work_have_no_scene(self):
        self.assertIsNone(self.run_command("pwd")["scene"])
        self.assertIsNone(self.run_command("ward /home/missing.bin x")["scene"])      # ошибка до начала работы
        self.assertIsNone(self.run_command("ward")["scene"])

    def test_the_window_opens_with_a_greeting_scene(self):
        page = self.client.get(reverse("terminal:index")).content.decode()
        self.assertIn('id="terminal-greeting"', page)
        self.assertIn("aether-shell", page)
        self.assertIn("ui/console.js", page)

    def test_the_greeting_is_the_full_node_welcome(self):
        page = self.client.get(reverse("terminal:index")).content.decode()
        for part in ("System information", "Link load", "Standalone mode", "Type "):
            self.assertIn(part, page)
        self.assertNotIn('"op":"read"', page.replace(" ", ""))             # без паузы на чтение: окно открывается быстро

    def test_clear_asks_the_screen_to_wipe(self):
        data = self.run_command("clear")
        self.assertTrue(data["clear"])
        self.assertEqual((data["output"], data["exit_code"]), ("", 0))
        self.assertFalse(self.run_command("pwd")["clear"])
        self.assertEqual(self.run_command("clear now")["exit_code"], 2)

    def test_the_prompt_is_login_at_machine_and_path(self):
        page = self.client.get(reverse("terminal:index")).content.decode()
        self.assertIn('data-login="ivan"', page)
        self.assertIn("ivan@aether-main:~$", page)
        from terminal.views import prompt_path

        self.assertEqual(
            [prompt_path(p) for p in ("/home", "/home/docs", "/", "/etc", "/homework")],
            ["~", "~/docs", "/", "/etc", "/homework"],
        )
