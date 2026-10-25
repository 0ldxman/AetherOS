"""Рабочий стол: подпись подключения, ключ раскладки, пункты меню панели.

Запуск: python manage.py test desktop
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from machines.models import Machine


@override_settings(FORCE_SCRIPT_NAME=None)
class DesktopTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        self.null = Machine.objects.create(name="Null", hostname="aether-null")
        self.user = get_user_model().objects.create_user("ivan", password="pw")

    def page(self):
        return self.client.get(reverse("desktop"))

    def test_player_sees_login_at_machine(self):
        self.client.force_login(self.user)
        response = self.page()
        self.assertContains(response, "ivan@aether-main")

    def test_layout_key_is_per_player_and_machine(self):
        self.client.force_login(self.user)
        self.assertContains(self.page(), f'data-layout-key="u{self.user.pk}-m{self.main.pk}"')

    def test_other_player_gets_another_layout_key(self):
        other = get_user_model().objects.create_user("petr", password="pw")
        self.client.force_login(other)
        self.assertContains(self.page(), f'data-layout-key="u{other.pk}-m{self.main.pk}"')

    def test_player_menu_has_sessions_reset_and_disconnect(self):
        self.client.force_login(self.user)
        response = self.page()
        self.assertContains(response, 'data-action="sessions"')
        self.assertContains(response, 'data-action="reset-layout"')
        self.assertContains(response, 'data-action="disconnect"')
        self.assertContains(response, f'data-logout-url="{reverse("logout")}"')
        self.assertContains(response, f'data-lock-url="{reverse("lock")}"')

    def test_guest_has_no_sessions_entry(self):
        session = self.client.session
        session["guest"] = True
        session.save()
        response = self.page()
        self.assertContains(response, "guest@aether-null")
        self.assertContains(response, 'data-layout-key="guest-m')
        self.assertNotContains(response, 'data-action="sessions"')
        self.assertContains(response, 'data-action="disconnect"')

    def test_anonymous_is_sent_to_boot(self):
        self.assertRedirects(self.page(), reverse("boot"), fetch_redirect_response=False)

    def test_csrf_cookie_is_set_for_the_disconnect_request(self):
        self.client.force_login(self.user)
        self.assertIn("csrftoken", self.page().cookies)


class UrlPrefixTests(TestCase):
    """Адреса из reverse() уже содержат префикс: добавлять его второй раз нельзя."""

    def test_menu_urls_are_not_prefixed_twice(self):
        previous = get_script_prefix()
        set_script_prefix("/proxy/8000/")
        self.addCleanup(set_script_prefix, previous)
        self.assertEqual(reverse("logout"), "/proxy/8000/auth/logout/")

        from django.test import RequestFactory
        from desktop import views

        Machine.objects.create(name="Main", hostname="aether-main")
        user = get_user_model().objects.create_user("ivan", password="pw")
        request = RequestFactory().get("/desktop/")
        request.user = user
        request.session = {}
        response = views.desktop(request)
        body = response.content.decode()
        self.assertIn('data-logout-url="/proxy/8000/auth/logout/"', body)
        self.assertNotIn("/proxy/8000/proxy/8000", body)


def boot_config(response):
    """Данные, которые страница отдаёт скрипту (json_script boot-config)."""
    import json
    import re

    body = response.content.decode()
    raw = re.search(r'<script id="boot-config" type="application/json">(.*?)</script>', body, re.S).group(1)
    return json.loads(raw)


def steps(scene, op):
    """Все шаги с этим op, включая вложенные (one_of)."""
    found = []
    for step in scene:
        if step["op"] == op:
            found.append(step)
        for nested in step.get("scenes", []):
            found += steps(nested, op)
    return found


def spoken(scene):
    """Весь текст сцены одной строкой (для поиска слов)."""
    import json

    return json.dumps(scene, ensure_ascii=False)


@override_settings(FORCE_SCRIPT_NAME=None)
class LockScreenTests(TestCase):
    """Экран входа: страница-оболочка для консольных сцен."""

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def test_page_is_a_shell_for_the_console_player(self):
        response = self.client.get(reverse("lock"))
        self.assertContains(response, 'id="boot-screen"')
        self.assertContains(response, 'id="boot-output"')
        self.assertContains(response, "ui/console.js")
        self.assertContains(response, "ui/console.css")
        self.assertContains(response, "boot/lock.js")
        self.assertContains(response, "boot/boot.css")

    def test_scripts_are_deferred_so_aether_namespace_exists(self):
        # utils.js и console.js defer: lock.js обязан идти после них, иначе Aether.console ещё нет
        body = self.client.get(reverse("lock")).content.decode()
        self.assertRegex(body, r'console\.js"\s+defer')
        self.assertRegex(body, r'lock\.js"\s+defer')

    def test_anonymous_gets_the_connection_scenes_but_no_restored_scene(self):
        scenes = boot_config(self.client.get(reverse("lock")))["scenes"]
        self.assertEqual(set(scenes), {"intro", "intro_known", "menu", "discord", "bypass", "established", "error"})

    def test_stylesheets_use_only_design_tokens(self):
        # tokens.css: хардкод цвета вне него считается багом (другая машина останется «от старой»)
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        for path in (root / "desktop/static/boot/lock.css", root / "static/ui/console.css"):
            css = path.read_text(encoding="utf-8")
            self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", css), [], path.name)
            self.assertNotIn(":root", css, path.name)
            self.assertNotRegex(css, r"rgba?\(", path.name)


class GatewayScenesTests(TestCase):
    """Содержание сцен входа: этапы, замазанный владелец, общий hid, глюк имени на месте."""

    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")

    def scenes(self, user=None, session=None):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from users.aether_auth import gateway_scenes

        request = RequestFactory().get("/lock/")
        request.user = user or AnonymousUser()
        request.session = session if session is not None else {}
        return gateway_scenes(request)

    def texts(self, scene):
        return [s.get("value", "") for s in scene if s["op"] == "text"]

    def after_last_clear(self, scene):
        index = max(i for i, step in enumerate(scene) if step["op"] == "cut")
        return scene[index + 1:]

    # ---------- чего на экране быть не должно ----------

    def test_the_owner_organisation_is_never_named(self):
        for name, scene in self.scenes().items():
            self.assertNotIn("CTRG", spoken(scene), name)

    def test_no_inbound_message_and_no_printed_mismatch(self):
        # незнакомец говорит прямо в меню, а смена имени это глюк самого текста, а не строка «mismatch -> »
        for name, scene in self.scenes().items():
            text = spoken(scene)
            for word in ("inbound", "MISMATCH", "channel opened", "->"):
                self.assertNotIn(word, text, f"{name}: {word}")

    # ---------- этапы ----------

    def test_intro_is_six_stages_split_by_mode_changes(self):
        intro = self.scenes()["intro"]
        self.assertEqual(sum(1 for s in intro if s["op"] == "cut"), 5)
        titles = [t for t in self.texts(intro) if t.startswith("-- ") and "/7" in t]
        self.assertEqual(
            titles,
            [
                "-- 1/7  resolve --", "-- 2/7  transport --", "-- 3/7  key exchange --",
                "-- 4/7  identity --", "-- 5/7  node --", "-- 6/7  access --",
            ],
        )

    def test_the_session_is_the_seventh_stage(self):
        self.assertIn("-- 7/7  session --", self.texts(self.scenes()["bypass"]))

    def test_each_stage_reprints_the_header(self):
        intro = self.scenes()["intro"]
        self.assertEqual(sum(1 for t in self.texts(intro) if t == "AETHER LINK 3.2"), 6)

    def test_connection_has_real_steps_not_just_a_banner(self):
        text = spoken(self.scenes()["intro"])
        for word in ("resolver", "AAAA", "path mtu", "alp/3.2", "certificate chain", "host key",
                     "key id", "auth      offered by node", "no client key"):
            self.assertIn(word, text)

    def test_key_exchange_has_a_progress_bar_and_a_key_id(self):
        from users.gateway import KEY_ID

        intro = self.scenes()["intro"]
        self.assertEqual(len(steps(intro, "bar")), 1)
        self.assertIn(KEY_ID, spoken(intro))

    def test_route_includes_a_timeout_and_a_retry(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("no answer", text)
        self.assertEqual(text.count("relay 03"), 2)

    def test_the_certificate_issuer_and_the_owner_are_masked(self):
        text = spoken(self.scenes()["intro"])
        self.assertGreaterEqual(text.count("█" * 14), 3)    # издатель, второй сертификат, владелец
        self.assertIn("[restricted]", text)

    def test_owner_field_is_masked_and_marked_restricted(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("█" * 14, text)
        self.assertIn("[restricted]", text)

    def test_trust_prompt_is_typed_by_the_player_like_a_human(self):
        typed = [s for s in self.scenes()["intro"] if s["op"] == "type"]
        self.assertEqual([(s["value"], s["human"]) for s in typed], [("y", True)])

    def test_the_prompt_shows_a_cursor_because_the_console_waits(self):
        prompt = [s for s in self.scenes()["intro"] if s.get("cursor")]
        self.assertEqual(len(prompt), 1)
        self.assertIn("[y/n]", prompt[0]["value"])

    def test_a_known_node_does_not_ask_again(self):
        known = self.scenes()["intro_known"]
        self.assertEqual([s for s in known if s["op"] == "type"], [])
        self.assertNotIn("Trust this node", spoken(known))
        self.assertIn("matches contacts", spoken(known))
        self.assertEqual(len(steps(known, "choice")), 1)

    # ---------- hid ----------

    def test_hid_is_read_from_the_machine_and_shown_before_and_after(self):
        scenes = self.scenes()
        self.assertIn(self.machine.hid, spoken(scenes["intro"]))
        self.assertIn(self.machine.hid, spoken(scenes["bypass"]))

    def test_hid_has_a_placeholder_when_the_machine_is_missing(self):
        from machines.identity import UNKNOWN_HID

        Machine.objects.all().delete()
        self.assertIn(UNKNOWN_HID, spoken(self.scenes()["intro"]))

    # ---------- вход и фраза незнакомца ----------

    def test_discord_is_immediate_and_the_stranger_text_arrives_later_in_place(self):
        from users.gateway import VOICE, VOICE_AFTER_MS

        (choice,) = [s for s in self.scenes()["intro"] if s["op"] == "choice"]
        discord, bypass = choice["options"]
        self.assertNotIn("late", discord)
        self.assertEqual(bypass["late"]["after_ms"], VOICE_AFTER_MS)
        self.assertEqual(bypass["keys"], ["?", "/"])
        self.assertEqual(bypass["label"], list(VOICE))   # случайная из набора, в первом лице

    def test_the_text_is_erased_and_typed_again_if_the_player_waits(self):
        from users.gateway import VOICE_AGAIN, VOICE_AGAIN_MS

        (choice,) = [s for s in self.scenes()["intro"] if s["op"] == "choice"]
        rewrites = choice["options"][1]["rewrites"]
        self.assertEqual(rewrites["after_ms"], list(VOICE_AGAIN_MS))
        self.assertEqual(rewrites["labels"], list(VOICE_AGAIN))
        self.assertGreaterEqual(len(rewrites["labels"]), 2)

    def test_after_a_failed_bypass_the_menu_shows_both_options_at_once(self):
        (choice,) = [s for s in self.scenes()["menu"] if s["op"] == "choice"]
        self.assertEqual([o["id"] for o in choice["options"]], ["discord", "bypass"])
        self.assertTrue(all("late" not in o and "rewrites" not in o for o in choice["options"]))

    # ---------- имя узла глючит на месте ----------

    def test_only_main_turns_into_null_so_the_prefix_stays_put(self):
        from machines.identity import ENTRY_HOST
        from users.gateway import NULL_HOST

        host, null = ENTRY_HOST, NULL_HOST
        prefix = 0
        while host[prefix] == null[prefix]:
            prefix += 1
        self.assertEqual(host[:prefix], "aether-")

    def test_the_glitch_acts_on_the_header_that_is_on_screen_at_that_moment(self):
        scenes = self.scenes()
        # перед выбором на экране шапка этапа 4 с именем узла (id host)...
        on_screen = {s["id"] for s in self.after_last_clear(scenes["intro"]) if s["op"] == "text" and "id" in s}
        self.assertIn("host", on_screen)
        (glitch,) = steps(scenes["bypass"], "glitch")
        self.assertEqual((glitch["id"], glitch["to"]), ("host", "aether-null"))
        # ...а после смены экран очищается и новая шапка уже с aether-null и тем же chassis
        after = self.after_last_clear(scenes["bypass"])
        self.assertIn("aether-null", [s.get("value") for s in after if s["op"] == "text"])
        self.assertIn(self.machine.hid, spoken(after))

    def test_failure_glitches_the_name_back_on_the_current_header(self):
        scenes = self.scenes()
        ids = {s["id"] for s in self.after_last_clear(scenes["bypass"]) if s["op"] == "text" and "id" in s}
        (glitch,) = steps(scenes["error"], "glitch")
        self.assertIn(glitch["id"], ids)
        self.assertEqual(glitch["to"], "aether-main")

    def test_the_glitch_is_long_enough_to_notice(self):
        (glitch,) = steps(self.scenes()["bypass"], "glitch")
        self.assertGreaterEqual(glitch["frames"], 24)

    # ---------- сессия ----------

    def test_the_session_is_only_announced_after_the_server_confirms(self):
        scenes = self.scenes()
        self.assertNotIn("session established", spoken(scenes["bypass"]))
        self.assertNotIn("Loading workspace", spoken(scenes["bypass"]))
        established = spoken(scenes["established"])
        self.assertIn("session established", established)
        self.assertIn("L0 (PUBLIC)", established)
        self.assertIn("not registered", established)

    def test_error_scene_has_a_placeholder_for_the_status(self):
        self.assertIn("{code}", spoken(self.scenes()["error"]))

    def test_logged_in_player_gets_a_restored_scene(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        text = spoken(self.scenes(user=user)["restored"])
        self.assertIn("ivan", text)
        self.assertIn("aether-main", text)
        self.assertNotIn("Unregistered", text)

    def test_returning_guest_restores_onto_aether_null(self):
        text = spoken(self.scenes(session={"guest": True})["restored"])
        self.assertIn("aether-null", text)
        self.assertIn("Unregistered session", text)


@override_settings(FORCE_SCRIPT_NAME=None)
class BootScreenTests(TestCase):
    """Загрузка машины: консольная сцена Aether, полная и короткая."""

    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(name="Main", hostname="aether-main")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def scenes(self):
        return boot_config(self.client.get(reverse("boot")))["scenes"]

    def test_page_is_a_shell_for_the_console_player(self):
        response = self.client.get(reverse("boot"))
        self.assertContains(response, 'id="boot-output"')
        self.assertContains(response, "ui/console.js")
        self.assertRegex(response.content.decode(), r'boot\.js"\s+defer')

    def test_page_carries_a_full_and_a_short_boot(self):
        scenes = self.scenes()
        self.assertEqual(set(scenes), {"full", "short"})
        self.assertGreater(len(scenes["full"]), len(scenes["short"]))

    def test_full_boot_has_all_stages_and_the_short_one_only_connect_and_units(self):
        scenes = self.scenes()
        full, short = spoken(scenes["full"]), spoken(scenes["short"])
        for word in ("AETHER FIRMWARE", "AEBOOT", "aether kernel", "keyagent"):
            self.assertIn(word, full)
        self.assertIn("keyagent", short)
        for word in ("AETHER FIRMWARE", "AEBOOT", "aether kernel"):
            self.assertNotIn(word, short)

    def test_firmware_is_a_modern_uefi_with_signatures_not_an_old_bios(self):
        full = spoken(self.scenes()["full"])
        for word in ("uefi", "secure boot", "tpm 2.0", "measured boot", "sha256:", "nvme0"):
            self.assertIn(word, full)
        for word in ("BIOS", "Press <DEL>", "Memory Testing"):
            self.assertNotIn(word, full)

    def test_aether_is_not_linux(self):
        full = spoken(self.scenes()["full"]).lower()
        for word in ("linux", "systemd", "dmesg", "ttys0", "[  ok  ]", "started "):
            self.assertNotIn(word, full)
        for word in ("aek", "aeinit", "aemc", "aefs"):
            self.assertIn(word, full)

    def test_the_machine_belongs_to_the_alternate_2020_not_to_2061(self):
        full = spoken(self.scenes()["full"])
        self.assertIn("2020", full)
        self.assertNotIn("2061", full)

    def test_the_boot_shows_the_same_machine_as_the_entry_screen(self):
        from machines.identity import serial_for

        full = spoken(self.scenes()["full"])
        self.assertIn("aether-main", full)
        self.assertIn(self.machine.hid, full)                  # MAC сетевого адаптера
        self.assertIn(serial_for(self.machine.hid), full)
        lock = spoken(boot_config(self.client.get(reverse("lock")))["scenes"]["intro"])
        self.assertIn(self.machine.hid, lock)
        self.assertIn(serial_for(self.machine.hid), lock)

    def test_boot_uses_the_toolkit_not_just_text(self):
        full = self.scenes()["full"]
        self.assertEqual(len(steps(full, "count")), 1)         # память
        self.assertEqual(len(steps(full, "bar")), 1)           # загрузка образа
        self.assertGreaterEqual(len(steps(full, "spin")), 11)  # службы и задачи ядра
        self.assertGreaterEqual(len(steps(full, "cut")), 4)    # смена режима между этапами
        self.assertEqual(full[-1]["op"], "cut")                # чёрный кадр перед переходом

    def test_times_are_ranges_so_two_boots_are_not_identical(self):
        ranges = [s["ms"] for s in steps(self.scenes()["full"], "spin") if isinstance(s["ms"], list)]
        self.assertGreaterEqual(len(ranges), 8)

    def test_the_cursor_is_only_where_the_console_waits(self):
        typed = steps(self.scenes()["full"], "type")
        self.assertEqual([s["value"] for s in typed], ["aemc attach aether-main"])

    def test_units_show_a_warning_and_a_failure(self):
        results = [s["done"][0][0] for s in steps(self.scenes()["short"], "spin")]
        self.assertIn("[ warn ] ", results)
        self.assertIn("[ fail ] ", results)

    def test_the_organisation_is_never_named(self):
        self.assertNotIn("CTRG", spoken(self.scenes()))

    def test_the_old_engines_are_gone(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent / "static/boot"
        self.assertFalse((root / "login.js").exists())
        self.assertNotIn("function stageBios", (root / "boot.js").read_text(encoding="utf-8"))
