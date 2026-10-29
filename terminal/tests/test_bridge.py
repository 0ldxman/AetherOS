"""Мосты: rcon, rshell, вкладки терминала, срок подключения.

Запуск: python manage.py test terminal.tests.test_bridge
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import key_item, make_app, make_file
from machines.models import Machine
from terminal.testing import TerminalClient


@override_settings(FORCE_SCRIPT_NAME=None)
class BridgeFixture(TerminalClient, TestCase):
    """Машины, записи и помощники для проверки входа на другие машины."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.hashers import make_password

        from filesystem.testing import make_file
        from machines.models import EntryPolicy, MachineProfile, MachineProfileToken
        from filesystem.testing import key_item

        cls.main = Machine.objects.create(name="Main", hostname="aether-main", hid="AA:00:00:00:00:01")
        cls.core = Machine.objects.create(name="Core", hostname="aether-core", hid="AA:00:00:00:00:02")
        cls.deep = Machine.objects.create(name="Deep", hostname="aether-deep", hid="AA:00:00:00:00:03")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
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
        cls.walled = account(cls.core, "walled", entry_policy=EntryPolicy.objects.create(name="walled", sources="somewhere-else"))
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
        from machines.network import bridge

        return bridge.depth(self.request())

    def shells(self):
        """Подключений от рабочего стола до терминала (оболочки, у которых рабочий стол остался позади)."""
        from machines.network import bridge

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
        patcher = mock.patch("machines.network.bridge.time", SimpleNamespace(time=lambda: self.now[0]))
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
