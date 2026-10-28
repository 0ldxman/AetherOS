"""Админки машин, файлов, карты, ассетов и пользователей: названия и списки.

Запуск: python manage.py test config.test_admin_lists
"""
from datetime import date

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import get_script_prefix, reverse, set_script_prefix

from assets.models import Asset
from filesystem.models import FileKey, MachineFile, SessionFile
from machines.models import Machine, MachineApp, MachineProfile, Session
from map.models import Country, CountryLabel, Ownership, Province
from secure.models import Key


def build(i, user, key):
    """Один «набор» связанных объектов; i делает ключи уникальными."""
    machine = Machine.objects.create(name=f"Машина {i}", hostname=f"host-{i}")
    profile = MachineProfile.objects.create(
        machine=machine, user=user, name=f"P{i}", login=f"login{i}", freq=i
    )
    session = Session.objects.create(user=user, profile=profile)
    file = MachineFile.objects.create(machine=machine, path=f"/docs/{i}.txt")
    FileKey.objects.create(file=file, key=key)
    SessionFile.objects.create(session=session, file=file)
    MachineApp.objects.create(machine=machine, label="wiki", glyph="W", path="/apps/wiki/")
    country = Country.objects.create(code=f"C{i}", name=f"Страна {i}", valid_from=date(2000, 1, 1))
    province = Province.objects.create(code=f"P{i}", source_code=f"S{i}", name=f"Пров {i}")
    Ownership.objects.create(province=province, country=country, date_from=date(2000, 1, 1), de_jure=True)
    CountryLabel.objects.create(country=country, lng=1, lat=1)
    Asset.objects.create(name=f"Ассет {i}", slug=f"asset-{i}", file_id=f"f{i}", viewer_type=Asset.ViewerType.AUDIO)


class NamesTests(TestCase):
    def test_machine_shows_name_and_hostname(self):
        self.assertEqual(str(Machine(name="Main", hostname="aether-main")), "Main (aether-main)")
        self.assertEqual(str(Machine(name="aether-null", hostname="aether-null")), "aether-null")
        self.assertEqual(str(Machine(name="Без хоста")), "Без хоста")

    def test_machine_without_hostname_does_not_print_none(self):
        machine = Machine.objects.create(name="Безымянный")
        profile = MachineProfile.objects.create(machine=machine, name="p", login="l", freq=1)
        app = MachineApp.objects.create(machine=machine, label="wiki", glyph="W", path="/apps/wiki/")
        file = MachineFile.objects.create(machine=machine, path="/a")
        for obj in (profile, app, file):
            self.assertNotIn("None", str(obj))

    def test_file_key_is_readable(self):
        machine = Machine.objects.create(name="M", hostname="m")
        file = MachineFile.objects.create(machine=machine, path="/a.txt")
        link = FileKey.objects.create(file=file, key=Key.objects.create(slug="key_a"))
        self.assertEqual(str(link), "m:/a.txt — key_a")
        self.assertNotIn("object", str(link))


@override_settings(FORCE_SCRIPT_NAME=None)
class ListsTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.user = get_user_model().objects.create_superuser("root", password="pw")
        self.key = Key.objects.create(slug="key_a")
        self.client.force_login(self.user)

    def urls(self):
        for model, model_admin in admin.site._registry.items():
            opts = model._meta
            if opts.app_label in ("machines", "filesystem", "map", "assets", "users", "secure"):
                yield f"admin:{opts.app_label}_{opts.model_name}_changelist"

    def test_every_changelist_renders_with_data(self):
        for i in range(1, 3):
            build(i, self.user, self.key)
        for name in self.urls():
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            self.assertNotContains(response, "object (", msg_prefix=name)

    def test_changelists_do_not_query_per_row(self):
        build(1, self.user, self.key)
        before = {}
        for name in self.urls():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse(name))
            before[name] = len(ctx)
        for i in range(2, 8):
            build(i, self.user, self.key)
        for name in self.urls():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse(name))
            self.assertEqual(len(ctx), before[name], f"{name}: число запросов растёт с числом строк")

    def test_machine_list_has_counts_and_link_to_its_files(self):
        build(1, self.user, self.key)
        response = self.client.get(reverse("admin:machines_machine_changelist"))
        machine = response.context["cl"].result_list[0]
        self.assertEqual((machine._profiles, machine._apps, machine._files), (1, 1, 1))
        self.assertContains(response, reverse("admin:machines_machine_files", args=[machine.pk]))         # колонка ведёт в файловый менеджер

    def test_file_page_has_keys_inline(self):
        build(1, self.user, self.key)
        file = MachineFile.objects.get()
        response = self.client.get(reverse("admin:filesystem_machinefile_change", args=[file.pk]))
        self.assertContains(response, "key_a")
        self.assertContains(response, "keys-TOTAL_FORMS")

    def test_user_list_shows_profile_count(self):
        build(1, self.user, self.key)
        response = self.client.get(reverse("admin:users_user_changelist"))
        row = next(u for u in response.context["cl"].result_list if u.pk == self.user.pk)
        self.assertEqual(row._profiles, 1)

    def test_asset_list_shows_snippet_and_size(self):
        build(1, self.user, self.key)
        response = self.client.get(reverse("admin:assets_asset_changelist"))
        self.assertContains(response, "::audio asset-1")
