"""Терминал: безымянный игрок видит окно, но команды отвечают ошибкой авторизации.

Запуск: python manage.py test terminal
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import embed_key, key_item, make_file
from machines.models import Machine, MachineApp
from users.aether_auth import AUTH_REQUIRED


@override_settings(FORCE_SCRIPT_NAME=None)
class AnonymousTerminalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        MachineApp.objects.create(machine=cls.null, label="console", glyph=">_", path="/apps/terminal/")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def witness(self):
        session = self.client.session
        session["guest"] = True
        session.save()

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        ok = response["Content-Type"].startswith("application/json")
        return response, (json.loads(response.content) if ok else None)

    def test_the_window_opens_for_a_witness(self):
        self.witness()
        response = self.client.get(reverse("terminal:index"))
        self.assertContains(response, "aether-null")

    def test_every_command_answers_with_the_authorization_error_in_the_terminal(self):
        self.witness()
        for command in ("ls", "cnt /home/readme", "whoami", ""):
            response, data = self.run_command(command)
            self.assertEqual(response.status_code, 200, command)           # ошибка внутри терминала, а не редирект
            self.assertEqual(data["exit_code"], 1)
            self.assertIn(AUTH_REQUIRED, data["output"])
            self.assertIsNone(data["window"])
            self.assertEqual(data["hostname"], "aether-null")

    def test_nothing_is_executed_for_a_witness(self):
        from filesystem.models import PlayerFile

        self.witness()
        self.run_command("ls")
        self.assertEqual(PlayerFile.objects.count(), 0)

    def test_a_visitor_who_is_not_connected_anywhere_is_refused(self):
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 403)
        self.assertEqual(self.run_command("ls")[0].status_code, 403)

    def test_the_machine_needs_the_console_icon(self):
        MachineApp.objects.all().delete()
        self.witness()
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 403)

    def test_a_signed_in_player_still_gets_a_real_terminal(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=main, label="console", glyph=">_", path="/apps/terminal/")
        self.client.force_login(user)
        response, data = self.run_command("pwd")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(AUTH_REQUIRED, data["output"])
        self.assertEqual(data["hostname"], "aether-main")


@override_settings(FORCE_SCRIPT_NAME=None)
class TerminalSceneTests(TestCase):
    """Сцены терминала: работа команды играет до ответа, приветствие приходит со страницей."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
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

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

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
        from filesystem.states.compiler import StateError, compile_text

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
        self.assertEqual(self.run_command("ls -l /home/big.dat")["output"], "123456  big.dat")
        listing = self.run_command("ls -l /home")["output"].splitlines()
        self.assertIn("123456  big.dat", [line.strip() for line in listing])
        self.assertTrue(any(line.endswith("docs/") and line.strip().startswith("4096") for line in listing))      # папка 4096
        self.assertIn("123456 bytes", self.run_command("cnt /home/big.dat")["output"])
        self.assertIn("120K  big.dat", [line.strip() for line in self.run_command("ls -lh /home")["output"].splitlines()])

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


