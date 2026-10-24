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


@override_settings(FORCE_SCRIPT_NAME=None)
class LockScreenTests(TestCase):
    """Экран входа после загрузки: терминал на деталях загрузки, данные про дыру для гостя."""

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def test_page_is_built_from_the_boot_screen_parts(self):
        response = self.client.get(reverse("lock"))
        self.assertContains(response, 'id="boot-screen"')
        self.assertContains(response, 'id="boot-output"')
        self.assertContains(response, "boot/boot.css")
        self.assertContains(response, "boot/login.css")
        self.assertContains(response, "boot/lock.js")

    def test_gateway_data_reaches_the_page(self):
        from machines.models import Machine

        machine = Machine.objects.create(name="Main", hostname="aether-main")
        body = self.client.get(reverse("lock")).content.decode()
        self.assertNotIn("CTRG", body)  # чья это машина, игрок должен догадаться сам
        self.assertIn("aether-null", body)
        self.assertIn(machine.hid, body)
        self.assertIn("i left it open for you", body)

    def test_node_name_is_in_the_config(self):
        from users.aether_auth import NODE_NAME

        self.assertContains(self.client.get(reverse("lock")), NODE_NAME)

    def test_stylesheet_uses_only_design_tokens(self):
        # tokens.css: хардкод цвета вне него считается багом (другая машина останется «от старой»)
        import re
        from pathlib import Path

        css = (Path(__file__).parent / "static" / "boot" / "lock.css").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", css), [])
        self.assertNotIn(":root", css)
        self.assertNotRegex(css, r"rgba?\(")


class GatewayConfigTests(TestCase):
    def test_the_screen_is_aether_on_aether_main(self):
        from users.aether_auth import gateway_config

        config = gateway_config()
        self.assertEqual((config["system"], config["host"]), ("AETHER", "aether-main"))

    def test_the_owner_organisation_is_never_sent_to_the_browser(self):
        import json

        from users.aether_auth import gateway_config

        config = gateway_config()
        self.assertNotIn("org", config)
        self.assertNotIn("CTRG", json.dumps(config))

    def test_bypass_turns_main_into_null(self):
        from users.aether_auth import gateway_config

        bypass = gateway_config()["bypass"]
        self.assertEqual(bypass["host"], "aether-null")
        self.assertEqual(bypass["clearance"], {"level": "L0", "label": "PUBLIC"})

    def test_bypass_voice_is_a_pool_to_pick_from(self):
        from users.aether_auth import GATEWAY

        self.assertGreaterEqual(len(GATEWAY["bypass"]["lines"]), 3)
        self.assertGreaterEqual(len(GATEWAY["bypass"]["again_lines"]), 2)
        low, high = GATEWAY["bypass"]["again_after_ms"]
        self.assertLess(low, high)

    def test_hid_is_taken_from_the_machine(self):
        from machines.models import Machine
        from users.aether_auth import gateway_config

        machine = Machine.objects.create(name="Main", hostname="aether-main")
        self.assertEqual(gateway_config()["hid"], machine.hid)

    def test_hid_has_a_placeholder_when_the_machine_is_missing(self):
        from users.aether_auth import UNKNOWN_HID, gateway_config

        self.assertEqual(gateway_config()["hid"], UNKNOWN_HID)

    def test_config_helper_does_not_mutate_the_template_data(self):
        from users.aether_auth import GATEWAY, gateway_config

        gateway_config()["bypass"]["host"] = "changed"
        self.assertEqual(GATEWAY["bypass"]["host"], "aether-null")
        self.assertNotIn("clearance", GATEWAY["bypass"])
