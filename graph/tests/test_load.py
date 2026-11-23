"""Нагрузка рантайма: ошибки сценария для карточки кэшируются по версии графа, факты игрока строятся раз на проход проверок."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from graph import check, runtime
from graph.models import Graph, Run


class ErrorCountTests(TestCase):
    def test_cached_until_the_graph_changes(self):
        graph = Graph.objects.create(slug="g", title="G", doc={"nodes": [], "wires": []})
        with mock.patch.object(check, "problems", return_value=[{"level": "error"}]) as problems:
            self.assertEqual(check.error_count(graph), 1)
            self.assertEqual(check.error_count(graph), 1)
            self.assertEqual(problems.call_count, 1)
            graph.title = "G2"
            graph.save()
            check.error_count(graph)
            self.assertEqual(problems.call_count, 2)


class FactsMemoTests(TestCase):
    def test_one_build_per_player_per_pass(self):
        user = get_user_model().objects.create_user("p")
        run = Run(graph=Graph(slug="g"), user=user)
        memo = {}
        with mock.patch("engine.facts.player_facts", return_value=frozenset({"k"})) as facts:
            runtime._facts(run, memo)
            runtime._facts(run, memo)
            self.assertEqual(facts.call_count, 1)
            runtime._facts(run)                              # без memo — каждый раз заново
            self.assertEqual(facts.call_count, 2)
