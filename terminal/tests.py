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
