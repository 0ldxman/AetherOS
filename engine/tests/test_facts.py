"""Факты игрока: личные метки flag:<имя> работают в любом условии рядом с ключами и world:."""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from documents.markup.expr import parse_expr
from engine import facts
from forum import logic
from forum.models import Section, Space
from mail.models import Flag
from secure.access import condition_slugs, satisfied
from secure.requestkeys import held_keys


class FactsTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_flags_join_keys(self):
        Flag.objects.create(user=self.ivan, name="dock-open")
        self.assertEqual(facts.of(self.ivan, {"mask"}), frozenset({"mask", "flag:dock-open"}))
        self.assertEqual(facts.of(None, {"mask"}), frozenset({"mask"}))

    def test_conditions_parse_and_check_flags(self):
        condition = parse_expr("flag:dock-open and not mask")
        self.assertEqual(condition, {"all": ["flag:dock-open", {"not": "mask"}]})
        self.assertTrue(satisfied(condition, facts.of(self.ivan) | {"flag:dock-open"}))
        self.assertFalse(satisfied(condition, frozenset()))

    def test_flags_and_world_atoms_are_not_keys(self):
        self.assertEqual(condition_slugs({"all": ["flag:x", "world:y", "mask"]}), ["mask"])

    def test_request_facts_carry_flags_without_a_machine_session(self):
        Flag.objects.create(user=self.ivan, name="met")
        request = RequestFactory().get("/")
        request.user, request.session = self.ivan, {}
        self.assertEqual(held_keys(request), frozenset({"flag:met"}))

    def test_a_forum_board_can_open_by_a_player_flag(self):
        space = Space.objects.create(slug="net", title="Net")
        board = Section.objects.create(space=space, title="Inner", read_if="flag:met")
        self.assertFalse(logic.can_read(board, facts.of(self.ivan)))
        Flag.objects.create(user=self.ivan, name="met")
        self.assertTrue(logic.can_read(board, facts.of(self.ivan)))
