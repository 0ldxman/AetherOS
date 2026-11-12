"""Мост эфира с Discord: очередь в канал, сообщения канала в эфир, скрытие, аренда бота, раздел Студии."""
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from air import bridge, cipher, radio
from air.models import BridgeLink, BridgeMessage, BridgeState, Station, Transmission
from team.testing import full_role


class BridgeTests(TestCase):
    def setUp(self):
        self.link = BridgeLink.objects.create(freq=Decimal("14.230"), channel_id="123456789012345678")
        self.ivan = get_user_model().objects.create_user("ivan")
        SocialAccount.objects.create(user=self.ivan, provider="discord", uid="555", extra_data={"username": "ivan_d"})
        self.now = timezone.now()

    def test_transmissions_of_a_bridged_frequency_queue_as_heard_without_a_key(self):
        radio.transmit(self.ivan, "14.230", "hello all", now=self.now)
        radio.transmit(self.ivan, "14.230", "meet at dawn", now=self.now + timedelta(seconds=3), air_key="orpheus")
        radio.transmit(self.ivan, "7.115", "elsewhere", now=self.now + timedelta(seconds=6))
        radio.station_transmit(Station.objects.create(name="CORE"), "14.230", "carrier lost")
        Transmission.objects.create(freq=Decimal("14.230"), callsign="X", text="secret", condition="k")       # под условием: нет
        texts = [text for _, _, text in bridge.outbox()]
        self.assertEqual(texts[0], "`14.230` **IVAN-D**: hello all")
        self.assertEqual(texts[1], "`14.230` **IVAN-D**: " + cipher.encrypt("meet at dawn", "orpheus"))
        self.assertEqual(texts[2], "`14.230` **CORE**: carrier lost")
        self.assertEqual(len(texts), 3)
        first = bridge.outbox()[0][0]
        bridge.sent(first, 999)
        self.assertEqual(len(bridge.outbox()), 2)
        for _ in range(bridge.MAX_ATTEMPTS):
            bridge.failed(bridge.outbox()[0][0], "403 Forbidden")
        self.assertEqual(BridgeMessage.objects.filter(state="failed").count(), 1)

    def test_hiding_deletes_in_discord_and_unhiding_posts_again(self):
        sent = radio.transmit(self.ivan, "14.230", "spam", now=self.now)
        row = BridgeMessage.objects.get(transmission=sent)
        bridge.sent(row.pk, 999)
        radio.hide(sent, None, "spam")
        self.assertEqual(bridge.to_delete(), [(row.pk, "123456789012345678", "999")])
        bridge.deleted(row.pk)
        radio.unhide(sent)
        self.assertEqual([pk for pk, _, _ in bridge.outbox()], [row.pk])

    def test_discord_messages_go_on_air_from_the_players_callsign(self):
        made, reason = bridge.inbound("123456789012345678", "555", "hi from discord", "42")
        self.assertEqual((made.callsign, made.text, made.via, reason), ("IVAN-D", "hi from discord", "discord", ""))
        self.assertEqual(bridge.outbox(), [])                                   # своё обратно в канал не уходит
        self.assertEqual(bridge.inbound("123456789012345678", "777", "who am i", "43"), (None, "sign in to the game with Discord to transmit"))
        self.assertEqual(bridge.inbound("1", "555", "x", "44")[1], "no bridge")
        radio.callsign_of(self.ivan).__class__.objects.filter(user=self.ivan).update(rx_only=True)
        self.assertEqual(bridge.inbound("123456789012345678", "555", "again", "45")[1], "transmitter disabled")
        radio.hide(made, None)
        self.assertEqual(bridge.to_delete()[0][2], "42")                        # скрытие удаляет и исходное сообщение в Discord

    def test_only_one_process_holds_the_bot(self):
        self.assertTrue(bridge.lease("a:1", "AIR#0001"))
        self.assertFalse(bridge.lease("b:2"))
        self.assertTrue(bridge.lease("a:1"))
        BridgeState.objects.filter(pk=1).update(seen_at=timezone.now() - timedelta(minutes=5))
        self.assertTrue(bridge.lease("b:2"))                                     # упавший отдаёт мост
        with mock.patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "x"}):
            self.assertEqual({k: v for k, v in bridge.status().items() if k in ("token", "online", "bot")}, {"token": True, "online": True, "bot": "AIR#0001"})
        bridge.release("b:2")
        self.assertFalse(bridge.status()["online"])

    def test_the_bot_client_builds_without_connecting(self):
        from air import discord_bot

        client = discord_bot._client_class()("a:1")
        self.assertTrue(client.intents.message_content)
        with mock.patch.dict("os.environ", {"DISCORD_BOT_TOKEN": ""}):
            self.assertIsNone(discord_bot.run())                                 # без токена ничего не делает


class BridgeApiTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"/studio/api{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_links_and_status(self):
        status, data = self.call("get", "/air/bridges")
        self.assertEqual((status, data["links"], data["status"]["online"]), (200, [], False))
        self.assertEqual(self.call("post", "/air/bridges", {"freq": "14.230", "channel_id": "general"})[0], 400)
        status, made = self.call("post", "/air/bridges", {"freq": "14.230", "channel_id": "123456789012345678", "label": "#эфир"})
        self.assertEqual((status, made["freq"], made["sent"]), (200, "14.230", 0))
        self.assertEqual(self.call("post", "/air/bridges", {"freq": "14.230", "channel_id": "223456789012345678"})[0], 400)
        self.assertFalse(self.call("put", f"/air/bridges/{made['id']}", {**made, "active": False})[1]["active"])
        self.assertEqual(self.call("delete", f"/air/bridges/{made['id']}")[0], 204)
