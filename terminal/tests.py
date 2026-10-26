"""Терминал: безымянный игрок видит окно, но команды отвечают ошибкой авторизации.

Запуск: python manage.py test terminal
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

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
        from filesystem.models import SessionFile

        self.witness()
        self.run_command("ls")
        self.assertEqual(SessionFile.objects.count(), 0)

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
        from filesystem.models import MachineFile
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        MachineFile.objects.create(machine=cls.main, path="/home/door.bin", state="> encrypted hunter2 attempts=3")
        MachineFile.objects.create(machine=cls.main, path="/home/note.txt", state="> base64")
        MachineFile.objects.create(machine=cls.main, path="/home/pack.dat", state="> archive")
        MachineFile.objects.create(machine=cls.main, path="/home/blob.bin", state="> binary")
        MachineFile.objects.create(machine=cls.main, path="/home/slice.img", state="> shifted skip=2 count=5")
        MachineFile.objects.create(machine=cls.main, path="/home/report.txt", state="> disguised pdf")

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
        self.assertIn("wrong", data["output"])                # текст ответа остаётся

    def test_the_right_password_ends_with_success(self):
        data = self.run_command("ward /home/door.bin hunter2")
        self.assertEqual(data["exit_code"], 0)
        done = [step for step in data["scene"] if step["op"] == "dots"]
        self.assertEqual(done[-1]["status"], "OK")
        self.assertIn("decrypted", data["output"])

    def test_each_layer_has_its_own_command(self):
        for command, expected in (
            ("enc /home/note.txt", "decoded"),
            ("pak /home/pack.dat", "unpacked"),
            ("txtx /home/blob.bin", "text extracted"),
            ("blk /home/slice.img 2 5", "blocks read"),
            ("cvt /home/report.txt PDF", "converted"),
        ):
            data = self.run_command(command)
            self.assertEqual(data["exit_code"], 0, command)
            self.assertIn(expected, data["output"])
            self.assertIsNotNone(data["scene"])

    def test_the_wrong_values_do_not_open_the_layer(self):
        self.assertEqual(self.run_command("blk /home/slice.img 1 5")["exit_code"], 1)
        self.assertEqual(self.run_command("cvt /home/report.txt docx")["exit_code"], 1)
        self.assertIn("not an archive", self.run_command("pak /home/report.txt")["output"])

    def test_the_old_names_are_gone(self):
        for name in ("cph", "b256", "bridge"):
            self.assertIn("command not found", self.run_command(f"{name} /home/door.bin x")["output"])

    def test_ftyp_and_cnt_play_a_short_scene_that_gives_nothing_away(self):
        from filesystem.models import MachineFile

        MachineFile.objects.create(machine=self.main, path="/home/page.txt", state="", url="apps/wiki/")
        plain, locked = self.run_command("ftyp /home/page.txt"), self.run_command("ftyp /home/door.bin")
        self.assertEqual(self.ops(plain["scene"]), self.ops(locked["scene"]))
        self.assertEqual(plain["output"], "/home/page.txt: data")
        opened = self.run_command("cnt /home/page.txt")
        self.assertEqual(opened["exit_code"], 0)
        self.assertEqual([s for s in opened["scene"] if s["op"] == "dots"][-1]["status"], "OK")
        blocked = self.run_command("cnt /home/door.bin")
        self.assertEqual([s for s in blocked["scene"] if s["op"] == "dots"][-1]["status"], "FAIL")
        self.assertIsNone(self.run_command("ftyp /home/missing")["scene"])               # ошибка до начала работы
        self.assertIsNone(self.run_command("ftyp /home")["scene"])                       # папка: работы нет

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

        from filesystem.models import FileKey, MachineFile
        from machines.models import MachineProfile, MachineProfileHID, MachineProfileToken
        from secure.models import Key

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

        key = Key.objects.create(slug="cardkey")
        card = MachineFile.objects.create(machine=cls.main, path="/home/card.key", state="")
        FileKey.objects.create(file=card, key=key)
        locked = MachineFile.objects.create(machine=cls.main, path="/home/locked.key", state="> encrypted hunter2")
        FileKey.objects.create(file=locked, key=key)
        MachineFile.objects.create(machine=cls.main, path="/home/trap.bin", state="> encrypted hunter2 attempts=1\non fail: kick")
        MachineFile.objects.create(machine=cls.main, path="/home/noise.bin",
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

    def depth(self):
        return len(self.client.session.get("bridge_stack", []))

    def shells(self):
        return len(self.client.session.get("rshell_stack", []))


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

    def test_a_key_account_needs_the_key_file(self):
        self.assertIn("Permission denied (publickey)", self.run_command("rcon badge@aether-core")["output"])
        self.assertIn("not found", self.run_command("rcon -i /home/none.key badge@aether-core")["output"])
        self.assertIn("invalid format", self.run_command("rcon -i /home/locked.key badge@aether-core")["output"])
        self.assertEqual(self.run_command("rcon -i /home/card.key badge@aether-core")["exit_code"], 0)
        self.assertEqual(self.where().login, "badge")

    def test_a_password_and_key_account_needs_both(self):
        data = self.run_command("rcon ops@aether-core")                        # без ключа: пароль всё равно спросят
        self.assertEqual(data["prompt"]["kind"], "password")
        self.assertIn("Permission denied (publickey,password)", self.answer("s3cret")["output"])
        self.assertEqual(self.depth(), 0)

        self.run_command("rcon -i /home/card.key ops@aether-core")
        self.assertIn("Permission denied", self.answer("nope")["output"])        # ключ есть, пароль неверный

        self.run_command("rcon -i /home/card.key ops@aether-core")
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
        from filesystem.models import MachineFile

        MachineFile.objects.create(machine=self.core, path="/home/trap.bin",
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
        from filesystem.models import MachineFile

        MachineFile.objects.create(machine=cls.main, path="/home/notes.txt", state="")
        MachineFile.objects.create(machine=cls.main, path="/home/work/a.txt", state="")
        MachineFile.objects.create(machine=cls.main, path="/home/vault.bin", state="> encrypted hunter2")
        MachineFile.objects.create(machine=cls.core, path="/home/loot.dat", state="> archive")
        MachineFile.objects.create(machine=cls.core, path="/home/docs/readme.txt", state="")

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

    def test_rcon_is_refused_inside_a_shell_but_shells_nest_in_a_tunnel(self):
        self.run_command("rshell guest@aether-core")
        self.assertIn("exit it first", self.run_command("rcon dig@aether-deep")["output"])
        self.run_command("rcon-close")
        self.assertEqual((self.depth(), self.shells()), (0, 0))
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
        self.assertEqual(self.run_command("pak /home/got.dat")["exit_code"], 0)    # слой переехал вместе с файлом

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
        from filesystem.models import MachineFile

        MachineFile.objects.create(machine=self.core, path="/home/trap2.bin", state="> encrypted x attempts=1\non fail: kick")
        data = self.run_command("ward /home/trap2.bin wrong")
        self.assertEqual(self.shells(), 0)
        self.assertNotIn({"op": "switch"}, data["effects"])
        self.assertEqual(data["hostname"], "aether-main")



@override_settings(FORCE_SCRIPT_NAME=None)
class NetTests(TestCase):
    """nreq и nget: внутриигровые серверы с узлами по путям, файлы приходят в сессию игрока."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.models import MachineFile
        from machines.models import MachineProfile, NetNode, NetResource
        from secure.models import Key

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.server = Machine.objects.create(name="Archive", hostname="aether-archive")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        MachineFile.objects.create(machine=cls.main, path="/home/own.txt", state="")
        ledger = MachineFile.objects.create(machine=cls.server, path="/srv/ledger.dat", state="> encrypted hunter2")
        report = MachineFile.objects.create(machine=cls.server, path="/srv/report.txt", state="")

        site = NetResource.objects.create(address="Apollo.com/", title="Apollo")
        cls.site = site
        NetNode.objects.create(resource=site, path="", response="APOLLO\n{listing}\nbye")
        NetNode.objects.create(resource=site, path="info")                                   # без текста: один список
        NetNode.objects.create(resource=site, path="info/file.pdf", file=ledger)
        NetNode.objects.create(resource=site, path="info/file2.png", file=report)
        NetNode.objects.create(resource=site, path="info/attachements/a.txt", file=report)    # папка только по пути
        NetNode.objects.create(resource=site, path="info/data", response="DATA SECTION")      # текст без {listing}
        NetNode.objects.create(resource=site, path="info/data/x.bin", file=report)
        NetNode.objects.create(resource=site, path="private", response="members", token="sesame")
        NetNode.objects.create(resource=site, path="info/own.txt", file=MachineFile.objects.get(path="/home/own.txt"))
        NetNode.objects.create(resource=site, path="info/hidden.txt", file=report, key_condition="nokey")
        Key.objects.create(slug="nokey")

        radio = NetResource.objects.create(address="14.230")
        NetNode.objects.create(resource=radio, path="", response="RELAY")
        ftp = NetResource.objects.create(address="FTP://apollo.com")
        NetNode.objects.create(resource=ftp, path="", response="FTP READY")
        NetNode.objects.create(resource=ftp, path="pub/tool.bin", file=report)
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
        self.assertIn("wrong", self.run_command("ward /home/file.pdf nope")["output"])

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
        from filesystem.models import MachineFile, ProtectedPath
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt", "/home/docs/x.txt", "/home/docs/y.txt", "/etc/keep.cfg"):
            MachineFile.objects.create(machine=cls.main, path=path, state="")
        MachineFile.objects.create(machine=cls.main, path="/home/core.sys", state="", system=True)
        MachineFile.objects.create(machine=cls.main, path="/home/locked.bin", state="> encrypted hunter2")
        MachineFile.objects.create(machine=cls.main, path="/home/bait.txt", state='> base64\non delete: say "Somebody is watching {name}."')
        MachineFile.objects.create(machine=cls.main, path="/home/trap.txt", state="> base64\non delete: alert unreachable count=2 gap=100")
        MachineFile.objects.create(machine=cls.main, path="/home/boom.txt", state="> base64\non delete: drop /home/a.txt")
        MachineFile.objects.create(machine=cls.main, path="/home/ghost.txt", state='> base64\non restore: say "It remembers you."')
        ProtectedPath.objects.create(path="/etc", machine=cls.main)

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

        from filesystem.models import SessionFile

        self.run_command("del -f /home/a.txt")
        data = self.run_command("rcvr /trash/a.txt")
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("a.txt", self.ls())
        self.assertEqual(self.run_command("rpr /home/a.txt")["exit_code"], 0)         # один слой
        self.assertIn("nothing to repair", self.run_command("rpr /home/a.txt")["output"])

        self.run_command("del -f /home/b.txt")
        SessionFile.objects.filter(path="/trash/b.txt").update(trashed_at=timezone.now() - timedelta(days=3, hours=1))
        self.run_command("rcvr /trash/b.txt")
        repaired = [self.run_command("rpr /home/b.txt")["exit_code"] for _ in range(5)]
        self.assertEqual(repaired, [0, 0, 0, 0, 1])                                   # 1 + 3 дня = 4 слоя

    def test_the_number_of_damaged_layers_is_capped(self):
        from datetime import timedelta

        from django.utils import timezone

        from filesystem.models import SessionFile

        self.run_command("del -f /home/a.txt")
        SessionFile.objects.filter(path="/trash/a.txt").update(trashed_at=timezone.now() - timedelta(days=6))
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

        from filesystem.models import SessionFile

        self.run_command("del -f /home/a.txt")
        SessionFile.objects.filter(path="/trash/a.txt").update(purge_at=timezone.now() - timedelta(minutes=1))
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

        from filesystem.models import SessionFile

        self.run_command("del -f /home/a.txt")
        SessionFile.objects.update(purge_at=timezone.now() - timedelta(minutes=1))
        out = StringIO()
        call_command("purge_trash", stdout=out)
        self.assertIn("purged: 1", out.getvalue())
        self.assertFalse(SessionFile.objects.filter(purge_at__isnull=False, deleted_at__isnull=True).exists())

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
        self.assertEqual(self.run_command("enc /home/ghost.txt")["exit_code"], 0)       # и слой автора под ним цел


@override_settings(FORCE_SCRIPT_NAME=None)
class FileOpsTests(TestCase):
    """mv и cp: перенос и копирование файлов и папок в сессии."""

    @classmethod
    def setUpTestData(cls):
        from filesystem.models import MachineFile
        from machines.models import MachineProfile

        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        MachineApp.objects.create(machine=cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1,
                                      mail="ivan@aether-main")
        for path in ("/home/a.txt", "/home/b.txt", "/home/docs/x.txt", "/home/docs/sub/y.txt", "/home/work/w.txt"):
            MachineFile.objects.create(machine=cls.main, path=path, state="")
        MachineFile.objects.create(machine=cls.main, path="/home/core.sys", state="", system=True)
        MachineFile.objects.create(machine=cls.main, path="/home/door.bin", state="> encrypted hunter2")

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
        self.assertIn("wrong", self.run_command("ward /home/door.bin nope")["output"])      # у оригинала слой на месте

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

