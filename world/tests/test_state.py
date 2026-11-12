"""Общий мир: метки и счётчики в условиях, вклады, триггеры и их цепочки, действия, подстановки, исходы писем."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from secure.access import satisfied
from world import state
from world.models import WorldContribution, WorldCounter, WorldEvent, WorldTrigger


class WorldStateTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")

    def test_flags_and_counters_work_in_any_condition(self):
        self.assertFalse(satisfied("world:core-online", set()))
        state.set_flag("core-online", source="автор")
        self.assertTrue(satisfied({"all": ["world:core-online", {"not": "world:act-2"}]}, set()))
        state.count("fragments", 3, "автор")
        self.assertTrue(satisfied("world:fragments>=3", set()))
        self.assertFalse(satisfied("world:fragments>3", set()))
        self.assertTrue(satisfied("world:silence<1", set()))                 # нет счётчика: ноль
        self.assertFalse(satisfied("world:bad name", set()))
        with self.assertRaises(state.WorldError):
            state.parse_atom("world:fragments=>3")

    def test_a_players_counter_takes_each_player_once(self):
        WorldCounter.objects.create(name="signals", mode=WorldCounter.Mode.PLAYERS)
        state.count("signals", user=self.ivan, source="ответчик")
        state.count("signals", user=self.ivan, source="ответчик")
        state.count("signals", user=self.olga, source="письмо")
        state.count("signals", source="автор")                               # без игрока не считается
        self.assertEqual(WorldCounter.objects.get(name="signals").value, 2)
        self.assertEqual(WorldContribution.objects.filter(counter__name="signals").count(), 2)
        self.assertEqual(state.set_counter("signals", 5, "автор"), 5)

    def test_triggers_fire_on_the_edge_and_chain(self):
        WorldTrigger.objects.create(name="act-2", condition="world:fragments>=3", actions=[{"do": "flag", "name": "act-2"}])
        WorldTrigger.objects.create(name="dawn", condition="world:act-2", actions=[{"do": "count", "name": "acts", "delta": 1}])
        WorldTrigger.objects.create(name="beacon", condition="world:fragments>=2", repeat=True, actions=[{"do": "count", "name": "beacons"}])
        state.count("fragments", 2)
        self.assertEqual(WorldTrigger.objects.get(name="act-2").fired_count, 0)
        state.count("fragments", 1)
        self.assertTrue(satisfied("world:act-2", set()))
        self.assertTrue(satisfied("world:acts=1", set()))                      # цепочка: act-2 поставил метку, dawn сработал на ней
        state.count("fragments", 5)
        self.assertEqual(WorldTrigger.objects.get(name="act-2").fired_count, 1)  # условие уже было верным: не повторяется
        self.assertEqual(state.snapshot()["counters"]["beacons"], 1)
        state.set_counter("fragments", 0)
        state.count("fragments", 2)
        self.assertEqual(state.snapshot()["counters"]["beacons"], 2)           # повторный: снова стало верно — снова сработал
        self.assertTrue(WorldEvent.objects.filter(kind="trigger", subject="dawn").exists())

    def test_a_loop_of_triggers_stops(self):
        WorldTrigger.objects.create(name="ping", condition="world:a", repeat=True, actions=[{"do": "unflag", "name": "a"}, {"do": "flag", "name": "b"}])
        WorldTrigger.objects.create(name="pong", condition="world:b", repeat=True, actions=[{"do": "unflag", "name": "b"}, {"do": "flag", "name": "a"}])
        state.set_flag("a")
        self.assertTrue(WorldEvent.objects.filter(text__contains="слишком длинная").exists())

    def test_actions_post_news_and_go_on_air(self):
        from air.models import Station, Transmission
        from news.models import Post

        Station.objects.create(name="BOREAS")
        trigger = WorldTrigger.objects.create(name="open", condition="world:open", actions=[
            {"do": "news", "title": "Core is back", "text": "All stations report."},
            {"do": "air", "station": "boreas", "freq": "7.205", "text": "CORE ONLINE", "key": "orpheus"},
            {"do": "news"},
        ])
        state.fire(trigger, by="автор")
        self.assertEqual(Post.objects.get().title, "Core is back")
        self.assertEqual((Transmission.objects.get().text, Transmission.objects.get().key), ("CORE ONLINE", "orpheus"))
        self.assertTrue(WorldEvent.objects.filter(text__contains="не выполнено").exists())
        self.assertEqual(state.check_actions([{"do": "news"}, {"do": "fly"}]), ["действие 1: у новости нет заголовка", "действие 2: неизвестно «fly»"])
        self.assertEqual(state.check_condition("world:x>=2 "), [])
        self.assertTrue(state.check_condition("secret-key"))

    def test_counters_fill_texts_and_mail_outcomes_change_the_world(self):
        from mail import letters, talk

        state.count("fragments", 4)
        self.assertEqual(letters.fill("собрано {world_fragments} из 7, {world_none}", {}), "собрано 4 из 7, {world_none}")
        box = type("Box", (), {"user": self.ivan, "machine": None, "login": "ivan", "profile": None})()
        talk.run_actions([{"do": "world_count", "name": "fragments", "delta": 2}, {"do": "world_flag", "name": "met-boreas"}], box)
        self.assertTrue(satisfied({"all": ["world:fragments=6", "world:met-boreas"]}, set()))
        self.assertEqual(WorldContribution.objects.filter(user=self.ivan).count(), 1)
        self.assertIn(Decimal("6"), [Decimal(v) for v in state.params().values()])
