"""Входящие персонажа: упоминание полным позывным, ответы на форуме, эфир, письма вне сценария, статусы."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from air import radio
from air.models import Station
from characters import inbox
from characters.models import Character, Inbound
from forum import logic
from forum.models import Section, Space
from mail.models import Persona


class InboxTests(TestCase):
    def setUp(self):
        self.op = Character.objects.create(code="OP7", name="Operator 7", callsign="OPERATOR-7")
        self.warden = Character.objects.create(code="WAR", name="Warden")
        Station.objects.create(name="WARDEN", kind="character", character=self.warden)
        self.ivan = get_user_model().objects.create_user("ivan")
        self.section = Section.objects.create(space=Space.objects.create(slug="net", title="Net"), title="General")

    def test_only_the_full_callsign_counts(self):
        self.assertEqual(inbox.mentioned("hey operator-7, and warden?"), [self.op, self.warden])
        self.assertEqual(inbox.mentioned("OP7 or operator 7 or OPERATOR-77 or XWARDEN"), [])

    def test_forum_reply_to_a_character_and_mention(self):
        topic = logic.author_topic(self.section, "", "Shift log", "nothing", character=self.op)
        logic.reply(topic, self.ivan, "who are you?", set())
        logic.start_topic(self.section, self.ivan, "Question", "WARDEN, open the gate", set())
        rows = list(Inbound.objects.order_by("id").values_list("character__code", "channel", "subject"))
        self.assertEqual(rows, [("OP7", "forum", "Shift log"), ("WAR", "forum", "Question")])
        plain = logic.start_topic(self.section, self.ivan, "Other", "nobody here", set())
        self.assertFalse(Inbound.objects.filter(ref__topic=plain.pk).exists())

    def test_air_transmission_with_a_callsign(self):
        sent = radio.transmit(self.ivan, radio.CALLING, "WARDEN DE IVAN, do you copy")
        row = Inbound.objects.get()
        self.assertEqual((row.character, row.channel, row.ref["transmission"], row.sender), (self.warden, "air", sent.pk, sent.callsign))

    def test_mail_without_a_variant_is_captured_for_the_character(self):
        persona = Persona.objects.create(address="op7@core", character=self.op)
        made = inbox.capture_mail(persona, self.ivan, "ivan@main", "hello", "are you there", None, "/var/mail/ivan/sent/1.msg")
        self.assertEqual((made.channel, made.subject, made.ref["path"]), ("mail", "hello", "/var/mail/ivan/sent/1.msg"))
        self.assertIsNone(inbox.capture_mail(Persona.objects.create(address="nobody@core"), self.ivan, "a", "b", "c", None, "p"))

    def test_status_and_counts(self):
        row = Inbound.objects.create(character=self.op, channel="mail", sender="x", text="t")
        Inbound.objects.create(character=self.op, channel="air", sender="x", text="t")
        self.assertEqual(inbox.counts(self.op), {"mail": 1, "forum": 0, "air": 1})
        author = get_user_model().objects.create_user("boss", is_staff=True)
        inbox.set_status(row, "taken", author)
        self.assertEqual((row.taken_by, inbox.counts(self.op)["mail"]), (author, 0))
        inbox.set_status(row, "new", author)
        self.assertIsNone(row.taken_by)
