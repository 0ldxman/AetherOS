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