@override_settings(FORCE_SCRIPT_NAME=None)
class BridgeFixture(TestCase):
    """Машины, записи и помощники для проверки входа на другие машины."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.hashers import make_password

        from filesystem.testing import make_file
        from machines.models import MachineProfile, MachineProfileHID, MachineProfileToken
        from filesystem.testing import key_item

        cls.main = Machine.objects.create(name="Main", hostname="aether-main", hid="AA:00:00:00:00:01")
        cls.core = Machine.objects.create(name="Core", hostname="aether-core", hid="AA:00:00:00:00:02")
        cls.deep = Machine.objects.create(name="Deep", hostname="aether-deep", hid="AA:00:00:00:00:03")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.home = MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan",
                                                 freq=1, mail="ivan@aether-main")

        def account(machine, login, freq=14.230, **extra):
            return MachineProfile.objects.create(machine=machine, login=login, name=login, freq=freq, **extra)

        cls.open_account = account(cls.core, "guest")
        cls.root = account(cls.core, "root", password_hash=make_password("s3cret"))
        cls.ops = account(cls.core, "ops", password_hash=make_password("s3cret"), key_condition="cardkey")
        cls.badge = account(cls.core, "badge", key_condition="cardkey")
        cls.tok = account(cls.core, "tok", password_hash=make_password("s3cret"), key_condition="cardkey")
        cls.walled = account(cls.core, "walled")
        MachineProfileHID.objects.create(profile=cls.walled, hid="FF:FF:FF:FF:FF:FF")
        cls.twin_a = account(cls.core, "twin", freq=14.230)
        cls.twin_b = account(cls.core, "twin", freq=15.000)
        cls.deep_open = account(cls.deep, "dig")
        cls.core_to_deep = account(cls.core, "relay")
        MachineProfileToken.objects.create(profile=cls.tok, token="golden", max_usage=1)
        MachineProfileToken.objects.create(profile=cls.tok, token="forever")

        key_item("cardkey")
        key_item("otherkey")
        make_file(cls.main, "/home/trap.bin", state="> encrypted hunter2 attempts=1\non fail: kick")
        make_file(cls.main, "/home/noise.bin",
                                   state="> encrypted hunter2 attempts=1\non fail: alert unreachable count=3 gap=200")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        from django.core.cache import cache

        cache.clear()
        self.client.force_login(self.user)

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

    def answer(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"answer": text}), content_type="application/json"
        )
        return json.loads(response.content)

    def where(self):
        from django.test import RequestFactory

        from machines.current import active_session

        request = RequestFactory().get("/")
        request.session = self.client.session
        request.user = self.user
        return active_session(request).profile

    def give_key(self, slug):
        """Ключ лежит в папке секретов текущей сессии игрока (как после kex)."""
        from django.test import RequestFactory

        from filesystem.testing import give_key_to_session
        from machines.current import active_session

        request = RequestFactory().get("/")
        request.session = self.client.session
        request.user = self.user
        give_key_to_session(active_session(request), slug)

    def request(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.session = self.client.session
        request.user = self.user
        return request

    def depth(self):
        """Подключений до рабочего стола."""
        from machines import bridge

        return bridge.depth(self.request())

    def shells(self):
        """Подключений от рабочего стола до терминала (оболочки, у которых рабочий стол остался позади)."""
        from machines import bridge

        request = self.request()
        tree = request.session.get(bridge.TREE_KEY)
        if not tree:
            return 0
        return max(0, bridge._depth_of(tree, tree["terminal"]) - bridge._depth_of(tree, tree["desktop"]))


@override_settings(FORCE_SCRIPT_NAME=None)
class BridgeTests(BridgeFixture):
    """Мост: вход на другую машину из терминала (rcon), условия входа, стек сессий, выход."""

    # ---------- вход ----------

    def test_an_open_account_lets_the_player_in_and_exit_brings_them_back(self):
        data = self.run_command("rcon guest@aether-core")
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["effects"], [{"op": "switch"}])
        self.assertTrue(any(step["op"] == "dots" for step in data["scene"]))
        self.assertEqual(self.where().login, "guest")
        self.assertEqual(self.depth(), 1)

        data = self.run_command("exit")
        self.assertEqual(data["effects"], [{"op": "switch"}])
        self.assertEqual(self.where().login, "ivan")
        self.assertEqual(self.depth(), 0)
        self.assertEqual(self.run_command("exit")["exit_code"], 1)               # выходить некуда

    def test_unknown_host_and_account_are_named(self):
        self.assertIn("could not resolve host", self.run_command("rcon guest@nowhere")["output"])
        self.assertIn("no such account", self.run_command("rcon stranger@aether-core")["output"])
        self.assertEqual(self.depth(), 0)

    def test_a_password_account_asks_for_the_password(self):
        data = self.run_command("rcon root@aether-core")
        self.assertEqual(data["prompt"]["kind"], "password")
        self.assertEqual(self.depth(), 0)                                        # пока не вошли

        data = self.answer("wrong")
        self.assertIn("Permission denied (password)", data["output"])
        self.assertEqual(data["exit_code"], 1)
        self.assertEqual(self.depth(), 0)

        self.run_command("rcon root@aether-core")
        data = self.answer("s3cret")
        self.assertEqual(data["effects"], [{"op": "switch"}])
        self.assertEqual(self.where().login, "root")

    def test_a_key_account_needs_the_key_from_the_secrets_folder(self):
        self.assertIn("Permission denied (publickey)", self.run_command("rcon badge@aether-core")["output"])
        self.assertIn("not found", self.run_command("rcon -i cardkey badge@aether-core")["output"])      # такого ключа у игрока нет
        self.give_key("otherkey")
        self.assertIn("Permission denied", self.run_command("rcon -i otherkey badge@aether-core")["output"])  # не тот ключ
        self.give_key("cardkey")
        self.assertEqual(self.run_command("rcon -i cardkey badge@aether-core")["exit_code"], 0)
        self.assertEqual(self.where().login, "badge")

    def test_rshell_and_xfer_take_the_same_key_name(self):
        self.assertIn("not found", self.run_command("rshell -i cardkey badge@aether-core")["output"])
        self.assertIn("not found", self.run_command("xfer -i cardkey badge@aether-core:/home/readme /home/x")["output"])
        self.give_key("cardkey")
        self.assertEqual(self.run_command("rshell -i cardkey badge@aether-core")["exit_code"], 0)
        self.assertEqual(self.shells(), 1)

    def test_a_deleted_key_file_is_a_lost_key(self):
        self.give_key("cardkey")
        self.run_command("del -f /home/.secrets/cardkey")
        self.assertIn("not found", self.run_command("rcon -i cardkey badge@aether-core")["output"])

    def test_a_password_and_key_account_needs_both(self):
        data = self.run_command("rcon ops@aether-core")                        # без ключа: пароль всё равно спросят
        self.assertEqual(data["prompt"]["kind"], "password")
        self.assertIn("Permission denied (publickey,password)", self.answer("s3cret")["output"])
        self.assertEqual(self.depth(), 0)

        self.give_key("cardkey")
        self.run_command("rcon -i cardkey ops@aether-core")
        self.assertIn("Permission denied", self.answer("nope")["output"])        # ключ есть, пароль неверный

        self.run_command("rcon -i cardkey ops@aether-core")
        self.assertEqual(self.answer("s3cret")["effects"], [{"op": "switch"}])

    def test_a_token_replaces_password_and_key_and_is_spent(self):
        data = self.run_command("rcon --token golden tok@aether-core")
        self.assertEqual((data["exit_code"], data["prompt"]), (0, None))
        self.assertEqual(self.where().login, "tok")
        self.run_command("rcon-close")
        self.assertIn("token rejected", self.run_command("rcon --token golden tok@aether-core")["output"])   # один раз
        self.assertEqual(self.run_command("rcon -t forever tok@aether-core")["exit_code"], 0)                # без предела
        self.run_command("rcon-close")
        self.assertIn("token rejected", self.run_command("rcon --token nope tok@aether-core")["output"])

    def test_an_expired_token_is_rejected(self):
        from datetime import timedelta

        from django.utils import timezone

        from machines.models import MachineProfileToken

        MachineProfileToken.objects.filter(token="forever").update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertIn("token rejected", self.run_command("rcon -t forever tok@aether-core")["output"])

    def test_only_listed_machines_may_enter_a_walled_account(self):
        self.assertIn("Permission denied", self.run_command("rcon walled@aether-core")["output"])
        self.assertEqual(self.depth(), 0)

    def test_several_endpoints_need_the_endpoint_option(self):
        self.assertIn("-p", self.run_command("rcon twin@aether-core")["output"])
        self.assertEqual(self.run_command("rcon -p 15 twin@aether-core")["exit_code"], 0)
        self.assertEqual(self.where().freq, self.twin_b.freq)
        self.assertEqual(self.run_command("exit")["exit_code"], 0)
        self.assertIn("no such account", self.run_command("rcon -p 99 twin@aether-core")["output"])

    # ---------- стек ----------

    def test_nested_bridges_exit_one_level_and_bridge_close_leaves_them_all(self):
        from machines.models import MachineProfile

        MachineProfile.objects.create(machine=self.core, login="hop", name="hop", freq=2)
        self.run_command("rcon hop@aether-core")
        self.run_command("rcon dig@aether-deep")
        self.assertEqual((self.depth(), self.where().login), (2, "dig"))

        self.run_command("exit")
        self.assertEqual((self.depth(), self.where().login), (1, "hop"))
        self.run_command("rcon dig@aether-deep")
        self.run_command("rcon-close")
        self.assertEqual((self.depth(), self.where().login), (0, "ivan"))
        self.assertEqual(self.run_command("rcon-close")["exit_code"], 1)

    def test_the_depth_is_limited(self):
        from machines.models import MachineProfile

        for n in range(6):
            MachineProfile.objects.create(machine=self.core, login=f"l{n}", name="x", freq=100 + n)
        results = [self.run_command(f"rcon l{n}@aether-core") for n in range(6)]
        self.assertEqual(self.depth(), 4)
        self.assertIn("too many nested", results[-1]["output"])

    def test_the_same_session_is_reused_between_visits(self):
        from machines.models import Session

        self.run_command("rcon guest@aether-core")
        first = self.client.session["machine_session_id"]
        self.run_command("rcon-close")
        self.run_command("rcon guest@aether-core")
        self.assertEqual(self.client.session["machine_session_id"], first)
        self.assertEqual(Session.objects.filter(profile=self.open_account).count(), 1)

    def test_the_shell_restarts_in_home_on_the_new_machine(self):
        self.run_command("cd /")
        data = self.run_command("rcon guest@aether-core")
        self.assertEqual(data["cwd"], "/home")
        self.assertEqual(self.run_command("pwd")["output"], "/home")

    def test_the_prompt_can_be_cancelled(self):
        self.run_command("rcon root@aether-core")
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"cancel": True}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.answer("s3cret")["effects"], [])                    # запроса уже нет
        self.assertEqual(self.depth(), 0)

    # ---------- рабочий стол ----------

    def test_the_desktop_opens_the_tunnel_terminal_on_the_foreign_machine(self):
        page = self.client.get(reverse("desktop")).content.decode()
        self.assertNotIn("data-tunnel-url", page)
        self.run_command("rcon guest@aether-core")
        page = self.client.get(reverse("desktop")).content.decode()
        self.assertIn("data-tunnel-url", page)
        self.assertIn("rcon: guest@", page)

    def test_the_tunnel_url_carries_the_site_prefix_once(self):
        self.run_command("rcon guest@aether-core")
        set_script_prefix("/proxy/8000/")
        page = self.client.get("/desktop/").content.decode()
        self.assertIn('data-tunnel-url="/proxy/8000/apps/terminal/"', page)

    def test_the_terminal_works_in_the_tunnel_even_without_its_icon(self):
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 200)
        self.run_command("rcon guest@aether-core")                                # у core иконки терминала нет
        self.assertEqual(self.client.get(reverse("terminal:index")).status_code, 200)
        self.client.post(reverse("terminal:bridge_close"))
        self.assertEqual(self.depth(), 0)

    def test_closing_the_tunnel_window_closes_every_bridge(self):
        self.run_command("rcon guest@aether-core")
        response = self.client.post(reverse("terminal:bridge_close"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.depth(), self.where().login), (0, "ivan"))

    # ---------- хуки ----------

    def test_the_kick_hook_throws_the_player_out_of_the_bridge(self):
        self.run_command("rcon guest@aether-core")
        # файл ловушки лежит на main, а на core свой пустой диск: заводим такой же файл на core
        from filesystem.testing import make_file

        make_file(self.core, "/home/trap.bin",
                                   state="> encrypted hunter2 attempts=1\non fail: kick")
        data = self.run_command("ward /home/trap.bin nope")
        self.assertEqual([e["op"] for e in data["effects"]], ["play", "switch"])
        self.assertEqual((self.depth(), self.where().login), (0, "ivan"))

    def test_the_kick_hook_at_the_base_machine_sends_the_player_to_the_entry_screen(self):
        data = self.run_command("ward /home/trap.bin nope")
        self.assertEqual([e["op"] for e in data["effects"]], ["play", "lock"])
        self.assertEqual(data["effects"][1]["url"], reverse("lock"))

    def test_the_alert_hook_reaches_the_browser(self):
        data = self.run_command("ward /home/noise.bin nope")
        alert = [e for e in data["effects"] if e["op"] == "alert"][0]
        self.assertEqual((alert["message"], alert["count"], alert["gap"]), ("unreachable", 3, 200))



@override_settings(FORCE_SCRIPT_NAME=None)
class RshellTests(BridgeFixture):
    """rshell: оболочка на другой машине внутри терминала (рабочий стол не меняется), exit, xfer."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from filesystem.testing import make_file

        make_file(cls.main, "/home/notes.txt", state="")
        make_file(cls.main, "/home/work/a.txt", state="")
        make_file(cls.main, "/home/vault.bin", state="> encrypted hunter2")
        make_file(cls.core, "/home/loot.dat", state="> encrypted hunter2")
        make_file(cls.core, "/home/docs/readme.txt", state="")

    def test_rshell_enters_without_switching_the_desktop(self):
        data = self.run_command("rshell guest@aether-core")
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual((data["hostname"], data["login"]), ("aether-core", "guest"))
        self.assertEqual(self.where().login, "ivan")                    # рабочий стол остался на aether-main
        self.assertEqual((self.depth(), self.shells()), (0, 1))
        self.assertFalse(any(step["op"] == "cut" for step in data["scene"]))
        self.assertEqual([e["op"] for e in data["effects"]], ["play"])  # приветствие той машины
        self.assertIn("loot.dat", self.run_command("ls /home")["output"])
        self.assertNotIn("notes.txt", self.run_command("ls /home")["output"])

    def test_exit_leaves_the_shell_and_restores_the_folder(self):
        self.assertEqual(self.run_command("cd /home/work")["cwd"], "/home/work")
        data = self.run_command("rshell guest@aether-core")
        self.assertEqual(data["cwd"], "/home")
        data = self.run_command("exit")
        self.assertEqual((data["hostname"], data["login"], data["cwd"]), ("aether-main", "ivan", "/home/work"))
        self.assertIsNone(data["effects"] or None)
        self.assertEqual(self.shells(), 0)
        self.assertIn("notes.txt", self.run_command("ls /home")["output"])

    def test_rshell_asks_for_the_same_conditions(self):
        data = self.run_command("rshell root@aether-core")
        self.assertEqual(data["prompt"]["kind"], "password")
        self.assertEqual(self.shells(), 0)
        self.assertIn("Permission denied", self.answer("nope")["output"])
        self.run_command("rshell root@aether-core")
        data = self.answer("s3cret")
        self.assertEqual((data["login"], data["hostname"]), ("root", "aether-core"))
        self.assertEqual(self.shells(), 1)

    def test_rcon_inside_a_shell_grows_from_the_shell_and_moves_the_desktop_there(self):
        self.run_command("rshell guest@aether-core")
        data = self.run_command("rcon dig@aether-deep")
        self.assertEqual(data["effects"], [{"op": "switch"}])
        self.assertEqual(self.where().login, "dig")
        self.assertEqual([row["label"] for row in data["tabs"]], ["ivan@aether-main", "guest@aether-core", "dig@aether-deep"])
        self.run_command("rcon-close")
        self.assertEqual((self.depth(), self.shells()), (0, 0))
        self.assertEqual(self.where().login, "ivan")
        self.run_command("rcon guest@aether-core")
        self.assertEqual(self.run_command("rshell dig@aether-deep")["exit_code"], 0)
        self.assertEqual((self.depth(), self.shells()), (1, 1))
        self.assertEqual(self.run_command("exit")["login"], "guest")            # сначала оболочка
        self.assertEqual(self.run_command("exit")["effects"], [{"op": "switch"}])   # потом мост

    def test_xfer_downloads_a_file_into_the_players_session_with_its_layers(self):
        self.run_command("rshell guest@aether-core")
        data = self.run_command("xfer :/home/loot.dat /home/got.dat")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("transferred", data["output"])
        self.run_command("exit")
        self.assertIn("got.dat", self.run_command("ls /home")["output"])
        self.assertEqual(self.run_command("ward /home/got.dat hunter2")["exit_code"], 0)    # слой переехал вместе с файлом

    def test_xfer_uploads_and_a_folder_destination_keeps_the_name(self):
        self.run_command("rshell guest@aether-core")
        data = self.run_command("xfer /home/notes.txt :/home/docs")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("readme.txt", self.run_command("ls /home/docs")["output"])
        self.assertIn("notes.txt", self.run_command("ls /home/docs")["output"])
        self.run_command("exit")
        self.assertNotIn("docs", self.run_command("ls /home")["output"])

    def test_xfer_errors(self):
        self.assertIn("not inside an rshell", self.run_command("xfer :/home/x y")["output"])
        self.run_command("rshell guest@aether-core")
        self.assertIn("No such file", self.run_command("xfer :/home/none.dat /home/a")["output"])
        self.assertIn("not a regular file", self.run_command("xfer :/home/docs /home/a")["output"])
        self.assertEqual(self.run_command("xfer /home/a /home/b")["exit_code"], 2)         # нет удалённой стороны
        self.assertEqual(self.run_command("xfer :/home/a :/home/b")["exit_code"], 2)       # обе удалённые

    def test_xfer_with_an_address_needs_no_shell_and_asks_for_the_password(self):
        data = self.run_command("xfer guest@aether-core:/home/loot.dat /home/got.dat")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertEqual(self.shells(), 0)
        self.assertIn("got.dat", self.run_command("ls /home")["output"])

        data = self.run_command("xfer root@aether-core:/home/loot.dat /home/second.dat")
        self.assertEqual(data["prompt"]["kind"], "password")
        self.assertNotIn("second.dat", self.run_command("ls /home")["output"])
        data = self.answer("s3cret")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("second.dat", self.run_command("ls /home")["output"])

        self.run_command("xfer root@aether-core:/home/loot.dat /home/third.dat")
        self.assertIn("Permission denied", self.answer("wrong")["output"])
        self.assertNotIn("third.dat", self.run_command("ls /home")["output"])

    def test_closing_the_tunnel_also_closes_shells(self):
        self.run_command("rshell guest@aether-core")
        self.client.post(reverse("terminal:bridge_close"))
        self.assertEqual(self.shells(), 0)

    def test_a_kick_inside_a_shell_throws_the_player_out_of_the_shell_only(self):
        self.run_command("rshell guest@aether-core")
        from filesystem.testing import make_file

        make_file(self.core, "/home/trap2.bin", state="> encrypted x attempts=1\non fail: kick")
        data = self.run_command("ward /home/trap2.bin wrong")
        self.assertEqual(self.shells(), 0)
        self.assertNotIn({"op": "switch"}, data["effects"])
        self.assertEqual(data["hostname"], "aether-main")



