"""«Найти по условию»: вещи по тегам и счётчикам, общее условие только дополняет, порядок и предел."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import search, values
from graph import check, runtime
from graph.tests.test_data import f
from graph.tests.test_runtime import make, node, wire
from machines.models import Machine, MachineProfile


class SearchTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        core = Machine.objects.create(name="Core", hostname="core")
        for login in ("guard", "ops", "guest"):
            MachineProfile.objects.create(machine=core, login=login, name=login, freq=1)
        values.set_tag("account", values.owner_id("account", "guard@core"), "compromised", True)
        values.set_tag("account", values.owner_id("account", "ops@core"), "compromised", True)
        values.add("account", values.owner_id("account", "guard@core"), "fails", 5)
        values.add("account", values.owner_id("account", "ops@core"), "fails", 2)

    def test_own_atoms_filter_and_world_only_completes(self):
        self.assertEqual(search.find("tag:account:compromised", "account"), ["guard@core", "ops@core"])
        self.assertEqual(search.find("tag:account:compromised and count:account:fails >= 3", "account"), ["guard@core"])
        self.assertEqual(search.find("not tag:account:compromised", "account"), ["guest@core"])
        self.assertEqual(search.find("tag:account:compromised and tag:world:alarm", "account"), [])
        values.set_tag("world", 0, "alarm", True)
        self.assertEqual(search.find("tag:account:compromised and tag:world:alarm", "account"), ["guard@core", "ops@core"])
        with self.assertRaises(search.SearchError):
            search.find("tag:world:alarm", "account")

    def test_order_limit_and_among(self):
        self.assertEqual(search.find("count:account:fails", "account", sort="fails", limit=1), ["guard@core"])
        self.assertEqual(search.find("count:account:fails", "account", sort="fails", descending=False), ["ops@core", "guard@core"])
        self.assertEqual(search.find("tag:account:compromised", "account", among=["ops@core", "guest@core"]), ["ops@core"])

    def test_the_node_gives_list_first_and_count_and_check_warns(self):
        graph = make([node("m", "manual"), node("s", "thing.find", what="account", expr="tag:account:compromised", sort="fails"),
                      node("t", "act:tag", variant="on", owner="world")],
                     [wire("m", "fire", "t"), f("s", "count", "t", "name")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertTrue(values.on("world", 0, "2"))
        doc = {"nodes": [node("s", "thing.find", what="account", expr="tag:world:alarm")], "wires": []}
        self.assertTrue(any("нет условия на саму вещь" in p["text"] for p in check.problems(doc)))
