"""Реплики персонажа: ответ в почту, на форум, в эфир; отложенные; отмена; действия мира; история с игроком."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from air import radio
from air.models import Station, Transmission
from characters import inbox, outbox
from characters.models import Character, Inbound, Reply
from filesystem.testing import make_app
from forum import logic
from forum.models import Post, Section, Space
from machines.models import Machine, MachineProfile
from mail.boxes import Box
from mail.models import Persona
from world.models import WorldFlag


class OutboxTests(TestCase):
    def setUp(self):
        self.op = Character.objects.create(code="OP7", name="Operator 7", callsign="OPERATOR-7")
        self.station = Station.objects.create(name="OPERATOR-7", kind="character", character=self.op)
        self.persona = Persona.objects.create(address="op7@core", character=self.op)
        self.boss = get_user_model().objects.create_user("boss", is_staff=True)
        self.ivan = get_user_model().objects.create_user("ivan")
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        make_app(self.main, label="mail", icon="mail", path="/apps/mail/")
        self.profile = MachineProfile.objects.create(machine=self.main, user=self.ivan, name="Ivan", login="ivan", freq=1)

    def mail_in(self):
        return inbox.capture_mail(self.persona, self.ivan, self.profile.mail, "the file", "what is on line 4?", self.main, "/var/mail/ivan/sent/1.msg")

    def test_mail_answer_lands_in_the_player_inbox_from_the_same_address(self):
        reply = outbox.answer(self.mail_in(), self.boss, "Nothing you should read.")
        self.assertEqual((reply.status, reply.subject, reply.ref["from"]), ("sent", "Re: the file", "op7@core"))
        rows = Box.of_profile(self.profile, user=self.ivan).letters_in("inbox")
        self.assertEqual([(r.letter.sender, r.letter.subject) for r in rows], [("op7@core", "Re: the file")])
        self.assertEqual(Inbound.objects.get().status, "answered")

    def test_forum_answer_goes_under_the_players_post(self):
        section = Section.objects.create(space=Space.objects.create(slug="net", title="Net"), title="General")
        topic = logic.author_topic(section, "", "Shift", "log", character=self.op)
        post = logic.reply(topic, self.ivan, "who are you?", set())
        found = Inbound.objects.get(channel="forum")
        outbox.answer(found, self.boss, "The night shift.")
        answer = Post.objects.filter(topic=topic, character=self.op, root=False).get()
        self.assertEqual((answer.parent_id, answer.name), (post.pk, "OPERATOR-7"))

    def test_air_answer_is_transmitted_by_the_station(self):
        radio.transmit(self.ivan, radio.CALLING, "OPERATOR-7 DE IVAN")
        outbox.answer(Inbound.objects.get(channel="air"), self.boss, "IVAN DE OPERATOR-7 QSL")
        self.assertTrue(Transmission.objects.filter(station=self.station, text="IVAN DE OPERATOR-7 QSL").exists())

    def test_delayed_reply_waits_then_goes_on_tick_and_can_be_cancelled(self):
        reply = outbox.answer(self.mail_in(), self.boss, "later", delay_minutes=30)
        self.assertEqual(reply.status, "pending")
        self.assertEqual(outbox.tick(force=True), 0)
        Reply.objects.filter(pk=reply.pk).update(send_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(outbox.tick(force=True), 1)
        self.assertEqual(Reply.objects.get(pk=reply.pk).status, "sent")
        other = outbox.answer(self.mail_in(), self.boss, "never", delay_minutes=30)
        outbox.cancel(other)
        Reply.objects.filter(pk=other.pk).update(send_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(outbox.tick(force=True), 0)
        with self.assertRaises(outbox.OutboxError):
            outbox.cancel(Reply.objects.get(pk=reply.pk))

    def test_world_actions_run_on_delivery_and_bad_ones_are_refused(self):
        outbox.answer(self.mail_in(), self.boss, "go", actions=[{"do": "flag", "name": "op7-met"}])
        self.assertTrue(WorldFlag.objects.get(name="op7-met").on)
        with self.assertRaises(outbox.OutboxError):
            outbox.answer(self.mail_in(), self.boss, "x", actions=[{"do": "explode"}])

    def test_failure_is_recorded_not_raised(self):
        found = self.mail_in()
        found.sender = "nobody@nowhere"
        found.save()
        reply = outbox.answer(found, self.boss, "hello?")
        self.assertEqual(reply.status, "failed")
        self.assertIn("nobody@nowhere", reply.error)

    def test_history_with_the_player_across_channels(self):
        outbox.answer(self.mail_in(), self.boss, "answer one")
        rows = outbox.history(self.op, self.ivan)
        self.assertEqual([(r["kind"], r["channel"]) for r in rows], [("in", "mail"), ("out", "mail")])
        self.assertEqual(rows[1]["author"], "boss")

    def test_empty_text_and_missing_channel(self):
        with self.assertRaises(outbox.OutboxError):
            outbox.answer(self.mail_in(), self.boss, "  ")
        lonely = Character.objects.create(code="LON", name="Lonely")
        row = Inbound.objects.create(character=lonely, channel="air", sender="IVAN", text="LONELY?", ref={"freq": "14.230"})
        with self.assertRaises(outbox.OutboxError):
            outbox.answer(row, self.boss, "hi")
