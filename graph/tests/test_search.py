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

    def test_accounts_by_rights_group(self):
        MachineProfile.objects.filter(login="ops").update(groups=["Ops", "wheel"])
        self.assertEqual(search.find("group:account:ops", "account"), ["ops@core"])
        self.assertEqual(search.find("group:account:wheel and not tag:account:compromised", "account"), [])
        with self.assertRaises(search.SearchError):
            search.find("group:account:ops", "machine")

    def test_order_limit_and_among(self):
        from datetime import timedelta

        from django.utils import timezone

        from engine.models import Value

        self.assertEqual(search.find("count:account:fails", "account", order="count", by="fails", descending=True, limit=1), ["guard@core"])
        self.assertEqual(search.find("count:account:fails", "account", order="count", by="fails"), ["ops@core", "guard@core"])
        self.assertEqual(search.find("tag:account:compromised or not tag:account:compromised", "account", order="name", descending=True),
                         ["ops@core", "guest@core", "guard@core"])
        Value.objects.filter(name="compromised", owner_id=values.owner_id("account", "ops@core")).update(changed_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(search.find("tag:account:compromised", "account", order="tag_time", by="compromised"), ["ops@core", "guard@core"])
        everyone = search.find("tag:account:compromised or not tag:account:compromised", "account", order="changed", by="compromised", descending=True)
        self.assertEqual(everyone, ["guard@core", "ops@core", "guest@core"])                   # без отметки — в конце
        self.assertEqual(sorted(search.find("tag:account:compromised", "account", order="random")), ["guard@core", "ops@core"])
        self.assertEqual(search.find("tag:account:compromised", "account", among=["ops@core", "guest@core"]), ["ops@core"])

    def test_the_node_gives_list_first_and_count_and_check_warns(self):
        graph = make([node("m", "manual"), node("s", "thing.find", what="account", expr="tag:account:compromised", order="count", by="fails"),
                      node("t", "act:tag", variant="on", owner="world")],
                     [wire("m", "fire", "t"), f("s", "count", "t", "name")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertTrue(values.on("world", 0, "2"))
        doc = {"nodes": [node("s", "thing.find", what="account", expr="tag:world:alarm")], "wires": []}
        self.assertTrue(any("нет условия на саму вещь" in p["text"] for p in check.problems(doc)))
