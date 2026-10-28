"""Админка профилей машин: пароль только хэшем, токены с автогенерацией.

Запуск: python manage.py test machines.test_admin
"""
from datetime import timedelta

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix
from django.utils import timezone

from machines.forms import has_real_hash
from machines.models import Machine, MachineProfile, MachineProfileToken


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminTestCase(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.admin = get_user_model().objects.create_superuser("root", password="pw")
        self.client.force_login(self.admin)
        self.machine = Machine.objects.create(name="M", hostname="m")


class ProfilePasswordTests(AdminTestCase):
    def form_data(self, **extra):
        data = {
            "machine": self.machine.pk, "user": "", "name": "Профиль", "login": "ivan", "mail": "ivan@m", "freq": "1.000",
            "key_condition": "",
            "tokens-TOTAL_FORMS": 0, "tokens-INITIAL_FORMS": 0, "tokens-MIN_NUM_FORMS": 0, "tokens-MAX_NUM_FORMS": 1000,
        }
        data.update(extra)
        return data

    def create(self, **extra):
        response = self.client.post(reverse("admin:machines_machineprofile_add"), self.form_data(**extra))
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["errors"])
        return MachineProfile.objects.get(login="ivan")

    def edit(self, profile, **extra):
        url = reverse("admin:machines_machineprofile_change", args=[profile.pk])
        return self.client.post(url, self.form_data(**extra))

    def test_new_password_is_stored_only_as_a_hash(self):
        profile = self.create(new_password="секрет123")
        self.assertNotIn("секрет123", profile.password_hash)
        self.assertTrue(has_real_hash(profile.password_hash))
        self.assertTrue(check_password("секрет123", profile.password_hash))

    def test_empty_field_keeps_the_current_password(self):
        profile = self.create(new_password="один")
        before = profile.password_hash
        self.edit(profile, name="Переименован")
        profile.refresh_from_db()
        self.assertEqual((profile.name, profile.password_hash), ("Переименован", before))

    def test_new_password_replaces_the_old_one(self):
        profile = self.create(new_password="один")
        self.edit(profile, new_password="два")
        profile.refresh_from_db()
        self.assertTrue(check_password("два", profile.password_hash))

    def test_clear_password(self):
        profile = self.create(new_password="один")
        self.edit(profile, clear_password="on")
        profile.refresh_from_db()
        self.assertEqual(profile.password_hash, "")

    def test_both_at_once_is_an_error(self):
        profile = self.create()
        response = self.edit(profile, new_password="x", clear_password="on")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нельзя одновременно")

    def test_the_mail_address_is_required_in_the_form(self):
        response = self.client.post(reverse("admin:machines_machineprofile_add"), self.form_data(mail="", new_password="x"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertFalse(MachineProfile.objects.filter(login="ivan").exists())

    def test_hash_is_never_rendered_back(self):
        profile = self.create(new_password="один")
        response = self.client.get(reverse("admin:machines_machineprofile_change", args=[profile.pk]))
        self.assertNotContains(response, profile.password_hash)
        self.assertContains(response, "задан (хэш)")

    def test_plain_text_in_the_old_field_is_flagged_and_can_be_fixed(self):
        profile = MachineProfile.objects.create(
            machine=self.machine, name="Старый", login="old", freq=2, password_hash="открытый"
        )
        page = self.client.get(reverse("admin:machines_machineprofile_change", args=[profile.pk]))
        self.assertContains(page, "открытый текст")

        self.client.post(
            reverse("admin:machines_machineprofile_changelist"),
            {"action": "hash_plain_passwords", ACTION_CHECKBOX_NAME: [profile.pk]},
        )
        profile.refresh_from_db()
        self.assertTrue(check_password("открытый", profile.password_hash))

    def test_action_does_not_touch_real_hashes(self):
        real = make_password("пароль")
        profile = MachineProfile.objects.create(
            machine=self.machine, name="Ок", login="ok", freq=3, password_hash=real
        )
        self.client.post(
            reverse("admin:machines_machineprofile_changelist"),
            {"action": "hash_plain_passwords", ACTION_CHECKBOX_NAME: [profile.pk]},
        )
        profile.refresh_from_db()
        self.assertEqual(profile.password_hash, real)


class TokenTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.profile = MachineProfile.objects.create(machine=self.machine, name="P", login="l", freq=1)

    def add(self, **extra):
        data = {"profile": self.profile.pk, "token": "", "max_usage": "", "usage": 0, "expires_at_0": "", "expires_at_1": ""}
        data.update(extra)
        return self.client.post(reverse("admin:machines_machineprofiletoken_add"), data)

    def test_blank_token_is_generated(self):
        self.assertEqual(self.add().status_code, 302)
        token = MachineProfileToken.objects.get().token
        self.assertGreaterEqual(len(token), 10)

    def test_generated_tokens_differ(self):
        self.add()
        self.add()
        self.assertEqual(MachineProfileToken.objects.values("token").distinct().count(), 2)

    def test_given_token_is_kept(self):
        self.add(token="  мой-токен ")
        self.assertEqual(MachineProfileToken.objects.get().token, "мой-токен")

    def test_duplicate_token_is_rejected(self):
        self.add(token="same")
        response = self.add(token="same")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MachineProfileToken.objects.count(), 1)

    def test_validity_and_usage_columns(self):
        now = timezone.now()
        make = lambda **kw: MachineProfileToken.objects.create(profile=self.profile, **kw)  # noqa: E731
        make(token="alive")
        make(token="expired", expires_at=now - timedelta(hours=1))
        make(token="used-up", max_usage=2, usage=2)
        make(token="partly", max_usage=5, usage=1)
        response = self.client.get(reverse("admin:machines_machineprofiletoken_changelist"))
        admin_obj = response.context["cl"].model_admin
        rows = {t.token: t for t in response.context["cl"].result_list}
        self.assertTrue(admin_obj.is_valid(rows["alive"]))
        self.assertFalse(admin_obj.is_valid(rows["expired"]))
        self.assertFalse(admin_obj.is_valid(rows["used-up"]))
        self.assertTrue(admin_obj.is_valid(rows["partly"]))
        self.assertEqual(admin_obj.uses(rows["partly"]), "1 / 5")
        self.assertEqual(admin_obj.uses(rows["alive"]), "0 / ∞")

    def test_reset_usage_action(self):
        token = MachineProfileToken.objects.create(profile=self.profile, token="t", max_usage=3, usage=3)
        self.client.post(
            reverse("admin:machines_machineprofiletoken_changelist"),
            {"action": "reset_usage", ACTION_CHECKBOX_NAME: [token.pk]},
        )
        token.refresh_from_db()
        self.assertEqual(token.usage, 0)

    def test_inline_on_the_profile_page_generates_too(self):
        url = reverse("admin:machines_machineprofile_change", args=[self.profile.pk])
        data = {
            "machine": self.machine.pk, "user": "", "name": "P", "login": "l", "mail": "l@m", "freq": "1.000", "key_condition": "",
            "tokens-TOTAL_FORMS": 1, "tokens-INITIAL_FORMS": 0, "tokens-MIN_NUM_FORMS": 0, "tokens-MAX_NUM_FORMS": 1000,
            "tokens-0-token": "", "tokens-0-max_usage": "5", "tokens-0-usage": "0",
            "tokens-0-expires_at_0": "", "tokens-0-expires_at_1": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        token = MachineProfileToken.objects.get(profile=self.profile)
        self.assertEqual(token.max_usage, 5)
        self.assertTrue(token.token)


class ConditionFieldTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        from filesystem.testing import key_item
        key_item("key_a")

    def test_profile_condition_is_validated_too(self):
        response = self.client.post(
            reverse("admin:machines_machineprofile_add"),
            {"machine": self.machine.pk, "user": "", "name": "P", "login": "l", "freq": "1.000",
             "key_condition": '{"not": []}',
             "tokens-TOTAL_FORMS": 0, "tokens-INITIAL_FORMS": 0, "tokens-MIN_NUM_FORMS": 0, "tokens-MAX_NUM_FORMS": 1000,},
        )
        self.assertEqual(response.status_code, 200)


class GroupAdminTests(AdminTestCase):
    def test_the_groups_of_a_system_type_are_edited_on_its_page_and_a_profile_names_its_groups(self):
        from machines.models import Group, SystemType

        system = SystemType.objects.get(code="AETHER")
        page = self.client.get(reverse("admin:machines_systemtype_change", args=[system.pk]))
        self.assertContains(page, "groups-0-privileges")
        from machines.models import MachineProfile

        profile = MachineProfile.objects.create(machine=self.machine, login="ivan", name="Ivan", freq=1)
        response = self.client.get(reverse("admin:machines_machineprofile_change", args=[profile.pk]))
        self.assertContains(response, 'name="groups"')
        self.assertContains(response, 'name="root"')
        self.assertTrue(Group.objects.filter(system_type=system, name="users").exists())