@override_settings(FORCE_SCRIPT_NAME=None)
class TabsTests(BridgeFixture):
    """Подключения это дерево со вкладками: терминал и рабочий стол ходят по нему независимо."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from filesystem.testing import make_file

        make_file(cls.main, "/home/notes.txt", state="")
        make_file(cls.main, "/home/work/a.txt", state="")
        make_file(cls.core, "/home/loot.dat", state="")
        make_file(cls.deep, "/home/deep.dat", state="")

    def post(self, name, node):
        response = self.client.post(reverse(f"terminal:{name}"), data=json.dumps({"node": node}), content_type="application/json")
        return response.status_code, json.loads(response.content)

    def chain(self):
        """main -> core (rcon, рабочий стол там) -> deep (rshell, терминал там)."""
        self.run_command("rcon guest@aether-core")
        return self.run_command("rshell dig@aether-deep")

    def test_the_tabs_list_the_tree_and_say_where_the_terminal_and_the_desktop_are(self):
        self.assertEqual(self.run_command("pwd")["tabs"], [])                              # одна машина: вкладок нет
        data = self.chain()
        rows = {row["label"]: row for row in data["tabs"]}
        self.assertEqual(list(rows), ["ivan@aether-main", "guest@aether-core", "dig@aether-deep"])
        self.assertEqual(rows["dig@aether-deep"]["parent"], rows["guest@aether-core"]["id"])
        self.assertTrue(rows["dig@aether-deep"]["terminal"] and not rows["dig@aether-deep"]["desktop"])
        self.assertTrue(rows["guest@aether-core"]["desktop"] and not rows["guest@aether-core"]["terminal"])

    def test_clicking_a_tab_moves_the_terminal_and_not_the_desktop(self):
        data = self.chain()
        ids = {row["label"]: row["id"] for row in data["tabs"]}
        code, data = self.post("tab_focus", ids["ivan@aether-main"])
        self.assertEqual(code, 200)
        self.assertEqual((data["login"], data["hostname"]), ("ivan", "aether-main"))
        self.assertEqual(self.where().login, "guest")                                      # рабочий стол остался на core
        self.assertIn("notes.txt", self.run_command("ls /home")["output"])                 # команды идут на выбранной вкладке
        code, data = self.post("tab_focus", ids["dig@aether-deep"])
        self.assertIn("deep.dat", self.run_command("ls /home")["output"])
        self.assertEqual(self.post("tab_focus", "99")[0], 404)

    def test_a_window_is_not_opened_from_a_tab_the_desktop_is_not_on(self):
        self.run_command("rshell guest@aether-core")                                        # терминал на core, стол на main
        data = self.run_command("cnt /home/loot.dat")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("no display", data["output"])
        self.assertIsNone(data["window"])
        self.post("tab_focus", "0")
        self.assertNotIn("no display", self.run_command("cnt /home/notes.txt")["output"])   # на столе работает как обычно

    def test_each_tab_remembers_its_folder(self):
        self.run_command("cd /home/work")
        data = self.run_command("rshell guest@aether-core")
        self.assertEqual(data["cwd"], "/home")
        self.post("tab_focus", "0")
        self.assertEqual(self.run_command("pwd")["output"], "/home/work")
        self.post("tab_focus", "1")
        self.assertEqual(self.run_command("pwd")["output"], "/home")

    def test_a_tab_menu_moves_the_desktop(self):
        data = self.chain()
        ids = {row["label"]: row["id"] for row in data["tabs"]}
        code, data = self.post("tab_desktop", ids["dig@aether-deep"])
        self.assertEqual(data["effects"], [{"op": "switch"}])
        self.assertEqual(self.where().login, "dig")
        self.assertEqual(self.depth(), 2)
        self.assertEqual(self.post("tab_desktop", ids["dig@aether-deep"])[0], 404)         # он и так там

    def test_closing_a_tab_closes_everything_opened_from_it(self):
        data = self.chain()
        ids = {row["label"]: row["id"] for row in data["tabs"]}
        code, data = self.post("tab_close", ids["guest@aether-core"])
        self.assertEqual(code, 200)
        self.assertEqual([row["label"] for row in data["tabs"]], [])                       # остался только корень
        self.assertEqual(data["effects"], [{"op": "switch"}])                              # рабочий стол был под закрытым
        self.assertEqual(self.where().login, "ivan")
        self.assertEqual((data["login"], data["hostname"]), ("ivan", "aether-main"))
        self.assertEqual(self.post("tab_close", "0")[0], 404)                              # корень не закрывается

    def test_closing_a_branch_keeps_the_others(self):
        self.run_command("rshell guest@aether-core")
        self.post("tab_focus", "0")
        self.run_command("rshell dig@aether-deep")                                         # вторая ветка от корня
        labels = [row["label"] for row in self.run_command("pwd")["tabs"]]
        self.assertEqual(labels, ["ivan@aether-main", "guest@aether-core", "dig@aether-deep"])
        code, data = self.post("tab_close", "1")
        self.assertEqual([row["label"] for row in data["tabs"]], ["ivan@aether-main", "dig@aether-deep"])
        self.assertEqual(data["effects"], [])
        self.assertEqual(data["login"], "dig")                                             # терминал не был под закрытым

    def test_a_kick_closes_only_the_terminal_branch(self):
        from filesystem.testing import make_file

        self.chain()
        make_file(self.deep, "/home/trap.bin", state="> encrypted x attempts=1\non fail: kick")
        data = self.run_command("ward /home/trap.bin wrong")
        self.assertEqual(data["login"], "guest")
        self.assertEqual(self.where().login, "guest")
        self.assertEqual([row["label"] for row in data["tabs"]], ["ivan@aether-main", "guest@aether-core"])

    def test_xfer_between_tabs_goes_along_the_tree_and_the_scene_shows_the_route(self):
        self.chain()                                    # main -> core -> deep, терминал на deep
        data = self.run_command("xfer ivan@aether-main:/home/notes.txt /home/got.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        text = json.dumps(data["scene"])
        self.assertIn("route", text)
        self.assertIn("ivan@aether-main -> guest@aether-core", text)                    # по полосе на каждый прыжок, по порядку
        self.assertIn("guest@aether-core -> dig@aether-deep", text)
        self.assertLess(text.index("ivan@aether-main -> guest"), text.index("guest@aether-core -> dig"))
        self.assertEqual(text.count('"op": "bar"'), 2)
        self.assertIn("got.txt", self.run_command("ls /home")["output"])

    def test_the_route_follows_the_direction_of_the_transfer(self):
        self.chain()                                    # терминал на deep
        data = self.run_command("xfer /home/deep.dat ivan@aether-main:/home/sent.dat")          # отправка: от deep к main
        text = json.dumps(data["scene"])
        self.assertLess(text.index("dig@aether-deep -> guest@aether-core"), text.index("guest@aether-core -> ivan@aether-main"))

    def test_the_limits_stop_endless_tabs(self):
        self.run_command("rshell guest@aether-core")
        self.run_command("rshell dig@aether-deep")
        self.run_command("rshell relay@aether-core")
        self.run_command("rshell guest@aether-core")
        self.assertIn("too many nested", self.run_command("rshell dig@aether-deep")["output"])


@override_settings(FORCE_SCRIPT_NAME=None)
class ConnectionLimitTests(BridgeFixture):
    """Срок подключения (ttl) записи: обрыв по времени, предупреждения, блокировка после обрыва, обрыв передачи файла."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from filesystem.testing import make_file

        make_file(cls.main, "/home/notes.txt", state="")

    def setUp(self):
        super().setUp()
        from types import SimpleNamespace
        from unittest import mock

        self.now = [1_000_000.0]
        patcher = mock.patch("machines.bridge.time", SimpleNamespace(time=lambda: self.now[0]))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.core_profile = type(self.open_account).objects.get(pk=self.open_account.pk)

    def limit(self, profile, ttl, **extra):
        type(profile).objects.filter(pk=profile.pk).update(ttl=ttl, **extra)

    def tick(self):
        response = self.client.post(reverse("terminal:tick"), data="{}", content_type="application/json")
        return json.loads(response.content)

    def test_a_connection_gets_a_deadline_from_the_ttl_of_the_record(self):
        self.limit(self.open_account, 90)
        data = self.run_command("rcon guest@aether-core")
        rows = {row["label"]: row for row in data["tabs"]}
        self.assertEqual(rows["guest@aether-core"]["deadline"], self.now[0] + 90)
        self.assertIsNone(rows["ivan@aether-main"]["deadline"])                        # у корня срока нет
        self.assertEqual(data["warn_at"], [30, 10])

    def test_after_the_deadline_the_connection_is_closed_and_the_desktop_goes_back(self):
        self.limit(self.open_account, 90, kick_message="Trace complete.\nYour address is known.")
        self.run_command("rcon guest@aether-core")
        self.now[0] += 60
        self.assertEqual(self.tick()["kicks"], [])                                      # ещё живо
        self.now[0] += 31
        data = self.tick()
        (kick,) = data["kicks"]
        self.assertEqual((kick["label"], kick["desktop"]), ("guest@aether-core", True))
        self.assertEqual(kick["message"], "Trace complete.\nYour address is known.")
        self.assertEqual(self.where().login, "ivan")
        self.assertEqual(data["tabs"], [])

    def test_the_default_message_depends_on_the_system(self):
        self.limit(self.open_account, 5)
        self.run_command("rcon guest@aether-core")
        self.now[0] += 6
        (kick,) = self.tick()["kicks"]
        self.assertIn("session time limit exceeded", kick["message"])

    def test_a_command_after_the_deadline_is_not_run_and_reports_the_kick(self):
        self.limit(self.open_account, 10)
        self.run_command("rcon guest@aether-core")
        self.now[0] += 11
        data = self.run_command("ls /home")
        self.assertEqual(len(data["kicks"]), 1)
        self.assertEqual(data["output"], "")
        self.assertEqual(self.where().login, "ivan")

    def test_a_shell_deadline_drops_only_that_shell(self):
        self.limit(self.open_account, 10)
        self.run_command("rshell guest@aether-core")
        self.now[0] += 11
        (kick,) = self.tick()["kicks"]
        self.assertFalse(kick["desktop"])                                              # стол не менялся
        data = self.run_command("pwd")
        self.assertEqual((data["hostname"], data["login"]), ("aether-main", "ivan"))

    def test_the_cooldown_blocks_the_record_until_it_passes(self):
        from datetime import timedelta

        from django.utils import timezone

        self.limit(self.open_account, 10, cooldown=120)
        self.run_command("rcon guest@aether-core")
        self.now[0] += 11
        self.tick()
        data = self.run_command("rcon guest@aether-core")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("account locked", data["output"])
        self.assertIn("retry in 0", data["output"])
        self.assertEqual(self.where().login, "ivan")
        from machines.models import Session

        Session.objects.filter(profile=self.open_account).update(blocked_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.run_command("rcon guest@aether-core")["exit_code"], 0)

    def test_a_transfer_is_cut_when_a_node_on_the_route_expires_before_it_ends(self):
        self.limit(self.open_account, 100)
        self.limit(self.deep_open, 100)
        self.run_command("rcon guest@aether-core")
        self.run_command("rshell dig@aether-deep")
        self.now[0] += 99                                                              # до срока секунда, а прыжок идёт дольше
        data = self.run_command("xfer ivan@aether-main:/home/notes.txt /home/got.txt")
        self.assertEqual(data["exit_code"], 1)
        self.assertIn("connection lost", data["output"])
        self.assertIn("connection lost", json.dumps(data["scene"]))
        self.assertNotIn("got.txt", self.run_command("ls /home")["output"])            # файл не доехал

    def test_a_transfer_that_ends_in_time_goes_through(self):
        self.limit(self.open_account, 100)
        self.run_command("rcon guest@aether-core")
        self.run_command("rshell dig@aether-deep")
        data = self.run_command("xfer ivan@aether-main:/home/notes.txt /home/got.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])


@override_settings(FORCE_SCRIPT_NAME=None)
class NetTests(TestCase):
    """nreq и nget: внутриигровые серверы с узлами по путям, файлы приходят в сессию игрока."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile, NetNode, NetResource
        from filesystem.testing import key_item

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.server = Machine.objects.create(name="Archive", hostname="aether-archive")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
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

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

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


@override_settings(FORCE_SCRIPT_NAME=None)
class TrashTests(TestCase):
    """del, rcvr, wipe: корзина /trash, подтверждение, повреждение при возврате, срок хранения."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt", "/home/docs/x.txt", "/home/docs/y.txt", "/etc/keep.cfg"):
            make_file(cls.main, path, state="")
        make_file(cls.main, "/home/core.sys", state="", system=True)
        make_file(cls.main, "/home/locked.bin", state="> encrypted hunter2")
        make_file(cls.main, "/home/bait.txt", state='> binary utf16\non delete: say "Somebody is watching {name}."')
        make_file(cls.main, "/home/trap.txt", state="> binary utf16\non delete: alert unreachable count=2 gap=100")
        make_file(cls.main, "/home/boom.txt", state="> binary utf16\non delete: drop /home/a.txt")
        make_file(cls.main, "/home/ghost.txt", state='> binary utf16\non restore: say "It remembers you."')
        make_file(cls.main, "/etc", directory=True, system=True)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def post(self, payload):
        response = self.client.post(reverse("terminal:execute"), data=json.dumps(payload), content_type="application/json")
        return json.loads(response.content)

    def run_command(self, text):
        return self.post({"command": text})

    def answer(self, text):
        return self.post({"answer": text})

    def ls(self, path="/home"):
        return self.run_command(f"ls {path}")["output"]

    def test_del_asks_and_a_yes_moves_the_file_to_the_trash(self):
        data = self.run_command("del /home/a.txt")
        self.assertEqual(data["prompt"]["kind"], "confirm")
        self.assertIn("a.txt", self.ls())                                   # пока не подтвердили
        data = self.answer("y")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertNotIn("a.txt", self.ls())
        self.assertIn("a.txt", self.ls("/trash"))

    def test_anything_but_yes_cancels(self):
        self.run_command("del /home/a.txt")
        self.assertEqual(self.answer("n")["output"], "")
        self.assertIn("a.txt", self.ls())
        self.run_command("del /home/a.txt")
        self.post({"cancel": True})
        self.assertIsNone(self.answer("y")["prompt"])                       # отменённый вопрос не оживает
        self.assertIn("a.txt", self.ls())

    def test_force_skips_the_question_and_several_files_work(self):
        data = self.run_command("del -f /home/a.txt /home/b.txt")
        self.assertIsNone(data["prompt"])
        self.assertEqual(self.ls("/trash").split(), ["a.txt", "b.txt"])

    def test_a_folder_needs_r_and_keeps_its_structure(self):
        self.assertIn("Is a directory", self.run_command("del -f /home/docs")["output"])
        self.run_command("del -rf /home/docs")
        self.assertNotIn("docs", self.ls())
        self.assertEqual(self.ls("/trash/docs").split(), ["x.txt", "y.txt"])

    def test_system_files_protected_paths_and_the_trash_cannot_be_deleted(self):
        self.assertIn("Operation not permitted", self.run_command("del -f /home/core.sys")["output"])
        self.assertIn("Operation not permitted", self.run_command("del -rf /home")["output"])        # внутри системный файл и /home защищён
        self.assertIn("Operation not permitted", self.run_command("del -rf /")["output"])
        self.assertIn("Operation not permitted", self.run_command("del -rf /etc")["output"])         # защищён у этой машины
        self.assertIn("core.sys", self.ls())
        self.run_command("del -f /home/a.txt")
        self.assertIn("already in the trash", self.run_command("del -f /trash/a.txt")["output"])
        self.assertIn("No such file", self.run_command("del -f /home/none")["output"])

    def test_a_live_name_in_the_trash_gets_a_numbered_suffix(self):
        self.run_command("del -f /home/a.txt")
        self.run_command("rcvr /trash/a.txt /home/b2.txt")
        self.run_command("del -f /home/b.txt")
        self.run_command("rcvr /trash/b.txt /home/a.txt")
        self.run_command("del -f /home/a.txt")                              # в корзине теперь b.txt под именем a.txt
        self.run_command("del -f /home/b2.txt")
        self.run_command("rcvr /trash/b2.txt /home/a.txt")
        self.run_command("del -f /home/a.txt")
        self.assertEqual(self.ls("/trash").split(), ["a.txt", "a.txt.1"])

    def test_rcvr_returns_the_file_damaged_and_longer_stay_means_more_layers(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        data = self.run_command("rcvr /trash/a.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("a.txt", self.ls())
        self.assertEqual(self.run_command("rpr /home/a.txt")["exit_code"], 0)         # один слой
        self.assertIn("nothing to repair", self.run_command("rpr /home/a.txt")["output"])

        self.run_command("del -f /home/b.txt")
        PlayerFile.objects.filter(path="trash/b.txt").update(trashed_at=timezone.now() - timedelta(days=3, hours=1))
        self.run_command("rcvr /trash/b.txt")
        repaired = [self.run_command("rpr /home/b.txt")["exit_code"] for _ in range(5)]
        self.assertEqual(repaired, [0, 0, 0, 0, 1])                                   # 1 + 3 дня = 4 слоя

    def test_the_number_of_damaged_layers_is_capped(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        PlayerFile.objects.filter(path="trash/a.txt").update(trashed_at=timezone.now() - timedelta(days=6))
        self.run_command("rcvr /trash/a.txt")
        self.assertEqual([self.run_command("rpr /home/a.txt")["exit_code"] for _ in range(7)], [0] * 5 + [1, 1])

    def test_rcvr_errors_and_a_destination(self):
        self.run_command("del -f /home/a.txt /home/b.txt")
        self.assertIn("not in the trash", self.run_command("rcvr /home/a.txt")["output"])
        self.assertIn("No such file", self.run_command("rcvr /trash/none")["output"])
        self.run_command("rcvr /trash/a.txt /home/b.txt")
        self.assertIn("b.txt", self.ls("/trash"))                                      # путь назначения был занят? нет: b.txt в корзине
        self.run_command("rcvr /trash/b.txt /home/moved.txt")
        self.assertIn("moved.txt", self.ls())

    def test_a_folder_comes_back_whole_to_its_old_places(self):
        self.run_command("del -rf /home/docs")
        self.assertEqual(self.run_command("rcvr /trash/docs")["exit_code"], 0)
        self.assertEqual(self.ls("/home/docs").split(), ["x.txt", "y.txt"])
        self.run_command("del -rf /home/docs")
        self.assertIn("a destination can only be given", self.run_command("rcvr /trash/docs /home/other")["output"])

    def test_expired_files_vanish_for_good_and_the_original_does_not_return(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        PlayerFile.objects.filter(path="trash/a.txt").update(purge_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.run_command("rcvr /trash/a.txt")["exit_code"], 1)         # срок вышел: возвращать нечего
        self.assertNotIn("a.txt", self.ls())                                           # машинный файл не вернулся на старое место
        self.assertIn("No such file", self.ls("/trash"))                               # корзина пуста

    def test_wipe_empties_the_trash_after_a_question(self):
        self.run_command("del -f /home/a.txt /home/b.txt")
        data = self.run_command("wipe")
        self.assertEqual(data["prompt"]["kind"], "confirm")
        self.assertIn("2 files removed", self.answer("y")["output"])
        self.assertIn("empty", self.run_command("wipe")["output"])
        self.assertNotIn("a.txt", self.ls())                                           # и со старых мест не вернулись
        self.assertNotIn("b.txt", self.ls())

    def test_the_purge_command_cleans_every_session(self):
        from datetime import timedelta
        from io import StringIO

        from django.core.management import call_command
        from django.utils import timezone

        from filesystem.models import PlayerFile

        self.run_command("del -f /home/a.txt")
        PlayerFile.objects.update(purge_at=timezone.now() - timedelta(minutes=1))
        out = StringIO()
        call_command("purge_trash", stdout=out)
        self.assertIn("purged: 1", out.getvalue())
        self.assertFalse(PlayerFile.objects.filter(purge_at__isnull=False, deleted_at__isnull=True).exists())

    def test_on_delete_runs_the_hooks_of_the_top_layer(self):
        data = self.run_command("del -f /home/bait.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("Somebody is watching bait.txt.", data["output"])
        self.assertIn("bait.txt", self.ls("/trash"))                                    # удалился, как обычно
        self.assertNotIn("Somebody", self.run_command("del -f /home/b.txt")["output"])  # у файла без слоёв хуков нет

    def test_on_delete_can_throw_effects_and_drop_other_files(self):
        data = self.run_command("del -f /home/trap.txt")
        self.assertEqual([e["op"] for e in data["effects"]], ["alert"])
        self.assertEqual(data["effects"][0]["count"], 2)
        self.run_command("del -f /home/boom.txt")
        self.assertNotIn("a.txt", self.ls())                                            # хук убрал и a.txt

    def test_on_restore_sees_the_file_before_the_damage_and_the_damage_still_comes(self):
        self.run_command("del -f /home/ghost.txt")
        data = self.run_command("rcvr /trash/ghost.txt")
        self.assertIn("It remembers you.", data["output"])
        self.assertEqual(self.run_command("rpr /home/ghost.txt")["exit_code"], 0)       # повреждение осталось
        self.assertEqual(self.run_command("cvt enc utf16 /home/ghost.txt")["exit_code"], 0)       # и слой автора под ним цел


@override_settings(FORCE_SCRIPT_NAME=None)
class FileOpsTests(TestCase):
    """mv и cp: перенос и копирование файлов и папок в сессии."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt", "/home/docs/x.txt", "/home/docs/sub/y.txt", "/home/work/w.txt"):
            make_file(cls.main, path, state="")
        make_file(cls.main, "/home/core.sys", state="", system=True)
        make_file(cls.main, "/home/door.bin", state="> encrypted hunter2")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

    def ls(self, path="/home"):
        return self.run_command(f"ls {path}")["output"].split()

    def test_mv_renames_a_file_and_moves_it_into_a_folder(self):
        self.assertEqual(self.run_command("mv /home/a.txt /home/c.txt")["exit_code"], 0)
        self.assertIn("c.txt", self.ls())
        self.assertNotIn("a.txt", self.ls())
        self.run_command("mv /home/c.txt /home/work")
        self.assertEqual(self.ls("/home/work"), ["c.txt", "w.txt"])

    def test_cp_leaves_the_original_and_keeps_the_layers(self):
        self.assertEqual(self.run_command("cp /home/door.bin /home/door2.bin")["exit_code"], 0)
        self.assertIn("door.bin", self.ls())
        self.assertIn("door2.bin", self.ls())
        self.assertEqual(self.run_command("ward /home/door2.bin hunter2")["exit_code"], 0)
        self.assertIn("Bad session key", self.run_command("ward /home/door.bin nope")["output"])      # у оригинала слой на месте

    def test_a_copy_carries_the_progress_made_before_it(self):
        self.run_command("ward /home/door.bin hunter2")
        self.run_command("cp /home/door.bin /home/open.bin")
        self.assertIn("not encrypted", self.run_command("ward /home/open.bin hunter2")["output"])

    def test_folders_need_r_for_cp_and_move_whole(self):
        self.assertIn("omitting directory", self.run_command("cp /home/docs /home/docs2")["output"])
        self.assertEqual(self.run_command("cp -r /home/docs /home/docs2")["exit_code"], 0)
        self.assertEqual(self.ls("/home/docs2/sub"), ["y.txt"])
        self.assertEqual(self.ls("/home/docs/sub"), ["y.txt"])
        self.run_command("mv /home/docs /home/work")
        self.assertNotIn("docs", self.ls())
        self.assertEqual(self.ls("/home/work/docs/sub"), ["y.txt"])

    def test_several_sources_need_a_folder_as_the_target(self):
        self.assertEqual(self.run_command("mv /home/a.txt /home/b.txt /home/work")["exit_code"], 0)
        self.assertEqual(self.ls("/home/work"), ["a.txt", "b.txt", "w.txt"])
        self.assertIn("is not a directory", self.run_command("cp /home/door.bin /home/core.sys /home/nothing")["output"])

    def test_nothing_is_overwritten_and_errors_are_clear(self):
        self.assertIn("exists", self.run_command("mv /home/a.txt /home/b.txt")["output"])
        self.assertIn("exists", self.run_command("cp /home/a.txt /home/b.txt")["output"])
        self.assertIn("No such file", self.run_command("mv /home/none /home/x")["output"])
        self.assertIn("into itself", self.run_command("cp -r /home/docs /home/docs/sub/copy")["output"])
        self.assertIn("the same", self.run_command("mv /home/a.txt /home/a.txt")["output"])
        self.assertIn("No such file", self.run_command("cp /home/a.txt /nowhere/deep/a.txt")["output"])
        self.assertIn("a.txt", self.ls())                                                   # ничего не пропало
        self.assertEqual(self.run_command("mv /home/a.txt")["exit_code"], 2)

    def test_a_system_file_cannot_move_but_its_copy_is_an_ordinary_file(self):
        self.assertIn("Operation not permitted", self.run_command("mv /home/core.sys /home/work")["output"])
        self.assertEqual(self.run_command("cp /home/core.sys /home/work/core.copy")["exit_code"], 0)
        self.assertEqual(self.run_command("del -f /home/work/core.copy")["exit_code"], 0)   # копию удалить можно
        self.assertIn("Operation not permitted", self.run_command("del -f /home/core.sys")["output"])

    def test_the_trash_is_not_a_source_or_a_target(self):
        self.run_command("del -f /home/a.txt")
        self.assertIn("use rcvr", self.run_command("mv /trash/a.txt /home/a.txt")["output"])
        self.assertIn("use del", self.run_command("cp /home/b.txt /trash/b.txt")["output"])



@override_settings(FORCE_SCRIPT_NAME=None)
class RawCommandTests(TestCase):
    """blk, txtx и cvt работают с настоящими данными файла (запись вики) и слоями поверх них."""

    BODY = "Cargo manifest altered.\n\nRef A-113."

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile
        from filesystem.testing import make_page

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
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

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

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
        from machines.models import MachineApp, MachineMount, Session
        from wiki.testing import make_document, make_namespace

        MachineApp.objects.create(machine=self.main, label="wiki", glyph="W", path="/apps/wiki/")
        section = make_namespace("Section")
        make_document(section, "Gated", type="rec", body="x", access={"all": ["secret_a"]})
        MachineMount.objects.create(machine=self.main, volume=section.volume, mount_path="", order=5)
        self.keyed_file()
        offset = self.offset_of_block("/home/keyed.rec")
        session = Session.objects.get(user=self.user)
        stored = self.client.session
        stored["machine_session_id"] = session.pk
        stored.save()
        self.assertEqual(self.client.get("/apps/wiki/Section/Gated").status_code, 403)
        self.run_command(f"kex /home/keyed.rec {offset}")
        self.assertEqual(self.client.get("/apps/wiki/Section/Gated").status_code, 200)
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
        from terminal.scenes import convert_scene, decode_scene

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


@override_settings(FORCE_SCRIPT_NAME=None)
class ArchiveTests(TestCase):
    """Архив это файл с расширением, под путём которого лежат другие файлы: pak l, pak x, pak pass."""

    BODY = "Cargo manifest altered.\n\nRef A-113."

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile
        from filesystem.testing import make_page

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
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

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

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
        from filesystem.rawview import formats

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
class SignatureTests(TestCase):
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
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
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

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

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
class WardKeyTests(TestCase):
    """ward расшифровывает паролем или ключом из /home/.secrets; зашифрованный файл в байтах выглядит как PGP."""

    BODY = "Cargo manifest altered.\n\nRef A-113."

    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file
        from machines.models import MachineProfile
        from filesystem.testing import key_item
        from filesystem.testing import make_page

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
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

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

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
        from filesystem.rawview import keys

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
        from filesystem.rawview import keys

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



@override_settings(FORCE_SCRIPT_NAME=None)
class HelpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.user)

    def run_command(self, text):
        response = self.client.post(
            reverse("terminal:execute"), data=json.dumps({"command": text}), content_type="application/json"
        )
        return json.loads(response.content)

    def test_every_command_of_the_system_has_help_text(self):
        from terminal.engine.commands import COMMANDS
        from terminal.engine.commands.help import HELP

        for name in COMMANDS:
            self.assertIn(name, HELP, f"нет справки для {name}")
            summary, synopsis, _ = HELP[name]
            self.assertTrue(summary and synopsis, name)
        for name in HELP:
            self.assertIn(name, COMMANDS, f"справка для несуществующей команды {name}")

    def test_help_speaks_about_the_tools_not_about_the_game(self):
        from terminal.engine.commands.help import HELP

        forbidden = ("layer", "shifted", "puzzle", "game", "real file", "real data", "player", "hint", "solve")
        for name, (summary, synopsis, details) in HELP.items():
            text = " ".join([summary, *synopsis, details]).lower()
            for word in forbidden:
                self.assertNotIn(word, text, f"{name}: справка выдаёт механику ({word})")

    def test_help_lists_the_commands_in_groups(self):
        data = self.run_command("help")
        self.assertEqual(data["exit_code"], 0)
        for name in ("ls", "cnt", "blk", "cvt", "ward", "pak", "kex", "rcon", "help"):
            self.assertIn(name, data["output"])
        self.assertIn("keys and archives:", data["output"])
        self.assertIn("help <command>", data["output"])

    def test_help_about_a_command_shows_usage_and_details(self):
        data = self.run_command("help cvt")
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("cvt ext <file> <out.ext>", data["output"])
        self.assertIn("cvt enc <encoding> <file>", data["output"])
        self.assertIn("usage:", data["output"])
        self.assertEqual(self.run_command("help nothing")["exit_code"], 1)
        self.assertIn("no such command", self.run_command("help nothing")["output"])
        self.assertEqual(self.run_command("help a b")["exit_code"], 2)
