"""Число запросов к БД не должно расти вместе с числом файлов (ls -l по папке, список вида машины)."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from filesystem.testing import embed_key, make_file
from machines.models import Machine, MachineProfile, Session
from terminal.engine.executor import TerminalExecutor


class QueryBudgetTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(name="Main", hostname="aether-main")
        self.user = get_user_model().objects.create_user("ivan", password="pw")
        profile = MachineProfile.objects.create(machine=self.machine, user=self.user, name="Ivan", login="ivan", freq=1)
        self.session = Session.objects.create(user=self.user, profile=profile)

    def fill(self, tag, count):
        for index in range(count):
            made = make_file(self.machine, f"/{tag}/f{index}.txt", body="text", size=None, format="")
            embed_key(made.item, "k")

    def run_ls(self, tag):
        with CaptureQueriesContext(connection) as queries:
            result, _ = TerminalExecutor().execute(session=self.session, source=f"ls -l /{tag}")
        return len(queries), result

    def test_ls_l_does_not_cost_more_queries_for_more_files(self):
        self.fill("small", 5)
        self.fill("large", 40)
        small, first = self.run_ls("small")
        large, second = self.run_ls("large")
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(len(second.output.splitlines()), 40)
        print(f"ls -l queries: 5 files {small}, 40 files {large}")
        self.assertLessEqual(large, small + 8)


class RequestBudgetTests(TestCase):
    """Запрос игрока собирает вид машины один раз, даже если на машине есть сетевой диск: число запросов не растёт с числом файлов."""

    def setUp(self):
        import json

        from django.core.cache import cache
        from django.test import override_settings
        from django.urls import get_script_prefix, reverse, set_script_prefix

        from filesystem.testing import make_app
        from machines.models import Export

        cache.clear()
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.machine = Machine.objects.create(name="Main", hostname="aether-main")
        self.host = Machine.objects.create(name="Core", hostname="aether-core")
        make_app(self.machine, label="console", glyph=">_", path="/apps/terminal/")
        self.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=self.machine, user=self.user, name="Ivan", login="ivan", freq=1)
        reader = MachineProfile.objects.create(machine=self.host, login="reader", name="Reader", freq=1)
        make_file(self.host, "/srv/harbor/manifest.txt", body="cargo")
        Export.objects.create(machine=self.host, path="/srv/harbor")
        from machines.models import MachineMount

        MachineMount.objects.create(machine=self.machine, mode="remote", host=self.host, host_path="/srv/harbor", mount_path="/mnt/h", account=reader)
        self.client.force_login(self.user)
        self.url = reverse("terminal:execute")
        self.json = json

    def run_command(self, text):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(self.url, data=self.json.dumps({"command": text}), content_type="application/json")
        return len(queries), self.json.loads(response.content)

    def test_a_simple_command_and_ls_l_stay_cheap_and_do_not_grow_with_the_files(self):
        self.run_command("pwd")
        cheap, data = self.run_command("pwd")
        self.assertEqual(data["exit_code"], 0)
        for index in range(30):
            made = make_file(self.machine, f"/data/f{index}.txt", body="text")
            embed_key(made.item, "k")
        make_file(self.machine, "/few/one.txt", body="x")
        few, _ = self.run_command("ls -l /few")
        many, listing = self.run_command("ls -l /data")
        self.assertEqual(len(listing["output"].splitlines()), 30)
        print(f"queries: pwd {cheap}, ls -l 1 file {few}, ls -l 30 files {many}")
        self.assertLessEqual(cheap, 40)
        self.assertLessEqual(many, few + 10)
