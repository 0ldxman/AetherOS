"""Почта узла: видимость писем, прочитанность, API, админка, приветствие.

Запуск: python manage.py test mail
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from machines.models import Machine, MachineApp, MachineProfile
from mail.access import Viewer, mark_read, mark_unread, read_ids, summary, visible_messages
from mail.models import Attachment, Message, MessageRead
from secure.models import Key
from users.models import UserKey


def make_message(**fields):
    data = {
        "sender_name": "██████",
        "sender_address": "██████@aether-core",
        "subject": "for you",
        "body": "come in.\n\nclose the door behind you.",
        "sent_at": datetime(2030, 11, 14, 3, 11, tzinfo=timezone.utc),
    }
    data.update(fields)
    return Message.objects.create(**data)


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")

    def viewer(self, login="witness", machine=None, keys=(), **extra):
        return Viewer(login=login, machine=machine or self.null, keys=frozenset(keys), **extra)

    def ids(self, viewer):
        return {m.pk for m in visible_messages(viewer)}

    def test_a_message_belongs_to_its_machine(self):
        here = make_message(machine=self.null)
        there = make_message(machine=self.main)
        self.assertEqual(self.ids(self.viewer(machine=self.null)), {here.pk})
        self.assertEqual(self.ids(self.viewer(machine=self.main)), {there.pk})

    def test_a_message_without_a_machine_is_on_every_machine(self):
        everywhere = make_message(machine=None)
        for machine in (self.main, self.null):
            self.assertEqual(self.ids(self.viewer(machine=machine)), {everywhere.pk})

    def test_an_addressed_message_is_only_for_that_login(self):
        mine = make_message(to_login="witness")
        self.assertEqual(self.ids(self.viewer(login="witness")), {mine.pk})
        self.assertEqual(self.ids(self.viewer(login="WITNESS")), {mine.pk})    # регистр не важен
        self.assertEqual(self.ids(self.viewer(login="ivan")), set())

    def test_a_message_without_an_addressee_is_for_everyone(self):
        open_letter = make_message(to_login="")
        self.assertEqual(self.ids(self.viewer(login="ivan")), {open_letter.pk})

    def test_keys_decide_who_sees_a_message(self):
        locked = make_message(key_condition="the_door")
        either = make_message(key_condition={"any": ["a", "b"]})
        self.assertEqual(self.ids(self.viewer()), set())
        self.assertEqual(self.ids(self.viewer(keys=["the_door"])), {locked.pk})
        self.assertEqual(self.ids(self.viewer(keys=["b"])), {either.pk})

    def test_the_newest_message_comes_first(self):
        old = make_message(sent_at=datetime(2027, 10, 1, tzinfo=timezone.utc))
        new = make_message(sent_at=datetime(2030, 11, 14, tzinfo=timezone.utc))
        self.assertEqual([m.pk for m in visible_messages(self.viewer())], [new.pk, old.pk])


class ReadStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        cls.message = make_message()
        cls.ivan = get_user_model().objects.create_user("ivan", password="pw")
        cls.olga = get_user_model().objects.create_user("olga", password="pw")

    def viewer(self, **extra):
        return Viewer(login="witness", machine=self.null, keys=frozenset(), **extra)

    def test_a_signed_in_player_is_tracked_by_the_account(self):
        viewer = self.viewer(user=self.ivan)
        mark_read(viewer, self.message)
        mark_read(viewer, self.message)             # повтор не плодит записи
        self.assertEqual(read_ids(viewer), {self.message.pk})
        self.assertEqual(MessageRead.objects.count(), 1)
        self.assertEqual(read_ids(self.viewer(user=self.olga)), set())

    def test_an_anonymous_player_is_tracked_by_the_session(self):
        mine, theirs = self.viewer(session_key="abc123"), self.viewer(session_key="zzz999")
        mark_read(mine, self.message)
        self.assertEqual(read_ids(mine), {self.message.pk})
        self.assertEqual(read_ids(theirs), set())

    def test_a_viewer_without_an_identity_reads_nothing_and_marks_nothing(self):
        nobody = self.viewer()
        mark_read(nobody, self.message)
        self.assertEqual(MessageRead.objects.count(), 0)
        self.assertEqual(read_ids(nobody), set())

    def test_mark_unread_forgets_only_this_readers_mark(self):
        a, b = self.viewer(user=self.ivan), self.viewer(user=self.olga)
        mark_read(a, self.message)
        mark_read(b, self.message)
        mark_unread(a, self.message)
        self.assertEqual(read_ids(a), set())
        self.assertEqual(read_ids(b), {self.message.pk})

    def test_the_summary_counts_unread_and_names_the_latest_sender(self):
        newest = make_message(sender_name="zero", sent_at=datetime(2030, 11, 14, 3, 11, tzinfo=timezone.utc))
        data = summary(self.viewer(user=self.ivan))
        self.assertEqual(data["unread"], 2)
        self.assertEqual((data["sender"], data["ago"]), ("zero", "3 min"))
        mark_read(self.viewer(user=self.ivan), newest)
        mark_read(self.viewer(user=self.ivan), self.message)
        self.assertEqual(summary(self.viewer(user=self.ivan)), {"unread": 0, "sender": "", "ago": ""})


@override_settings(FORCE_SCRIPT_NAME=None)
class InboxApiTests(TestCase):
    """Окно почты и его API: игрок на aether-null, у машины есть иконка intercom."""

    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        for machine in (cls.main, cls.null):
            MachineApp.objects.create(machine=machine, label="intercom", glyph="@", path="/apps/mail/")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def witness(self):
        session = self.client.session
        session["guest"] = True
        session.save()

    def get_json(self, name, *args):
        response = self.client.get(reverse(name, args=args))
        return response, (json.loads(response.content) if response["Content-Type"] == "application/json" else None)

    def test_the_window_needs_a_connected_player(self):
        # ни машины, ни иконки: до вида письма дело не доходит
        self.assertEqual(self.client.get(reverse("mail:inbox")).status_code, 403)
        self.assertEqual(self.client.get(reverse("mail:messages")).status_code, 403)

    def test_the_machine_must_have_the_intercom_icon(self):
        MachineApp.objects.filter(machine=self.null).delete()
        self.witness()
        self.assertEqual(self.client.get(reverse("mail:inbox")).status_code, 403)

    def test_the_window_is_a_shell_with_the_players_address(self):
        self.witness()
        response = self.client.get(reverse("mail:inbox"))
        self.assertContains(response, "witness@aether-null")
        for element in ('id="mail-list"', 'id="mail-folders"', 'id="mail-labels"', 'id="mail-reader"',
                        'id="mail-compose"', 'id="mail-status"'):
            self.assertContains(response, element)
        self.assertContains(response, "mail/mail.js")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_the_list_shows_unread_and_a_preview(self):
        make_message(machine=self.null, subject="the door", body="come in.\n\nquietly.")
        self.witness()
        _, data = self.get_json("mail:messages")
        (row,) = data["messages"]
        self.assertEqual((row["sender"], row["subject"], row["unread"]), ("██████", "the door", True))
        self.assertEqual(row["when"], "2030-11-14 03:11 UTC")
        self.assertEqual(row["preview"], "come in. quietly.")

    def test_the_card_has_a_label_with_a_tone(self):
        make_message(machine=self.null, label="system", label_tone="info")
        make_message(machine=self.null, subject="plain")
        self.witness()
        _, data = self.get_json("mail:messages")
        by_subject = {row["subject"]: row for row in data["messages"]}
        self.assertEqual((by_subject["for you"]["label"], by_subject["for you"]["tone"]), ("system", "info"))
        self.assertEqual((by_subject["plain"]["label"], by_subject["plain"]["tone"]), ("", "dim"))

    def test_the_card_preview_has_no_markup_marks(self):
        make_message(machine=self.null, body="## the door\n\n- **open** since `monday`\n> *quiet*")
        self.witness()
        _, data = self.get_json("mail:messages")
        self.assertEqual(data["messages"][0]["preview"], "the door open since monday quiet")

    def test_the_full_text_keeps_its_markup_for_the_reader(self):
        message = make_message(machine=self.null, body="## the door\n\n- **open**")
        self.witness()
        _, data = self.get_json("mail:message", message.pk)
        self.assertEqual(data["body"], "## the door\n\n- **open**")

    def test_opening_a_message_marks_it_read_and_returns_everything(self):
        message = make_message(machine=self.null, to_login="witness")
        Attachment.objects.create(message=message, label="first file", path="/apps/mail/", order=1)
        self.witness()
        _, data = self.get_json("mail:message", message.pk)
        self.assertEqual(data["from"], "██████ <██████@aether-core>")
        self.assertEqual((data["to"], data["body"]), ("witness", message.body))
        self.assertEqual(data["attachments"], [{"label": "first file", "url": "/apps/mail/"}])
        self.assertFalse(data["unread"])
        _, listing = self.get_json("mail:messages")
        self.assertFalse(listing["messages"][0]["unread"])

    def test_mark_unread_brings_the_dot_back(self):
        message = make_message(machine=self.null)
        self.witness()
        self.get_json("mail:message", message.pk)
        self.client.post(reverse("mail:unread", args=[message.pk]))
        _, listing = self.get_json("mail:messages")
        self.assertTrue(listing["messages"][0]["unread"])

    def test_unread_needs_post(self):
        message = make_message(machine=self.null)
        self.witness()
        self.assertEqual(self.client.get(reverse("mail:unread", args=[message.pk])).status_code, 405)

    def test_a_hidden_message_does_not_exist_for_the_player(self):
        for hidden in (
            make_message(machine=self.main),                        # чужая машина
            make_message(machine=self.null, to_login="ivan"),       # чужой адресат
            make_message(machine=self.null, key_condition="nope"),  # нет ключа
        ):
            self.witness()
            self.assertEqual(self.client.get(reverse("mail:message", args=[hidden.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("mail:unread", args=[hidden.pk])).status_code, 404)
            self.assertEqual(MessageRead.objects.count(), 0)

    def test_a_player_with_the_key_sees_the_locked_message(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        message = make_message(machine=self.main, key_condition="the_door")
        self.client.force_login(user)
        _, data = self.get_json("mail:messages")
        self.assertEqual(data["messages"], [])                    # ключа ещё нет
        UserKey.objects.create(user=user, key=Key.objects.create(slug="the_door"))
        _, data = self.get_json("mail:messages")
        self.assertEqual([row["id"] for row in data["messages"]], [message.pk])

    def test_the_body_is_data_not_markup(self):
        make_message(machine=self.null, body="<script>alert(1)</script>")
        self.witness()
        _, listing = self.get_json("mail:messages")
        self.assertIn("<script>", listing["messages"][0]["preview"])      # как текст, браузер вставит через textContent
        self.assertEqual(self.client.get(reverse("mail:inbox")).content.decode().count("<script>alert"), 0)

    def test_two_witnesses_do_not_share_what_they_have_read(self):
        message = make_message(machine=self.null)
        self.witness()
        self.get_json("mail:message", message.pk)
        from django.test import Client

        other = Client()
        session = other.session
        session["guest"] = True
        session.save()
        other.cookies["sessionid"] = session.session_key
        data = json.loads(other.get(reverse("mail:messages")).content)
        self.assertTrue(data["messages"][0]["unread"])

    def test_attachments_open_inside_the_project_only(self):
        from django.core.exceptions import ValidationError

        message = make_message()
        for bad in ("https://evil.example/", "//evil.example/", "apps/wiki/", "/no/such/page/", "/a\\b/"):
            with self.assertRaises(ValidationError, msg=bad):
                Attachment(message=message, label="x", path=bad).full_clean()
        Attachment(message=message, label="x", path="/apps/mail/").full_clean()


class StylesTests(TestCase):
    def test_the_stylesheet_uses_only_design_tokens(self):
        css = (Path(__file__).resolve().parent / "static/mail/mail.css").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", css), [])
        self.assertNotIn(":root", css)
        self.assertNotRegex(css, r"rgba?\(")

    def test_the_script_never_writes_server_text_as_html(self):
        js = (Path(__file__).resolve().parent / "static/mail/mail.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("insertAdjacentHTML", js)


class LookTests(TestCase):
    """Почта выглядит как остальные приложения (вики, карта), а не как терминал."""

    def css(self):
        return (Path(__file__).resolve().parent / "static/mail/mail.css").read_text(encoding="utf-8")

    def test_the_window_uses_the_interface_font_size_and_colors(self):
        css = self.css()
        for token in ("--font-main", "--fg", "--font-light", "--font-muted", "--accent", "--panel", "--line", "--radius"):
            self.assertIn(f"var({token})", css)
        self.assertIn("font-size: 81.25%", css)            # 13px, как в вики

    def test_the_terminal_palette_and_font_are_not_used_here(self):
        css = self.css()
        for token in ("--font-console", "--fs-console", "--lh-console", "--term-"):
            self.assertNotIn(token, css)

    def test_the_status_colors_come_from_the_status_tokens(self):
        css = self.css()
        for token in ("--status-ok", "--status-warn", "--status-info", "--status-error"):
            self.assertIn(f"var({token})", css)

    def test_the_script_renders_a_small_safe_markup(self):
        js = (Path(__file__).resolve().parent / "static/mail/mail.js").read_text(encoding="utf-8")
        for helper in ("renderBody", "md-strong", "md-quote", "md-list", "md-h"):
            self.assertIn(helper, js)

    def test_compose_is_disabled_while_the_core_is_silent(self):
        js = (Path(__file__).resolve().parent / "static/mail/mail.js").read_text(encoding="utf-8")
        self.assertIn("core unreachable", js)


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("root", password="pw")
        cls.machine = Machine.objects.create(name="Null", hostname="aether-null")
        cls.message = make_message(machine=cls.machine, key_condition="the_door", label="personal")

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.client.force_login(self.admin)

    @override_settings(FORCE_SCRIPT_NAME=None)
    def test_pages_open(self):
        for name, args in (
            ("admin:mail_message_changelist", ()),
            ("admin:mail_message_add", ()),
            ("admin:mail_message_change", (self.message.pk,)),
            ("admin:mail_messageread_changelist", ()),
        ):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)

    @override_settings(FORCE_SCRIPT_NAME=None)
    def test_the_list_shows_the_key_condition_and_readers(self):
        mark_read(Viewer("x", self.machine, frozenset(), session_key="abc"), self.message)
        response = self.client.get(reverse("admin:mail_message_changelist"))
        self.assertContains(response, "the_door")
        self.assertContains(response, "██████")
        self.assertContains(response, "personal")

    def test_the_key_usage_lists_the_letter(self):
        from secure.usage import key_usage, used_slugs

        usage = key_usage("the_door")
        self.assertEqual([(u.kind, u.url) for u in usage],
                         [("письмо", reverse("admin:mail_message_change", args=[self.message.pk]))])
        self.assertIn("the_door", used_slugs())


@override_settings(FORCE_SCRIPT_NAME=None)
class GreetingTests(TestCase):
    """Приветствие узла берёт непрочитанное из почты."""

    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")

    def scenes(self, session=None):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from users.aether_auth import gateway_scenes

        request = RequestFactory().get("/lock/")
        request.user = AnonymousUser()
        request.session = session if session is not None else {}
        return gateway_scenes(request)

    def screen(self, scene):
        return "".join(
            step["value"] if step["op"] == "text" else "\n" if step["op"] == "newline" else ""
            for step in scene
        )

    def test_no_mail_no_claim(self):
        self.assertIn("intercom: no new messages", self.screen(self.scenes()["established"]))

    def test_an_unread_letter_is_announced_with_its_sender_and_age(self):
        make_message(machine=self.null, sender_name="██████")
        text = self.screen(self.scenes()["established"])
        self.assertIn("intercom: 1 unread message  (latest from ██████, 3 min ago)", text)

    def test_the_number_follows_the_database(self):
        make_message(machine=self.null)
        make_message(machine=self.null)
        make_message(machine=self.main)               # чужая машина: не считается
        make_message(machine=self.null, key_condition="locked")      # скрытое: не считается
        text = self.screen(self.scenes()["established"])
        self.assertIn("2 unread messages", text)

    def test_a_missing_witness_machine_does_not_break_the_screen(self):
        Machine.objects.filter(hostname="aether-null").delete()
        self.assertIn("no new messages", self.screen(self.scenes()["established"]))
