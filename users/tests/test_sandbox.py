"""Песочница автора: один песочный игрок, своя сессия, автор в Студии остаётся собой, следов в Студии и мире нет."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from machines.models import LoginEvent, Machine, MachineProfile, Session
from team.testing import full_role
from users import sandbox

API = "/studio/api"


@override_settings(FORCE_SCRIPT_NAME=None)
class SandboxTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        self.author = get_user_model().objects.create_user("anna", password="pw", is_staff=True, role=full_role())
        self.client.force_login(self.author)

    def open(self):
        response = self.client.post(f"{API}/sandbox/open")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_one_sandbox_player_per_author_reused_everywhere(self):
        first = sandbox.sandbox_of(self.author)
        self.assertEqual(sandbox.sandbox_of(self.author), first)
        self.assertEqual(first.username, "sandbox-anna")
        self.assertFalse(first.is_staff or first.has_usable_password())
        get_user_model().objects.create_user("sandbox-bob")
        bob = get_user_model().objects.create_user("bob", is_staff=True)
        get_user_model().objects.filter(username="sandbox-bob").update(username="sandbox-bob")
        self.assertEqual(sandbox.sandbox_of(bob).username, "sandbox-bob-2")       # имя занято: добавляется номер

    def test_game_pages_go_as_the_sandbox_player_and_studio_stays_with_the_author(self):
        self.assertEqual(self.client.get(f"{API}/sandbox").json(), {"open": False, "player": ""})
        state = self.open()
        self.assertEqual(state, {"open": True, "player": "sandbox-anna"})
        player = get_user_model().objects.get(username="sandbox-anna")
        self.assertEqual(self.client.get(reverse("desktop")).status_code, 200)
        self.assertTrue(Session.objects.filter(user=player).exists())               # игра узнала песочного игрока
        self.assertFalse(Session.objects.filter(user=self.author).exists())
        self.assertIn(sandbox.SESSION_COOKIE, self.client.cookies)                    # у него своя сессия
        self.assertEqual(self.client.get(f"{API}/sandbox").json()["open"], True)     # Студия видит автора
        self.client.post(f"{API}/sandbox/close")
        self.client.get(reverse("desktop"))
        self.assertTrue(Session.objects.filter(user=self.author).exists())          # выключили: снова сам автор

    def test_the_author_session_is_not_touched_by_the_sandbox(self):
        self.client.get(reverse("desktop"))                                          # автор сам на машине
        own = self.client.session.get("machine_session_id")
        self.open()
        self.client.get(reverse("desktop"))
        self.assertEqual(self.client.session.get("machine_session_id"), own)

    def test_a_forged_or_foreign_cookie_does_nothing(self):
        other = get_user_model().objects.create_user("bob", is_staff=True)
        self.client.cookies[sandbox.COOKIE] = sandbox.token(other)                    # чужая кука
        self.client.get(reverse("desktop"))
        self.client.cookies[sandbox.COOKIE] = "forged"
        self.client.get(reverse("desktop"))
        self.assertFalse(get_user_model().objects.filter(sandbox_of__isnull=False).exists())
        player = get_user_model().objects.create_user("ivan")                          # игрок не сотрудник: куки нет силы
        self.client.force_login(player)
        self.client.cookies[sandbox.COOKIE] = sandbox.token(player)
        self.client.get(reverse("desktop"))
        self.assertFalse(get_user_model().objects.filter(sandbox_of__isnull=False).exists())

    def test_reset_leaves_nothing_behind(self):
        self.open()
        self.client.get(reverse("desktop"))
        player = get_user_model().objects.get(username="sandbox-anna")
        profile = MachineProfile.objects.get(user=player)
        LoginEvent.objects.create(profile=profile, user=player, kind=LoginEvent.Kind.BAD_PASSWORD)
        self.client.post(f"{API}/sandbox/reset")
        self.assertFalse(Session.objects.filter(user=player.pk).exists())
        self.assertFalse(MachineProfile.objects.filter(pk=profile.pk).exists())
        self.assertFalse(LoginEvent.objects.filter(profile=profile.pk).exists())
        self.assertFalse(LoginEvent.objects.filter(user__isnull=True).exists())
        fresh = get_user_model().objects.get(sandbox_of=self.author)
        self.assertNotEqual(fresh.pk, player.pk)                                        # новый, пустой

    def test_the_sandbox_player_is_hidden_in_the_studio_and_the_world(self):
        from machines.world.facts import last_login
        from team.players import players

        self.open()
        self.client.get(reverse("desktop"))
        player = get_user_model().objects.get(username="sandbox-anna")
        Session.objects.filter(user=player).update(seen_at=__import__("django.utils.timezone", fromlist=["now"]).now())
        profile = MachineProfile.objects.get(user=player)
        LoginEvent.objects.create(profile=profile, user=player, kind=LoginEvent.Kind.OK)
        self.assertNotIn("sandbox-anna", [u.username for u in players()])
        self.client.post(f"{API}/sandbox/close")
        dash = self.client.get(f"{API}/dashboard").json()
        self.assertNotIn("sandbox-anna", str(dash))
        overview = self.client.get(f"{API}/machines/{self.main.pk}").json()
        self.assertNotIn("sandbox-anna", str(overview))
        self.assertEqual(last_login(profile, None), "never")                             # другим игрокам его вход не виден

    def test_support_is_closed_in_the_sandbox(self):
        import json

        from django.test import RequestFactory

        from support import views

        request = RequestFactory().post("/apps/support/create/", {"subject": "x", "category": "other", "text": "help"})
        request.user = sandbox.sandbox_of(self.author)
        response = views.create.__wrapped__(request) if hasattr(views.create, "__wrapped__") else views.create(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("sandbox", json.loads(response.content)["error"])
