"""Список игроков в действиях: «Размещение: Создать» и «Учётка: Блокировка» делают своё для каждого."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem.machine_view import view_for
from graph import check, runtime
from graph.models import Graph
from graph.tests.test_runtime import make, node, wire
from machines.models import AccountBlock, Machine, MachineProfile


class ManyPlayersTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ivan, self.anna = users.create_user("ivan"), users.create_user("anna")
        self.main = Machine.objects.create(name="Main", hostname="main")
        for user in (self.ivan, self.anna):
            MachineProfile.objects.create(machine=self.main, user=user, name=user.username, login=user.username, freq=1)
        self.ops = MachineProfile.objects.create(machine=self.main, login="ops", name="Ops")

    def run_graph(self, kind, **data):
        graph = make([node("m", "manual"), node("a", kind, **data)], [wire("m", "fire", "a")], slug=f"g{Graph.objects.count()}")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)

    def test_a_file_is_created_for_each_listed_player(self):
        self.run_graph("act:placement.create", machine="main", path="/home/{login}/hint.txt", text="ping", player=["ivan", "anna"])
        for user in (self.ivan, self.anna):
            self.assertIn("ping", view_for(self.main, user, login=user.username).get(f"/home/{user.username}/hint.txt").own_text or "")

    def test_block_for_a_list_of_players_and_for_one_named_player(self):
        self.run_graph("act:account.access", variant="block", account="ops@main", scope="player", player=["ivan", "anna"], minutes=5, text="locked")
        self.assertEqual(sorted(AccountBlock.objects.values_list("user__username", flat=True)), ["anna", "ivan"])
        AccountBlock.objects.all().delete()
        self.run_graph("act:account.access", variant="block", account="ops@main", scope="player", player="anna", minutes=5, text="locked")
        self.assertEqual(list(AccountBlock.objects.values_list("user__username", flat=True)), ["anna"])
