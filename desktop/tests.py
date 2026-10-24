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
    """Все шаги с этим op, включая вложенные (one_of, события выбора)."""
    found = []
    for step in scene:
        if step["op"] == op:
            found.append(step)
        for nested in step.get("scenes", []):
            found += steps(nested, op)
        for event in step.get("events", []):
            found += steps(event["steps"], op)
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
        self.assertEqual(set(scenes), {"intro", "menu", "discord", "bypass", "established", "error"})

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
    """Содержание сцен входа: сюжет, замазанный владелец, общий hid."""

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

    def test_the_owner_organisation_is_never_named(self):
        for name, scene in self.scenes().items():
            self.assertNotIn("CTRG", spoken(scene), name)

    def test_owner_field_is_masked_and_marked_restricted(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("█" * 14, text)
        self.assertIn("[restricted]", text)

    def test_hid_is_read_from_the_machine_and_shown_before_and_after(self):
        scenes = self.scenes()
        self.assertIn(self.machine.hid, spoken(scenes["intro"]))
        self.assertIn(self.machine.hid, spoken(scenes["bypass"]))
        self.assertIn("(unchanged)", spoken(scenes["bypass"]))

    def test_hid_has_a_placeholder_when_the_machine_is_missing(self):
        from users.aether_auth import UNKNOWN_HID

        Machine.objects.all().delete()
        self.assertIn(UNKNOWN_HID, spoken(self.scenes()["intro"]))

    def test_intro_goes_through_the_stages_in_order(self):
        text = [s.get("value", "") for s in self.scenes()["intro"] if s["op"] == "text"]
        joined = "|".join(text)
        order = ["AETHER LINK", "target", "node", "chassis", "owner", "Trust node", "node notice", "access"]
        positions = [joined.index(word) for word in order]
        self.assertEqual(positions, sorted(positions))

    def test_route_includes_a_timeout_and_a_retry(self):
        text = spoken(self.scenes()["intro"])
        self.assertIn("no answer", text)
        self.assertEqual(text.count("relay 03"), 2)

    def test_trust_prompt_is_typed_by_the_player_like_a_human(self):
        typed = [s for s in self.scenes()["intro"] if s["op"] == "type"]
        self.assertEqual([(s["value"], s["human"]) for s in typed], [("y", True)])

    def test_entry_choice_starts_with_discord_only(self):
        (choice,) = [s for s in self.scenes()["intro"] if s["op"] == "choice"]
        self.assertEqual([o["id"] for o in choice["options"]], ["discord"])

    def test_stranger_appears_later_with_the_bypass_option(self):
        from users.gateway import GATEWAY

        (choice,) = [s for s in self.scenes()["intro"] if s["op"] == "choice"]
        first, second = choice["events"]
        self.assertEqual(first["after_ms"], GATEWAY["event_after_ms"])
        self.assertEqual([o["id"] for o in first["options"]], ["bypass"])
        self.assertEqual(first["options"][0]["keys"], ["?", "/"])
        self.assertEqual(second["after_ms"], GATEWAY["nudge_after_ms"])

    def test_the_stranger_speaks_in_the_first_person_from_a_random_pool(self):
        from users.gateway import GATEWAY

        (one_of,) = steps(self.scenes()["intro"], "one_of")[:1]
        said = {nested[0]["value"] for nested in one_of["scenes"]}
        self.assertEqual(said, set(GATEWAY["messages"]))

    def test_bypass_turns_the_host_into_null_in_place(self):
        scenes = self.scenes()
        ids = {s["id"] for s in steps(scenes["intro"], "text") if "id" in s}
        glitches = steps(scenes["bypass"], "glitch") + steps(scenes["error"], "glitch")
        self.assertTrue(glitches)
        for glitch in glitches:
            self.assertIn(glitch["id"], ids)  # иначе браузеру нечего портить
        self.assertEqual(steps(scenes["bypass"], "glitch")[0]["to"], "aether-null")
        self.assertEqual(steps(scenes["error"], "glitch")[0]["to"], "aether-main")

    def test_the_session_is_only_announced_after_the_server_confirms(self):
        # bypass играется, пока идёт запрос; established только после успешного ответа
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
        restored = self.scenes(user=user)["restored"]
        text = spoken(restored)
        self.assertIn("ivan", text)
        self.assertIn("aether-main", text)
        self.assertNotIn("Unregistered", text)

    def test_returning_guest_restores_onto_aether_null(self):
        restored = self.scenes(session={"guest": True})["restored"]
        text = spoken(restored)
        self.assertIn("aether-null", text)
        self.assertIn("Unregistered session", text)
