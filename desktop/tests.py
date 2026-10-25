"""Рабочий стол: подпись подключения, ключ раскладки, пункты меню панели.

Запуск: python manage.py test desktop
"""
from pathlib import Path

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
        self.assertContains(response, "witness@aether-null")
        self.assertContains(response, 'data-layout-key="guest-m')
        self.assertNotContains(response, 'data-action="sessions"')
        self.assertContains(response, 'data-action="disconnect"')

    def test_the_desktop_page_carries_the_machine_catalog(self):
        session = self.client.session
        session["guest"] = True
        session.save()
        response = self.page()
        self.assertContains(response, 'id="system-messages"')
        self.assertContains(response, "AE-0403")

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


def volume(scene):
    """Сколько символов текста в сцене (по всем шагам, включая вложенные и задачи)."""
    total = 0
    for step in steps(scene, "text") + steps(scene, "type"):
        total += len(step["value"])
    for step in steps(scene, "dots"):
        total += len(step["label"]) + len(step["status"])
    for step in steps(scene, "spin"):
        total += sum(len(part[0]) for part in step["pending"] + step["done"])
    for step in steps(scene, "bar") + steps(scene, "count"):
        total += len(step["label"])
    return total


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

    def test_intro_is_eight_stages_split_by_mode_changes(self):
        intro = self.scenes()["intro"]
        self.assertEqual(sum(1 for s in intro if s["op"] == "cut"), 7)
        titles = [t for t in self.texts(intro) if t.startswith("-- ") and "/9" in t]
        self.assertEqual(
            titles,
            [
                "-- 1/9  bridge --", "-- 2/9  tune --", "-- 3/9  path --", "-- 4/9  sync --",
                "-- 5/9  key exchange --", "-- 6/9  identity --", "-- 7/9  node --", "-- 8/9  access --",
            ],
        )

    def test_the_session_is_the_ninth_stage(self):
        self.assertIn("-- 9/9  session --", self.texts(self.scenes()["bypass"]))

    def test_each_stage_reprints_the_header(self):
        intro = self.scenes()["intro"]
        self.assertEqual(sum(1 for t in self.texts(intro) if t == "AETHER LINK 3.2"), 8)

    def test_the_link_is_radio_after_the_bridge_not_an_ip_network(self):
        import re

        intro = self.scenes()["intro"]
        first_cut = next(i for i, step in enumerate(intro) if step["op"] == "cut")
        bridge, radio = spoken(intro[:first_cut]), spoken(intro[first_cut:])
        for word in ("rf0", "MHz", "carrier", "stations", "dBm", "ofdm", "ldpc", "ground wave", "callsign",
                     "alp/3.2", "certificate chain", "host key", "key id", "[ED25519 256]",
                     "auth      offered by node", "no client key", "38 Mbit/s"):
            self.assertIn(word, radio)
        for word in ("dns", "tcp", "udp", "ethernet", "eth0", "ttl", "ssh", "tls", "mtu"):
            self.assertIsNone(re.search(rf"\b{word}\b", radio, re.IGNORECASE), word)
        # а первый этап честно говорит на языке обычного интернета: ПК игрока живёт в нём
        for word in ("tcp 443", "tls", "x86_64"):
            self.assertIn(word, bridge)

    def test_the_players_pc_has_no_radio_so_a_bridge_comes_first(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("radio: no device found", text)
        self.assertLess(text.index("-- 1/9  bridge --"), text.index("-- 2/9  tune --"))

    def test_the_bridge_directory_lists_near_and_far_working_and_dead(self):
        from users.gateway import BRIDGE, BRIDGES

        distances = [km for _, km, _, _ in BRIDGES]
        self.assertEqual(distances, sorted(distances))                      # ближайшие первыми
        self.assertGreaterEqual(len({status for _, _, status, _ in BRIDGES}), 4)
        nearest_alive = next(name for name, _, status, _ in BRIDGES if status in ("reachable", "degraded"))
        self.assertEqual(nearest_alive, BRIDGE)                             # берётся ближайший рабочий
        dead_before = [name for name, _, status, _ in BRIDGES[:2] if status in ("offline", "no answer")]
        self.assertEqual(len(dead_before), 2)                               # ближе него мертво
        text = spoken(self.scenes()["intro"])
        for name, *_ in BRIDGES:
            self.assertIn(name, text)
        self.assertIn(f"select    {BRIDGE}  (nearest reachable)", text)

    def test_the_bridge_names_are_greek_winds_and_messengers(self):
        from users.gateway import BRIDGES

        self.assertEqual({name for name, *_ in BRIDGES}, {"zephyr", "boreas", "narthex", "notos", "euros", "iris", "hermes"})

    def test_the_bridge_was_opened_for_this_client_by_someone_restricted(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("allowlisted", text)
        self.assertIn("allowlist: 1 entry (this client)", text)
        self.assertIn("added 3 min ago by " + "█" * 10, text)
        self.assertIn("for the one who comes to see", text)

    def test_the_client_key_is_personal(self):
        from django.contrib.auth import get_user_model

        from machines.identity import client_fingerprint

        first = get_user_model().objects.create_user("ivan", password="pw")
        second = get_user_model().objects.create_user("olga", password="pw")
        a, b = self.scenes(user=first), self.scenes(user=second)
        self.assertIn(client_fingerprint(f"user:{first.pk}"), spoken(a["intro"]))
        self.assertIn(client_fingerprint(f"user:{second.pk}"), spoken(b["intro"]))
        self.assertNotEqual(spoken(a["intro"]), spoken(b["intro"]))

    def test_the_known_node_does_not_repeat_the_bridge_noise(self):
        scenes = self.scenes()
        known = spoken(scenes["intro_known"])
        self.assertNotIn("bridges   nearest first", known)
        self.assertNotIn("tls       1.3 handshake", known)
        self.assertIn("select    narthex", known)
        self.assertIn("allowlisted", known)

    def test_the_node_frequency_comes_from_the_machine(self):
        from machines.identity import freq_for

        text = spoken(self.scenes()["intro"])
        self.assertIn(f"{freq_for(self.machine.hid)} MHz", text)

    def test_the_network_is_broken_in_places(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("no answer", text)
        self.assertIn("(retry)", text)
        self.assertIn("(detour)", text)
        self.assertIn("reachable 17", text)      # из 31 станции в каталоге
        self.assertIn("unreachable", text)       # центр не отвечает

    def test_the_world_is_after_the_hunt_dates_come_from_the_world_module(self):
        from machines.world import CORE_LAST_CONTACT, GAME_DATE, days_since

        text = spoken(self.scenes()["intro"])
        self.assertIn(str(GAME_DATE), text)
        self.assertIn(str(CORE_LAST_CONTACT), text)
        self.assertIn(days_since(CORE_LAST_CONTACT) + " d ago", text)
        self.assertIn("expired", text)           # сертификат давно просрочен
        self.assertNotIn("2061", text)

    def test_the_status_of_the_certificate_cannot_be_checked(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("revoked", text)
        self.assertIn("unknown", text)

    def test_someone_reset_the_node_remotely_just_before(self):
        self.assertIn("remote request", spoken(self.scenes()["intro"]))

    def test_key_exchange_has_a_progress_bar_and_a_key_id(self):
        from users.gateway import KEY_ID

        intro = self.scenes()["intro"]
        self.assertEqual(len(steps(intro, "bar")), 1)
        self.assertIn(KEY_ID, spoken(intro))

    def test_a_silent_station_is_called_twice_then_detoured(self):
        text = spoken(self.scenes()["intro"])
        self.assertEqual(text.count("VX-19"), 2)

    def test_there_is_twice_as_much_text_as_before(self):
        self.assertGreaterEqual(volume(self.scenes()["intro"]), 4000)    # было 2010

    def test_noise_is_for_the_first_visit_a_known_node_skips_it(self):
        scenes = self.scenes()
        self.assertLess(volume(scenes["intro_known"]), volume(scenes["intro"]) * 0.8)
        self.assertNotIn("[ED25519 256]", spoken(scenes["intro_known"]))   # картинка отпечатка только на первом заходе
        self.assertIn("[ED25519 256]", spoken(scenes["intro"]))

    def test_every_stage_gives_time_to_read_before_the_screen_changes(self):
        intro = self.scenes()["intro"]
        cuts = [i for i, step in enumerate(intro) if step["op"] == "cut"]
        self.assertEqual(len(cuts), 7)
        for index in cuts:
            self.assertEqual(intro[index - 1]["op"], "read", f"перед cut №{index} нет read")

    def test_the_host_key_picture_belongs_to_the_machine(self):
        from machines.identity import fingerprint_for, randomart_for

        text = spoken(self.scenes()["intro"])
        self.assertIn(fingerprint_for(self.machine.hid), text)
        for line in randomart_for(self.machine.hid):
            self.assertIn(line, text)

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
        self.assertIn("MRT", established)
        self.assertNotIn("L0", established)
        self.assertNotIn("PUBLIC", established)
        self.assertIn("witness", established)
        self.assertIn("not registered", established)

    # ---------- приветствие узла (как на сервере) ----------

    def screen_text(self, scene):
        text = ""
        for step in scene:
            if step["op"] == "text":
                text += step["value"]
            elif step["op"] == "newline":
                text += "\n"
        return text

    def test_the_node_greets_the_player_after_the_session_opens(self):
        from machines.world import GAME_DATE
        from users.gateway import LOGO

        text = self.screen_text(self.scenes()["established"])
        for line in LOGO:
            self.assertIn(line, text)
        for word in ("Welcome to AETHER 9.1 (halcyon)", f"System information as of {GAME_DATE}",
                     "Link load:", "Radio:", "Vault usage:", "Memory:", "Processes:", "Temperature:", "Uptime:"):
            self.assertIn(word, text)
        self.assertLess(text.index("session established."), text.index("Welcome to"))
        self.assertLess(text.index("Welcome to"), text.index("Loading workspace"))

    def test_the_greeting_carries_traces_of_the_world(self):
        from machines.world import BEACON_LAST_SYNC, days_since, CORE_LAST_CONTACT

        text = self.screen_text(self.scenes()["established"])
        self.assertIn(f"the core has not answered for {days_since(CORE_LAST_CONTACT)} days", text)
        self.assertIn("events buffered in the vault, none delivered", text)
        self.assertIn(f"last updated {BEACON_LAST_SYNC}", text)
        self.assertIn("Last login: 2027-10-29 23:41 UTC as " + "█" * 6 + "  through aether-core", text)
        self.assertIn("intercom: no new messages", text)     # почта пуста: приветствие ничего не придумывает
        self.assertNotIn("CTRG", text)

    def test_the_numbers_in_the_greeting_belong_to_the_machine(self):
        first = self.screen_text(self.scenes()["established"])
        second = self.screen_text(self.scenes()["established"])
        self.assertEqual(first, second)
        self.assertIn(f"rf0 {self.machine_freq()} MHz locked", first)

    def machine_freq(self):
        from machines.identity import freq_for

        return freq_for(self.machine.hid)

    def test_the_greeting_is_big_and_gets_time_to_read(self):
        scene = self.scenes()["established"]
        self.assertGreaterEqual(len(self.screen_text(scene).split("Welcome to")[1]), 900)
        reads = [step for step in scene if step["op"] == "read"]
        self.assertEqual(len(reads), 1)
        self.assertGreaterEqual(reads[0]["min_ms"], 1500)
        self.assertLess(scene.index(reads[0]), len(scene) - 1)     # после него ещё «Loading workspace»

    def test_a_returning_session_gets_a_short_greeting_without_the_logo(self):
        from users.gateway import LOGO

        user = get_user_model().objects.create_user("ivan", password="pw")
        text = self.screen_text(self.scenes(user=user)["restored"])
        self.assertIn("System information as of", text)
        self.assertIn("Last login:", text)
        self.assertNotIn(LOGO[2], text)
        self.assertNotIn("Serial:", text)

    def test_the_unregistered_player_is_a_witness_not_a_guest(self):
        for name, scene in self.scenes().items():
            self.assertNotIn("guest", spoken(scene).lower(), name)

    def test_error_scene_has_a_placeholder_for_the_status(self):
        self.assertIn("{code}", spoken(self.scenes()["error"]))

    def test_logged_in_player_gets_a_restored_scene(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        text = spoken(self.scenes(user=user)["restored"])
        self.assertIn("ivan", text)
        self.assertIn("aether-main", text)
        self.assertIn("AKR", text)          # допуск пользователя: ступень первая
        self.assertNotIn("Unregistered", text)

    def test_returning_guest_restores_onto_aether_null(self):
        text = spoken(self.scenes(session={"guest": True})["restored"])
        self.assertIn("aether-null", text)
        self.assertIn("Unregistered session", text)
        self.assertIn("witness", text)


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

    def test_the_hardware_is_radio_not_ethernet(self):
        from machines.identity import freq_for

        full = spoken(self.scenes()["full"])
        for word in ("rf0", "rf1: no carrier", "antenna", "earth", "electrode", "ofdm", "compatd"):
            self.assertIn(word, full)
        self.assertIn(f"{freq_for(self.machine.hid)} MHz", full)
        import re

        for word in ("eth0", "eth1", "ethernet", "dnsd", "tcp", "dhcp"):
            self.assertIsNone(re.search(rf"\b{word}\b", full, re.IGNORECASE), word)

    def test_the_node_is_abandoned_the_core_is_gone_and_the_directory_is_stale(self):
        from machines.world import CORE_LAST_CONTACT, GAME_DATE

        full = spoken(self.scenes()["full"])
        self.assertIn(str(GAME_DATE), full)
        self.assertIn(f"unreachable, last contact {CORE_LAST_CONTACT}", full)
        self.assertIn("beacon directory stale", full)
        self.assertIn("7 of 12 sectors silent", full)
        self.assertIn("buffering to vault", full)

    def test_the_node_was_reset_remotely_by_someone_restricted(self):
        full = spoken(self.scenes()["full"])
        self.assertIn("reset by remote request", full)
        self.assertIn("[restricted]", full)

    def test_the_recovery_entry_wants_the_top_greek_step_not_l5(self):
        full = spoken(self.scenes()["full"])
        self.assertIn("[clearance ARC required]", full)
        self.assertNotIn("L5", full)

    def test_the_machine_belongs_to_the_alternate_2020_not_to_2061(self):
        full = spoken(self.scenes()["full"])
        self.assertIn("2020-09-02", full)      # сборка ядра: версия старая, прошивку не меняют каждый год
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

    def test_there_is_twice_as_much_text_as_before(self):
        scenes = self.scenes()
        self.assertGreaterEqual(volume(scenes["full"]), 5500)      # было 2754
        self.assertGreaterEqual(volume(scenes["short"]), 1500)     # было 764

    def test_every_boot_stage_gives_time_to_read_before_the_screen_changes(self):
        full = self.scenes()["full"]
        for index, step in enumerate(full):
            if step["op"] == "cut" and index:
                self.assertEqual(full[index - 1]["op"], "read", f"перед cut №{index} нет read")

    def test_units_come_in_groups(self):
        text = spoken(self.scenes()["short"])
        for group in ("-- base --", "-- storage --", "-- radio --", "-- services --"):
            self.assertIn(group, text)

    def test_boot_uses_the_toolkit_not_just_text(self):
        full = self.scenes()["full"]
        self.assertEqual(len(steps(full, "count")), 1)         # память
        self.assertEqual(len(steps(full, "bar")), 1)           # загрузка образа
        self.assertGreaterEqual(len(steps(full, "spin")), 20)  # службы и задачи ядра
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



class LoadingIndicatorTests(TestCase):
    """Круглый спиннер: общий стиль, заслон на окнах рабочего стола, загрузка внутри почты."""

    root = Path(__file__).resolve().parent.parent

    def read(self, relative):
        return (self.root / relative).read_text(encoding="utf-8")

    def test_the_spinner_style_exists_and_uses_only_design_tokens(self):
        import re

        css = self.read("static/ui/spinner.css")
        for selector in (".spinner", ".spinner--small", ".loading-veil", "@keyframes spinner-turn"):
            self.assertIn(selector, css)
        self.assertIn("border-radius: 50%", css)                 # круглый
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", css), [])
        self.assertNotIn(":root", css)
        self.assertNotRegex(css, r"rgba?\(")

    def test_the_spinner_respects_reduced_motion(self):
        self.assertIn("prefers-reduced-motion", self.read("static/ui/spinner.css"))

    def test_every_page_gets_the_spinner_style_from_the_base_template(self):
        base = self.read("templates/ui/base.html")
        self.assertIn("ui/spinner.css", base)
        self.assertLess(base.index("ui/tokens.css"), base.index("ui/spinner.css"))   # после токенов

    def test_desktop_windows_show_a_veil_until_the_app_has_loaded(self):
        js = self.read("desktop/static/desktop/desktop.js")
        for part in ("attachLoader", "loading-veil", 'className = "spinner"', '"load"', "beforeunload", "LOAD_TIMEOUT_MS"):
            self.assertIn(part, js)
        self.assertIn("attachLoader(win, label)", js)             # вызывается при открытии окна
        loader = js[js.index("function attachLoader"):js.index("function openApp")]
        self.assertNotIn("innerHTML", loader)

    def test_the_mail_window_shows_a_spinner_while_data_is_coming(self):
        js = self.read("mail/static/mail/mail.js")
        self.assertIn("function loading()", js)
        self.assertGreaterEqual(js.count("loading()"), 3)        # сам помощник, список и письмо


class SystemMessageTests(TestCase):
    """Окна ошибок и уведомления: каталог по системе машины, desktopAPI, вики."""

    root = Path(__file__).resolve().parent.parent

    def read(self, relative):
        return (self.root / relative).read_text(encoding="utf-8")

    def test_every_message_has_a_kind_and_a_title(self):
        from desktop.messages import MESSAGES

        for system, entries in MESSAGES.items():
            for key, entry in entries.items():
                self.assertIn(entry["kind"], ("error", "warning", "info"), f"{system}.{key}")
                self.assertTrue(entry["title"], f"{system}.{key}")

    def test_error_codes_are_unique_within_a_system(self):
        from desktop.messages import MESSAGES

        for system, entries in MESSAGES.items():
            codes = [e["code"] for e in entries.values() if e["code"]]
            self.assertEqual(len(codes), len(set(codes)), system)

    def test_an_unknown_system_falls_back_to_the_default_catalog(self):
        from desktop.messages import DEFAULT_SYSTEM, MESSAGES, catalog

        self.assertIs(catalog("SOMETHING_ELSE"), MESSAGES[DEFAULT_SYSTEM])
        self.assertIn("access_denied", catalog("AETHER"))

    def test_the_organisation_is_never_named_in_messages(self):
        from desktop.messages import MESSAGES

        self.assertNotIn("CTRG", repr(MESSAGES))

    def test_the_desktop_exposes_error_and_notify_without_innerHTML(self):
        js = self.read("desktop/static/desktop/desktop.js")
        block = js[js.index("/* ---------- сообщения системы"):js.index("window.desktopAPI = {")]
        self.assertNotIn("innerHTML", block)        # текст сообщений только как текст
        api = js[js.index("window.desktopAPI = {"):]
        for name in ("openApp", "error: showDialog", "notify: showToast"):
            self.assertIn(name, api[:200])

    def test_dialog_styles_use_only_design_tokens(self):
        import re

        css = self.read("desktop/static/desktop/desktop.css")
        block = css[css.index("окно ошибки и уведомления"):]
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", block), [])
        self.assertNotRegex(block, r"rgba?\(")

    def test_the_wiki_answers_a_locked_record_with_an_error_dialog(self):
        js = self.read("wiki/static/wiki/wiki.js")
        self.assertIn('desktop.error("access_denied"', js)
        self.assertIn('row.dataset.access === "locked"', js)
