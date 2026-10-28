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
