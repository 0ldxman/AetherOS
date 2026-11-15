"""«Ответить» вне графа попытки: ответ некому, это видно в журнале мира."""
from django.test import TestCase

from graph import runtime
from graph.tests.test_runtime import make, node, wire


class AnswerOutsideTests(TestCase):
    def test_answer_outside_an_attempt_is_logged(self):
        from world.models import WorldEvent

        graph = make([node("m", "manual"), node("a", "answer", mode="allow")], [wire("m", "fire", "a")])
        runtime.start_manual(graph, "m")
        self.assertTrue(WorldEvent.objects.filter(text__contains="без попытки").exists())
