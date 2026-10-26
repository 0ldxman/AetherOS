"""Почта узла: видимость писем, прочитанность, API, админка, приветствие.

Запуск: python manage.py test mail
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import get_script_prefix, reverse, set_script_prefix

from machines.models import Machine, MachineApp, MachineProfile
from mail.addresses import matches, matches_any, split, validate_address, validate_masks
from mail.access import Viewer, mark_read, mark_unread, read_ids, summary, visible_messages
from mail.models import Attachment, ComposeProgress, Delivered, Message, MessageRead, Trashed
from secure.models import Key
from users.models import UserKey


def make_message(**fields):
    data = {
        "sender": "██████@aether-core",
        "recipients": "*",
        "subject": "for you",
        "body": "come in.\n\nclose the door behind you.",
        "sent_at": datetime(2030, 11, 14, 3, 11, tzinfo=timezone.utc),
    }
    data.update(fields)
    return Message.objects.create(**data)


class AccessTests(TestCase):
    def viewer(self, address="witness@aether-null", keys=(), **extra):
        return Viewer(address=address, keys=frozenset(keys), **extra)

    def ids(self, viewer):
        return {m.pk for m in visible_messages(viewer)}

    def test_a_message_is_for_its_recipients(self):
        mine = make_message(recipients="ivan@aether-null")
        self.assertEqual(self.ids(self.viewer("ivan@aether-null")), {mine.pk})
        self.assertEqual(self.ids(self.viewer("IVAN@aether-null")), {mine.pk})       # регистр не важен
        self.assertEqual(self.ids(self.viewer("olga@aether-null")), set())
        self.assertEqual(self.ids(self.viewer("ivan@aether-main")), set())            # тот же логин на другой машине это другой адрес

    def test_several_recipients_may_be_listed(self):
        letter = make_message(recipients="ivan@aether-null\nolga@apollo.mail, zero@aether-core")
        for address in ("ivan@aether-null", "olga@apollo.mail", "zero@aether-core"):
            self.assertEqual(self.ids(self.viewer(address)), {letter.pk}, address)
        self.assertEqual(self.ids(self.viewer("kate@apollo.mail")), set())

    def test_a_mask_stands_for_any_characters(self):
        letter = make_message(recipients="*@aether-*")
        for address in ("witness@aether-null", "ivan@aether-main", "x@aether-"):
            self.assertEqual(self.ids(self.viewer(address)), {letter.pk}, address)
        for address in ("ivan@apollo.mail", "ivan@xaether-main"):
            self.assertEqual(self.ids(self.viewer(address)), set(), address)

    def test_a_lone_star_is_everyone(self):
        letter = make_message(recipients="*")
        self.assertEqual(self.ids(self.viewer("anyone@anywhere")), {letter.pk})

    def test_a_letter_without_recipients_is_for_nobody(self):
        make_message(recipients="")
        self.assertEqual(self.ids(self.viewer()), set())

    def test_the_dots_in_a_mask_are_not_wildcards(self):
        self.assertTrue(matches("ivan@apollo.mail", "ivan@apollo.mail"))
        self.assertFalse(matches("ivan@apollo.mail", "ivan@apolloxmail"))

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


class SelfMailFolderTests(TestCase):
    def test_message_to_myself_is_in_inbox_and_sent(self):
        from .access import Viewer, visible_messages
        make_message(sender="me@aether-main", recipients="me@aether-main, *@aether-main")
        viewer = Viewer(address="me@aether-main", keys=frozenset())
        self.assertEqual([m.folder for m in visible_messages(viewer)], ["inbox", "sent"])
        self.assertEqual(len(visible_messages(viewer, "sent")), 1)
        self.assertEqual(len(visible_messages(viewer, "inbox")), 1)


class RecipientsLineTests(TestCase):
    def test_reader_sees_own_address_and_full_addresses_only(self):
        from .addresses import recipients_line
        masks = "*@aether-main\n*@aether-null\njohn_snow@aether-core"
        self.assertEqual(
            recipients_line(masks, "oldman@aether-main"),
            "oldman@aether-main, john_snow@aether-core and +1",
        )

    def test_no_hidden_masks_no_tail(self):
        from .addresses import recipients_line
        self.assertEqual(recipients_line("a@x, *@x", "a@x"), "a@x")
        self.assertEqual(recipients_line("*@y", "a@x"), "+1")


class AddressTests(TestCase):
    def test_split_accepts_lines_commas_and_spaces(self):
        self.assertEqual(split("a@b\nc@d, e@f;  g@h"), ["a@b", "c@d", "e@f", "g@h"])
        self.assertEqual(split(""), [])

    def test_an_address_is_name_at_host(self):
        validate_address("will_smith@apollo.mail")
        for bad in ("", "will_smith", "a@b@c", "a b@c", "*@apollo.mail", "a@"):
            with self.assertRaises(ValidationError, msg=bad):
                validate_address(bad)

    def test_masks_may_have_stars(self):
        validate_masks("*\n*@aether-*\nivan@apollo.mail")
        for bad in ("ivan", "a@b@c"):
            with self.assertRaises(ValidationError, msg=bad):
                validate_masks(bad)

    def test_matches_any_looks_through_the_whole_list(self):
        self.assertTrue(matches_any("a@b\nc@*", "c@d"))
        self.assertFalse(matches_any("a@b\nc@*", "e@d"))


class ProfileMailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = Machine.objects.create(name="Staff", hostname="apollo-staff")

    def test_an_explicit_address_is_kept(self):
        profile = MachineProfile.objects.create(machine=self.staff, name="W", login="will_smith", freq=1, mail="will@apollo.mail")
        self.assertEqual(profile.mail, "will@apollo.mail")

    def test_a_profile_saved_without_an_address_gets_login_at_hostname(self):
        profile = MachineProfile.objects.create(machine=self.staff, name="W", login="will_smith", freq=2)
        self.assertEqual(profile.mail, "will_smith@apollo-staff")

    def test_the_address_is_required_and_checked_in_forms(self):
        profile = MachineProfile(machine=self.staff, name="W", login="w", freq=3, mail="")
        with self.assertRaises(ValidationError) as caught:
            profile.full_clean()
        self.assertIn("mail", caught.exception.message_dict)
        profile.mail = "no at sign"
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_two_profiles_may_share_an_address(self):
        MachineProfile.objects.create(machine=self.staff, name="A", login="a", freq=1, mail="boss@apollo.mail")
        MachineProfile.objects.create(machine=self.staff, name="B", login="b", freq=1, mail="boss@apollo.mail")


class ReadStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        cls.message = make_message()
        cls.ivan = get_user_model().objects.create_user("ivan", password="pw")
        cls.olga = get_user_model().objects.create_user("olga", password="pw")

    def viewer(self, **extra):
        return Viewer(address="witness@aether-null", keys=frozenset(), **extra)

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
        newest = make_message(sender="zero@aether-core", sent_at=datetime(2030, 11, 14, 3, 11, tzinfo=timezone.utc))
        data = summary(self.viewer(user=self.ivan))
        self.assertEqual(data["unread"], 2)
        self.assertEqual((data["sender"], data["ago"]), ("zero@aether-core", "3 min"))
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
        cache.clear()      # кэш пережил бы откат базы между тестами
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

    def test_pulse_counts_unread_and_shrinks_after_reading(self):
        first = make_message(subject="the door")
        self.witness()
        _, data = self.get_json("mail:pulse")
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["messages"][0]["id"], first.pk)
        self.assertEqual(data["messages"][0]["subject"], "the door")
        self.get_json("mail:message", first.pk)
        _, data = self.get_json("mail:pulse")
        self.assertEqual((data["unread"], data["messages"]), (0, []))

    def test_pulse_is_cached_and_new_mail_drops_the_cache(self):
        make_message(subject="first")
        self.witness()
        self.get_json("mail:pulse")
        with CaptureQueriesContext(connection) as queries:
            _, data = self.get_json("mail:pulse")
        self.assertFalse([q for q in queries if "mail_message" in q["sql"]])
        self.assertEqual(data["unread"], 1)
        make_message(subject="second")
        _, data = self.get_json("mail:pulse")
        self.assertEqual(data["unread"], 2)

    def test_the_list_is_cached_and_follows_reading(self):
        first = make_message(subject="first")
        self.witness()
        _, data = self.get_json("mail:messages")
        self.assertTrue(data["messages"][0]["unread"])
        self.get_json("mail:messages")
        self.get_json("mail:message", first.pk)
        _, data = self.get_json("mail:messages")
        self.assertFalse(data["messages"][0]["unread"])

    def test_pulse_ignores_mail_of_other_addresses_in_the_query(self):
        for n in range(30):
            make_message(subject=f"to someone {n}", recipients="other@aether-core")
        make_message(subject="mine")
        self.witness()
        _, data = self.get_json("mail:pulse")
        self.assertEqual([m["subject"] for m in data["messages"]], ["mine"])

    def test_pulse_needs_a_connected_player(self):
        self.assertEqual(self.client.get(reverse("mail:pulse")).status_code, 403)

    def test_the_desktop_polls_mail_only_with_the_intercom_icon(self):
        self.witness()
        page = self.client.get(reverse("desktop")).content.decode()
        self.assertIn('data-mail-pulse-url="/apps/mail/api/pulse/"', page)
        MachineApp.objects.filter(machine=self.null).delete()
        page = self.client.get(reverse("desktop")).content.decode()
        self.assertIn('data-mail-pulse-url=""', page)

    def test_the_list_shows_unread_and_a_preview(self):
        make_message(subject="the door", body="come in.\n\nquietly.")
        self.witness()
        _, data = self.get_json("mail:messages")
        (row,) = data["messages"]
        self.assertEqual((row["sender"], row["subject"], row["unread"]), ("██████@aether-core", "the door", True))
        self.assertEqual(row["when"], "2030-11-14 03:11 UTC")
        self.assertEqual(row["preview"], "come in. quietly.")

    def test_the_card_has_a_label_with_a_tone(self):
        make_message(label="system", label_tone="info")
        make_message(subject="plain")
        self.witness()
        _, data = self.get_json("mail:messages")
        by_subject = {row["subject"]: row for row in data["messages"]}
        self.assertEqual((by_subject["for you"]["label"], by_subject["for you"]["tone"]), ("system", "info"))
        self.assertEqual((by_subject["plain"]["label"], by_subject["plain"]["tone"]), ("", "dim"))

    def test_the_card_preview_has_no_markup_marks(self):
        make_message(body="## the door\n\n- **open** since `monday`\n> *quiet*")
        self.witness()
        _, data = self.get_json("mail:messages")
        self.assertEqual(data["messages"][0]["preview"], "the door open since monday quiet")

    def test_the_full_text_keeps_its_markup_for_the_reader(self):
        message = make_message(body="## the door\n\n- **open**")
        self.witness()
        _, data = self.get_json("mail:message", message.pk)
        self.assertEqual(data["body"], "## the door\n\n- **open**")

    def test_opening_a_message_marks_it_read_and_returns_everything(self):
        message = make_message(recipients="witness@aether-null\nivan@apollo.mail")
        Attachment.objects.create(message=message, label="first file", path="/apps/mail/", order=1)
        self.witness()
        _, data = self.get_json("mail:message", message.pk)
        self.assertEqual(data["from"], "██████@aether-core")
        self.assertEqual((data["to"], data["body"]), ("witness@aether-null, ivan@apollo.mail", message.body))
        self.assertEqual(data["attachments"], [{"id": 1, "kind": "link", "label": "first file", "open": "/apps/mail/"}])
        self.assertFalse(data["unread"])
        _, listing = self.get_json("mail:messages")
        self.assertFalse(listing["messages"][0]["unread"])

    def test_mark_unread_brings_the_dot_back(self):
        message = make_message()
        self.witness()
        self.get_json("mail:message", message.pk)
        self.client.post(reverse("mail:unread", args=[message.pk]))
        _, listing = self.get_json("mail:messages")
        self.assertTrue(listing["messages"][0]["unread"])

    def test_unread_needs_post(self):
        message = make_message()
        self.witness()
        self.assertEqual(self.client.get(reverse("mail:unread", args=[message.pk])).status_code, 405)

    def test_a_hidden_message_does_not_exist_for_the_player(self):
        for hidden in (
            make_message(recipients="ivan@aether-null"),    # чужой адресат
            make_message(key_condition="nope"),             # нет ключа
            make_message(sender="ivan@aether-null", recipients="", status="draft"),   # чужой черновик
        ):
            self.witness()
            self.assertEqual(self.client.get(reverse("mail:message", args=[hidden.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("mail:unread", args=[hidden.pk])).status_code, 404)
            self.assertEqual(MessageRead.objects.count(), 0)

    def test_a_player_with_the_key_sees_the_locked_message(self):
        user = get_user_model().objects.create_user("ivan", password="pw")
        message = make_message(key_condition="the_door")
        self.client.force_login(user)
        _, data = self.get_json("mail:messages")
        self.assertEqual(data["messages"], [])                    # ключа ещё нет
        UserKey.objects.create(user=user, key=Key.objects.create(slug="the_door"))
        _, data = self.get_json("mail:messages")
        self.assertEqual([row["id"] for row in data["messages"]], [message.pk])

    def test_the_body_is_data_not_markup(self):
        make_message(body="<script>alert(1)</script>")
        self.witness()
        _, listing = self.get_json("mail:messages")
        self.assertIn("<script>", listing["messages"][0]["preview"])      # как текст, браузер вставит через textContent
        self.assertEqual(self.client.get(reverse("mail:inbox")).content.decode().count("<script>alert"), 0)

    def test_two_witnesses_do_not_share_what_they_have_read(self):
        message = make_message()
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

    def test_compose_is_a_real_composer_not_the_old_stub(self):
        js = (Path(__file__).resolve().parent / "static/mail/mail.js").read_text(encoding="utf-8")
        self.assertNotIn("core unreachable", js)
        self.assertIn("nothing to send from this mailbox", js)


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("root", password="pw")
        cls.machine = Machine.objects.create(name="Null", hostname="aether-null")
        cls.message = make_message(key_condition="the_door", label="personal")

    def setUp(self):
        cache.clear()      # кэш пережил бы откат базы между тестами
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
            ("admin:mail_composetask_add", ()),
        ):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)

    @override_settings(FORCE_SCRIPT_NAME=None)
    def test_the_list_shows_the_key_condition_and_readers(self):
        mark_read(Viewer("x@y", frozenset(), session_key="abc"), self.message)
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
        make_message(sender="██████@aether-core")
        text = self.screen(self.scenes()["established"])
        self.assertIn("intercom: 1 unread message  (latest from ██████@aether-core, 3 min ago)", text)

    def test_the_number_follows_the_database(self):
        make_message()
        make_message(recipients="witness@aether-null")
        make_message(recipients="olga@apollo.mail")                  # чужой адрес: не считается
        make_message(key_condition="locked")                         # скрытое: не считается
        text = self.screen(self.scenes()["established"])
        self.assertIn("2 unread messages", text)

    def test_a_missing_witness_machine_does_not_break_the_screen(self):
        Machine.objects.filter(hostname="aether-null").delete()
        self.assertIn("no new messages", self.screen(self.scenes()["established"]))


class FolderTests(TestCase):
    """Ящик адреса: входящие, отправленные, черновики и корзина профиля."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = Machine.objects.create(name="Staff", hostname="apollo-staff")
        cls.will = MachineProfile.objects.create(machine=cls.staff, name="W", login="will_smith", freq=1, mail="will_smith@apollo.mail")
        cls.olga = MachineProfile.objects.create(machine=cls.staff, name="O", login="olga", freq=1, mail="olga@apollo.mail")

    def viewer(self, profile=None, keys=()):
        profile = profile or self.will
        return Viewer(address=profile.mail, keys=frozenset(keys), profile=profile, session_key="s1")

    def titles(self, viewer, folder=None):
        return [m.subject for m in visible_messages(viewer, folder)]

    def test_a_letter_to_the_address_is_in_its_inbox(self):
        make_message(subject="hello", recipients="will_smith@apollo.mail")
        self.assertEqual(self.titles(self.viewer(), "inbox"), ["hello"])
        self.assertEqual(self.titles(self.viewer(self.olga), "inbox"), [])

    def test_a_letter_from_the_address_is_in_its_sent_folder_not_in_the_inbox(self):
        make_message(subject="done", sender="will_smith@apollo.mail", recipients="olga@apollo.mail")
        self.assertEqual(self.titles(self.viewer(), "sent"), ["done"])
        self.assertEqual(self.titles(self.viewer(), "inbox"), [])
        self.assertEqual(self.titles(self.viewer(self.olga), "inbox"), ["done"])     # получателю то же письмо во входящих

    def test_a_letter_to_oneself_is_in_the_inbox_and_in_sent(self):
        make_message(subject="note", sender="will_smith@apollo.mail", recipients="will_smith@apollo.mail")
        self.assertEqual(self.titles(self.viewer(), "inbox"), ["note"])
        self.assertEqual(self.titles(self.viewer(), "sent"), ["note"])

    def test_a_draft_is_only_in_its_authors_drafts(self):
        make_message(subject="unsent", sender="will_smith@apollo.mail", recipients="olga@apollo.mail", status="draft")
        self.assertEqual(self.titles(self.viewer(), "drafts"), ["unsent"])
        self.assertEqual(self.titles(self.viewer(self.olga)), [])                  # адресат не видит неотправленное

    def test_a_broadcast_is_not_a_draft_of_anyone(self):
        make_message(subject="x", recipients="*", status="draft")
        self.assertEqual(self.titles(self.viewer()), [])

    def test_each_message_knows_its_folder(self):
        make_message(subject="a", recipients="will_smith@apollo.mail")
        make_message(subject="b", sender="will_smith@apollo.mail", recipients="x@y")
        make_message(subject="c", sender="will_smith@apollo.mail", recipients="", status="draft")
        folders = {m.subject: m.folder for m in visible_messages(self.viewer())}
        self.assertEqual(folders, {"a": "inbox", "b": "sent", "c": "drafts"})

    def test_the_address_match_ignores_case(self):
        make_message(subject="x", sender="Will_Smith@Apollo.Mail", recipients="", status="draft")
        self.assertEqual(self.titles(self.viewer(), "drafts"), ["x"])

    def test_keys_still_gate_a_draft(self):
        make_message(subject="x", sender="will_smith@apollo.mail", status="draft", key_condition="the_door")
        self.assertEqual(self.titles(self.viewer()), [])
        self.assertEqual(self.titles(self.viewer(keys=["the_door"])), ["x"])

    def test_the_summary_counts_only_the_inbox(self):
        make_message(sender="will_smith@apollo.mail", recipients="", status="draft")
        make_message(sender="will_smith@apollo.mail", recipients="olga@apollo.mail")
        inbox = make_message(recipients="will_smith@apollo.mail")
        self.assertEqual(summary(self.viewer())["unread"], 1)
        mark_read(self.viewer(), inbox)
        self.assertEqual(summary(self.viewer())["unread"], 0)

    # ---------- корзина ----------

    def test_a_trashed_letter_moves_to_the_profiles_trash(self):
        letter = make_message(subject="gone", recipients="will_smith@apollo.mail")
        Trashed.objects.create(message=letter, profile=self.will)
        self.assertEqual(self.titles(self.viewer(), "trash"), ["gone"])
        self.assertEqual(self.titles(self.viewer(), "inbox"), [])

    def test_the_trash_belongs_to_the_profile_not_to_the_address(self):
        twin = MachineProfile.objects.create(machine=self.staff, name="T", login="twin", freq=1, mail="will_smith@apollo.mail")
        letter = make_message(subject="gone", recipients="will_smith@apollo.mail")
        Trashed.objects.create(message=letter, profile=self.will)
        self.assertEqual(self.titles(self.viewer(twin), "inbox"), ["gone"])          # у двойника с тем же адресом оно во входящих
        self.assertEqual(self.titles(self.viewer(twin), "trash"), [])

    def test_a_trashed_letter_stays_hidden_from_those_it_was_never_for(self):
        letter = make_message(subject="gone", recipients="will_smith@apollo.mail")
        Trashed.objects.create(message=letter, profile=self.olga)                  # лежит в корзине, но письмо не её
        self.assertEqual(self.titles(self.viewer(self.olga)), [])

    def test_sent_and_draft_letters_can_be_trashed_too(self):
        sent = make_message(subject="s", sender="will_smith@apollo.mail", recipients="x@y")
        draft = make_message(subject="d", sender="will_smith@apollo.mail", recipients="", status="draft")
        Trashed.objects.create(message=sent, profile=self.will)
        Trashed.objects.create(message=draft, profile=self.will)
        self.assertEqual(sorted(self.titles(self.viewer(), "trash")), ["d", "s"])

    def test_a_witness_has_no_trash(self):
        letter = make_message(subject="gone", recipients="witness@aether-null")
        Trashed.objects.create(message=letter, profile=self.will)
        guest = Viewer(address="witness@aether-null", keys=frozenset(), session_key="s")
        self.assertEqual(self.titles(guest, "inbox"), ["gone"])
        self.assertEqual(self.titles(guest, "trash"), [])

    def test_the_summary_does_not_count_trashed_letters(self):
        letter = make_message(recipients="will_smith@apollo.mail")
        Trashed.objects.create(message=letter, profile=self.will)
        self.assertEqual(summary(self.viewer())["unread"], 0)

    def test_deleting_a_profile_empties_its_trash_rows(self):
        letter = make_message(recipients="will_smith@apollo.mail")
        Trashed.objects.create(message=letter, profile=self.will)
        self.will.delete()
        self.assertEqual(Trashed.objects.count(), 0)
        self.assertTrue(Message.objects.filter(pk=letter.pk).exists())

    def test_one_letter_lies_in_a_trash_once(self):
        from django.db import IntegrityError, transaction

        letter = make_message()
        Trashed.objects.create(message=letter, profile=self.will)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Trashed.objects.create(message=letter, profile=self.will)


class TriggerDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null = Machine.objects.create(name="Null", hostname="aether-null")
        cls.player = get_user_model().objects.create_user("ivan", password="pw")
        cls.other = get_user_model().objects.create_user("olga", password="pw")

    def viewer(self, user=None):
        return Viewer(address="ivan@aether-null", keys=frozenset(), user=user)

    def letter(self, **fields):
        return make_message(slug="door_open", recipients="ivan@aether-null", **fields)

    def test_a_trigger_letter_is_invisible_until_delivered(self):
        self.letter()
        self.assertEqual(visible_messages(self.viewer(self.player)), [])

    def test_delivery_makes_it_visible_to_that_player_only(self):
        from mail.delivery import deliver_by_slug

        self.letter()
        result = deliver_by_slug(self.player, "door_open")
        self.assertTrue(result.delivered and result.immediate)
        self.assertEqual(len(visible_messages(self.viewer(self.player))), 1)
        self.assertEqual(visible_messages(self.viewer(self.other)), [])

    def test_a_delayed_letter_appears_only_after_its_time(self):
        from datetime import timedelta

        from django.utils import timezone

        from mail.delivery import deliver_by_slug

        self.letter()
        now = timezone.now()
        result = deliver_by_slug(self.player, "door_open", delay=30, now=now)
        self.assertTrue(result.delivered and not result.immediate)
        self.assertEqual(visible_messages(self.viewer(self.player), now=now + timedelta(seconds=10)), [])
        self.assertEqual(len(visible_messages(self.viewer(self.player), now=now + timedelta(seconds=31))), 1)

    def test_delivering_twice_changes_nothing(self):
        from mail.delivery import deliver_by_slug

        self.letter()
        deliver_by_slug(self.player, "door_open", delay=60)
        deliver_by_slug(self.player, "door_open", delay=0)       # не ускоряет и не плодит записи
        self.assertEqual(Delivered.objects.count(), 1)
        self.assertEqual(visible_messages(self.viewer(self.player)), [])

    def test_a_witness_gets_no_trigger_letters(self):
        from mail.delivery import deliver_by_slug

        self.letter()
        from django.contrib.auth.models import AnonymousUser

        result = deliver_by_slug(AnonymousUser(), "door_open")
        self.assertFalse(result.delivered)
        self.assertEqual(Delivered.objects.count(), 0)
        self.assertEqual(visible_messages(self.viewer()), [])

    def test_an_unknown_letter_is_reported_not_raised(self):
        from mail.delivery import deliver_by_slug

        result = deliver_by_slug(self.player, "nope")
        self.assertFalse(result.delivered)
        self.assertIn("nope", result.reason)

    def test_the_delay_is_capped(self):
        from mail.delivery import MAX_DELAY_SECONDS, deliver

        message = self.letter()
        record, _ = deliver(self.player, message, delay=10**9)
        self.assertLessEqual((record.available_at - record.created_at).total_seconds(), MAX_DELAY_SECONDS + 1)

    def test_open_letters_do_not_need_delivery(self):
        make_message(recipients="ivan@aether-null")
        self.assertEqual(len(visible_messages(self.viewer(self.player))), 1)

    def test_slugs_are_unique_but_blank_slugs_may_repeat(self):
        from django.db import IntegrityError, transaction

        make_message()
        make_message()                      # без идентификатора: сколько угодно
        make_message(slug="one")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_message(slug="one")


class HookMailActionTests(TestCase):
    """Действие хука «mail»: язык, выполнение и доставка из снятого слоя."""

    LAYERED = "> encrypted hunter2 attempts=2\non remove: mail door_open delay=0"

    @classmethod
    def setUpTestData(cls):
        from machines.models import MachineProfile, Session
        from filesystem.models import MachineFile

        cls.machine = Machine.objects.create(name="Staff", hostname="apollo-staff")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        profile = MachineProfile.objects.create(machine=cls.machine, user=cls.user, name="Ivan", login="will_smith", freq=1)
        cls.session = Session.objects.create(user=cls.user, profile=profile)
        cls.file = MachineFile.objects.create(machine=cls.machine, path="/home/door.bin", state=cls.LAYERED)
        cls.letter = make_message(
            slug="door_open", recipients="will_smith@apollo-staff", subject="open"
        )

    def compile(self, text):
        from filesystem.states.compiler import StateError, compile_text

        try:
            return compile_text(text), []
        except StateError as error:
            return None, [str(p) for p in error.problems]

    # ---------- язык ----------

    def test_the_action_is_part_of_the_language(self):
        from filesystem.states.hooks import ACTIONS

        self.assertIn("mail", ACTIONS)

    def test_valid_forms_compile(self):
        for text in (
            "> encrypted x\non remove: mail door_open",
            "> encrypted x\non remove: mail door_open delay=30",
            "> encrypted x\non fail: mail broken-1_a delay=0",
        ):
            layers, problems = self.compile(text)
            self.assertEqual(problems, [], text)

    def test_wrong_forms_are_reported_with_a_reason(self):
        cases = {
            "> encrypted x\non remove: mail": "требует идентификатор",
            '> encrypted x\non remove: mail "door open"': "без кавычек",
            "> encrypted x\non remove: mail Door_Open": "не подходит",
            "> encrypted x\non remove: mail door_open delay=abc": "целым числом",
            "> encrypted x\non remove: mail door_open delay=-5": "от 0 до",
            "> encrypted x\non remove: mail door_open soon=1": "только delay",
        }
        for text, expected in cases.items():
            layers, problems = self.compile(text)
            self.assertTrue(any(expected in p for p in problems), (text, problems))

    # ---------- выполнение ----------

    def test_the_executor_collects_the_letter_and_its_delay(self):
        from filesystem.states.attempt import attempt_remove

        outcome = attempt_remove(
            "> encrypted hunter2\non remove: mail door_open delay=45", "", path="/a", name="a", given={"password": "hunter2"}
        )
        self.assertEqual([(m.slug, m.delay) for m in outcome.hooks.mails], [("door_open", 45)])

    def test_nothing_is_sent_when_the_layer_stays(self):
        from filesystem.states.attempt import attempt_remove

        outcome = attempt_remove(self.LAYERED, "", path="/a", name="a", given={"password": "wrong"})
        self.assertEqual(outcome.hooks.mails, [])

    # ---------- доставка ----------

    def test_removing_the_layer_delivers_the_letter_to_the_player(self):
        from filesystem.models import SessionFile
        from filesystem.unlock import unlock_file

        row = SessionFile.objects.create(session=self.session, file=self.file)
        result = unlock_file(row, {"password": "hunter2"})
        self.assertTrue(result.result.removed)
        self.assertEqual([(m.slug, m.delivered, m.immediate) for m in result.mail], [("door_open", True, True)])
        viewer = Viewer(address="will_smith@apollo-staff", keys=frozenset(), user=self.user)
        self.assertEqual([m.subject for m in visible_messages(viewer)], ["open"])

    def test_a_wrong_password_delivers_nothing(self):
        from filesystem.models import SessionFile
        from filesystem.unlock import unlock_file

        row = SessionFile.objects.create(session=self.session, file=self.file)
        result = unlock_file(row, {"password": "nope"})
        self.assertFalse(result.result.removed)
        self.assertEqual(result.mail, [])
        self.assertEqual(Delivered.objects.count(), 0)

    def test_an_unknown_letter_in_a_hook_does_not_break_the_unlock(self):
        from filesystem.models import MachineFile, SessionFile
        from filesystem.unlock import unlock_file

        broken = MachineFile.objects.create(
            machine=self.machine, path="/home/b.bin", state="> encrypted hunter2\non remove: mail missing_letter"
        )
        row = SessionFile.objects.create(session=self.session, file=broken)
        result = unlock_file(row, {"password": "hunter2"})
        self.assertTrue(result.result.removed)
        self.assertFalse(result.mail[0].delivered)

    def test_the_terminal_tells_the_player_a_letter_arrived(self):
        from terminal.engine.executor import TerminalExecutor

        result, _ = TerminalExecutor().execute(session=self.session, source="cph /home/door.bin hunter2")
        self.assertIn("decrypted", result.output)
        self.assertIn("intercom: 1 new message", result.output)

    def test_a_delayed_letter_is_not_announced_yet(self):
        from filesystem.models import MachineFile
        from terminal.engine.executor import TerminalExecutor

        MachineFile.objects.create(
            machine=self.machine, path="/home/slow.bin", state="> encrypted hunter2\non remove: mail door_open delay=60"
        )
        result, _ = TerminalExecutor().execute(session=self.session, source="cph /home/slow.bin hunter2")
        self.assertNotIn("intercom:", result.output)
        self.assertEqual(Delivered.objects.count(), 1)


@override_settings(FORCE_SCRIPT_NAME=None)
class AttachmentKindTests(TestCase):
    def setUp(self):
        cache.clear()      # кэш пережил бы откат базы между тестами
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    @classmethod
    def setUpTestData(cls):
        from assets.models import Asset
        from filesystem.models import MachineFile
        from machines.models import MachineProfile, Session

        cls.machine = Machine.objects.create(name="Staff", hostname="apollo-staff")
        cls.elsewhere = Machine.objects.create(name="Lab", hostname="apollo-lab")
        cls.asset = Asset.objects.create(name="photo", file_id="42")
        cls.file = MachineFile.objects.create(machine=cls.machine, path="/home/evidence.dat", delivered_only=True)
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        profile = MachineProfile.objects.create(machine=cls.machine, user=cls.user, name="I", login="will_smith", freq=1)
        cls.session = Session.objects.create(user=cls.user, profile=profile)
        cls.message = make_message(recipients="will_smith@apollo-staff")

    def attach(self, **fields):
        return Attachment.objects.create(message=self.message, label=fields.pop("label", "x"), **fields)

    # ---------- проверка вложения ----------

    def test_each_kind_needs_its_own_target(self):
        from django.core.exceptions import ValidationError

        for kind in (Attachment.Kind.LINK, Attachment.Kind.ASSET, Attachment.Kind.FILE):
            with self.assertRaises(ValidationError, msg=kind):
                Attachment(message=self.message, label="x", kind=kind).full_clean()
        Attachment(message=self.message, label="x", kind="asset", asset=self.asset).full_clean()
        Attachment(message=self.message, label="x", kind="file", machine_file=self.file).full_clean()

    # ---------- что видит окно почты ----------

    def test_an_asset_opens_in_the_viewer_and_downloads_as_a_file(self):
        from mail.attachments import payload

        data = payload(self.attach(kind="asset", asset=self.asset))
        self.assertEqual(data["open"], f"/view/{self.asset.public_id}/")
        self.assertEqual(data["download"], f"/view/{self.asset.public_id}/content/?download=1")

    def test_a_file_can_be_saved_to_the_machine_and_knows_if_it_already_was(self):
        from mail.attachments import payload

        item = self.attach(kind="file", machine_file=self.file)
        before = payload(item, self.session)
        self.assertEqual((before["path"], before["saved"]), ("/home/evidence.dat", False))
        self.assertTrue(before["save"].endswith(f"/api/attachments/{item.pk}/save/"))
        from mail.attachments import save_to_machine

        save_to_machine(self.session, item)
        self.assertTrue(payload(item, self.session)["saved"])

    def test_a_download_header_makes_the_browser_save_the_file(self):
        from types import SimpleNamespace

        from django.http import HttpResponse

        from assets.views import _apply_file_headers

        file = SimpleNamespace(filename="photo.png", etag="", last_modified="")
        plain = _apply_file_headers(HttpResponse(), file, "image/png")
        forced = _apply_file_headers(HttpResponse(), file, "image/png", as_attachment=True)
        self.assertTrue(plain["Content-Disposition"].startswith("inline"))
        self.assertTrue(forced["Content-Disposition"].startswith("attachment"))
        self.assertIn("photo.png", forced["Content-Disposition"])

    # ---------- сохранение в файловую систему ----------

    def test_saving_puts_the_file_into_the_players_session_only(self):
        from filesystem.models import SessionFile
        from mail.attachments import save_to_machine

        item = self.attach(kind="file", machine_file=self.file)
        self.assertEqual(save_to_machine(self.session, item), "/home/evidence.dat")
        row = SessionFile.objects.get(session=self.session)
        self.assertEqual((row.file, row.deleted_at), (self.file, None))

    def test_saving_twice_keeps_one_copy(self):
        from filesystem.models import SessionFile
        from mail.attachments import save_to_machine

        item = self.attach(kind="file", machine_file=self.file)
        save_to_machine(self.session, item)
        save_to_machine(self.session, item)
        self.assertEqual(SessionFile.objects.count(), 1)

    def test_a_deleted_file_comes_back_when_saved_again(self):
        from django.utils import timezone

        from filesystem.models import SessionFile
        from mail.attachments import save_to_machine

        item = self.attach(kind="file", machine_file=self.file)
        save_to_machine(self.session, item)
        SessionFile.objects.update(deleted_at=timezone.now())
        save_to_machine(self.session, item)
        self.assertIsNone(SessionFile.objects.get().deleted_at)

    def test_a_file_of_another_machine_is_refused(self):
        from filesystem.models import MachineFile
        from mail.attachments import SaveError, save_to_machine

        far = MachineFile.objects.create(machine=self.elsewhere, path="/home/far.dat")
        with self.assertRaises(SaveError) as caught:
            save_to_machine(self.session, self.attach(kind="file", machine_file=far))
        self.assertEqual(caught.exception.status, 409)

    def test_only_file_attachments_can_be_saved(self):
        from mail.attachments import SaveError, save_to_machine

        with self.assertRaises(SaveError):
            save_to_machine(self.session, self.attach(kind="asset", asset=self.asset))

    def test_a_delivered_only_file_is_not_on_the_machine_until_it_is_saved(self):
        from terminal.engine.executor import TerminalExecutor
        from mail.attachments import save_to_machine

        item = self.attach(kind="file", machine_file=self.file)
        listing = lambda: TerminalExecutor().execute(session=self.session, source="ls /home")[0].output
        self.assertNotIn("evidence.dat", listing())
        save_to_machine(self.session, item)
        self.assertIn("evidence.dat", listing())

    def test_an_ordinary_machine_file_is_listed_for_everyone(self):
        from filesystem.models import MachineFile
        from terminal.engine.executor import TerminalExecutor

        MachineFile.objects.create(machine=self.machine, path="/home/readme.txt")
        self.assertIn("readme.txt", TerminalExecutor().execute(session=self.session, source="ls /home")[0].output)


@override_settings(FORCE_SCRIPT_NAME=None)
class AttachmentSaveApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from filesystem.models import MachineFile
        from machines.models import MachineProfile, Session

        cls.machine = Machine.objects.create(name="Staff", hostname="apollo-staff")
        MachineApp.objects.create(machine=cls.machine, label="intercom", glyph="@", path="/apps/mail/")
        cls.file = MachineFile.objects.create(machine=cls.machine, path="/home/evidence.dat", delivered_only=True)
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.user, name="I", login="will_smith", freq=1)
        cls.message = make_message(recipients="will_smith@apollo-staff")
        cls.item = Attachment.objects.create(message=cls.message, label="evidence", kind="file", machine_file=cls.file)

    def setUp(self):
        cache.clear()      # кэш пережил бы откат базы между тестами
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def player(self):
        from machines.current import SESSION_KEY
        from machines.models import Session

        self.client.force_login(self.user)
        session = Session.objects.create(user=self.user, profile=self.profile)
        stored = self.client.session
        stored[SESSION_KEY] = session.pk
        stored.save()
        return session

    def save(self):
        response = self.client.post(reverse("mail:save", args=[self.item.pk]))
        return response, json.loads(response.content)

    def test_a_signed_in_player_saves_the_file(self):
        from filesystem.models import SessionFile

        session = self.player()
        response, data = self.save()
        self.assertEqual((response.status_code, data), (200, {"saved": True, "path": "/home/evidence.dat"}))
        self.assertTrue(SessionFile.objects.filter(session=session, file=self.file).exists())

    def test_the_window_shows_the_saved_state_afterwards(self):
        self.player()
        self.save()
        detail = json.loads(self.client.get(reverse("mail:message", args=[self.message.pk])).content)
        self.assertTrue(detail["attachments"][0]["saved"])

    def test_a_witness_gets_the_authorization_error_and_nothing_changes(self):
        from filesystem.models import SessionFile
        from users.aether_auth import AUTH_REQUIRED

        null = Machine.objects.create(name="Null", hostname="aether-null")
        MachineApp.objects.create(machine=null, label="intercom", glyph="@", path="/apps/mail/")
        session = self.client.session
        session["guest"] = True
        session.save()
        # письмо с вложением на машине witness
        letter = make_message(subject="for the witness")
        item = Attachment.objects.create(message=letter, label="f", kind="file", machine_file=self.file)
        response = self.client.post(reverse("mail:save", args=[item.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.content)["error"], AUTH_REQUIRED)
        self.assertEqual(SessionFile.objects.count(), 0)

    def test_a_hidden_letters_attachment_does_not_exist(self):
        Message.objects.filter(pk=self.message.pk).update(key_condition="nope")
        self.player()
        self.assertEqual(self.client.post(reverse("mail:save", args=[self.item.pk])).status_code, 404)

    def test_saving_needs_post(self):
        self.player()
        self.assertEqual(self.client.get(reverse("mail:save", args=[self.item.pk])).status_code, 405)

    def open(self, item=None):
        response = self.client.get(reverse("mail:open", args=[(item or self.item).pk]))
        return response, json.loads(response.content)

    def test_a_file_without_layers_opens_in_its_viewer(self):
        self.file.url = "apps/wiki/"
        self.file.save()
        self.player()
        response, data = self.open()
        self.assertEqual((response.status_code, data["url"], data["title"]), (200, "/apps/wiki/", "evidence.dat"))

    def test_a_locked_file_does_not_open(self):
        from filesystem.models import MachineFile

        locked = MachineFile.objects.create(
            machine=self.machine, path="/home/locked.dat", url="apps/wiki/", state="> encrypted hunter2"
        )
        item = Attachment.objects.create(message=self.message, label="locked", kind="file", machine_file=locked)
        self.player()
        response, data = self.open(item)
        self.assertEqual((response.status_code, data), (423, {"error": "content_locked"}))

    def test_a_file_without_content_says_so(self):
        self.player()
        response, data = self.open()
        self.assertEqual((response.status_code, data), (404, {"error": "no_content"}))

    def test_someone_elses_message_attachment_is_not_found(self):
        self.player()
        other = make_message(recipients="nobody@elsewhere")
        item = Attachment.objects.create(message=other, label="x", kind="file", machine_file=self.file)
        self.assertEqual(self.client.get(reverse("mail:open", args=[item.pk])).status_code, 404)

    def test_the_script_has_a_button_for_each_attachment_kind(self):
        js = (Path(__file__).resolve().parent / "static/mail/mail.js").read_text(encoding="utf-8")
        for word in ("downloadAttachment", "saveAttachment", "openFile", "save to machine", "item.download", "item.save", "item.open"):
            self.assertIn(word, js)


class ComposeLogicTests(TestCase):
    """Задача на набор: разбор текста, доступность, проверка и отправка."""

    @classmethod
    def setUpTestData(cls):
        from machines.models import MachineProfile, Session
        from mail.models import ComposeProgress, ComposeTask

        cls.machine = Machine.objects.create(name="Staff", hostname="apollo-staff")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.other = get_user_model().objects.create_user("olga", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.user, name="W", login="will_smith", freq=1)
        cls.stranger = MachineProfile.objects.create(machine=cls.machine, name="O", login="olga", freq=1)
        cls.reply = make_message(slug="reply_1", recipients="will_smith@apollo-staff", subject="re")
        cls.task = ComposeTask.objects.create(
            profile=cls.profile, recipients="olga@apollo-staff", subject="the file",
            target="hi olga,\nthe password is {{hunter22}}, thanks", max_attempts=3, reply_delay=30,
        )
        cls.task.replies.add(cls.reply)
        cls.right = "hi olga,\nthe password is hunter22, thanks"

    def viewer(self, user=None, profile=None, keys=()):
        profile = profile or self.profile
        return Viewer(address=profile.mail, keys=frozenset(keys), profile=profile, user=user or self.user)

    # ---------- текст ----------

    def test_the_target_is_split_into_visible_and_hidden_parts(self):
        from mail.compose import segments

        self.assertEqual(segments("a {{b}} c {{d}}"), [("text", "a "), ("hidden", "b"), ("text", " c "), ("hidden", "d")])
        self.assertEqual(segments("plain"), [("text", "plain")])
        self.assertEqual(segments("{{only}}"), [("hidden", "only")])

    def test_the_expected_text_has_the_secret_values_in_place(self):
        from mail.compose import expected_text

        self.assertEqual(expected_text(self.task), self.right)

    def test_the_browser_only_learns_how_long_a_secret_is(self):
        from mail.compose import public_segments

        shown = public_segments(self.task)
        self.assertEqual(shown, [{"text": "hi olga,\nthe password is "}, {"hidden": 8}, {"text": ", thanks"}])
        self.assertNotIn("hunter22", json.dumps(shown))

    def test_windows_line_breaks_do_not_matter(self):
        from mail.compose import normalize

        self.assertEqual(normalize("a\r\nb\rc"), "a\nb\nc")

    # ---------- доступность ----------

    def test_the_task_is_offered_under_its_profile_only(self):
        from mail.compose import available_tasks

        self.assertEqual(available_tasks(self.viewer()), [self.task])
        self.assertEqual(available_tasks(self.viewer(profile=self.stranger)), [])               # в чужом профиле задачи нет

    def test_keys_gate_the_task(self):
        from mail.compose import available_tasks

        self.task.key_condition = "the_door"
        self.task.save()
        self.assertEqual(available_tasks(self.viewer()), [])
        self.assertEqual(available_tasks(self.viewer(keys=["the_door"])), [self.task])

    def test_a_witness_has_no_tasks(self):
        from mail.compose import available_tasks

        self.assertEqual(available_tasks(Viewer(address="will_smith@apollo-staff", keys=frozenset(), session_key="s")), [])

    # ---------- отправка ----------

    def test_a_right_text_sends_the_letter_and_queues_the_replies(self):
        from datetime import timedelta

        from django.utils import timezone

        from mail.compose import send

        now = timezone.now()
        result = send(self.user, self.task, self.right, now=now)
        self.assertEqual((result.replies, result.delay), (1, 30))
        mine = visible_messages(self.viewer(), "sent", now=now)
        self.assertEqual([m.body for m in mine], [self.right])
        self.assertEqual((mine[0].recipients, mine[0].sender), ("olga@apollo-staff", "will_smith@apollo-staff"))
        self.assertEqual(visible_messages(self.viewer(), "inbox", now=now), [])                    # ответа ещё нет
        later = visible_messages(self.viewer(), "inbox", now=now + timedelta(seconds=31))
        self.assertEqual([m.subject for m in later], ["re"])

    def test_the_sent_copy_belongs_to_that_player_only(self):
        from mail.compose import send

        send(self.user, self.task, self.right)
        self.assertEqual(visible_messages(self.viewer(self.other), "sent"), [])

    def test_a_wrong_secret_costs_an_attempt_and_sends_nothing(self):
        from mail.compose import TaskError, send

        with self.assertRaises(TaskError) as caught:
            send(self.user, self.task, self.right.replace("hunter22", "hunter23"))
        self.assertEqual((caught.exception.status, caught.exception.extra), (422, {"attempts_left": 2}))
        self.assertEqual(visible_messages(self.viewer(), "sent"), [])
        self.assertEqual(Delivered.objects.count(), 0)

    def test_too_many_wrong_attempts_lock_the_task_even_for_the_right_text(self):
        from mail.compose import TaskError, send

        for _ in range(3):
            with self.assertRaises(TaskError):
                send(self.user, self.task, "nope")
        with self.assertRaises(TaskError) as caught:
            send(self.user, self.task, self.right)
        self.assertEqual(caught.exception.status, 423)

    def test_zero_attempts_means_unlimited(self):
        from mail.compose import TaskError, send

        self.task.max_attempts = 0
        self.task.save()
        for _ in range(10):
            with self.assertRaises(TaskError) as caught:
                send(self.user, self.task, "nope")
        self.assertIsNone(caught.exception.extra["attempts_left"])
        send(self.user, self.task, self.right)

    def test_the_letter_cannot_be_sent_twice(self):
        from mail.compose import TaskError, send

        send(self.user, self.task, self.right)
        with self.assertRaises(TaskError) as caught:
            send(self.user, self.task, self.right)
        self.assertEqual(caught.exception.status, 409)

    def test_a_sent_task_is_no_longer_offered(self):
        from mail.compose import available_tasks, send

        send(self.user, self.task, self.right)
        self.assertEqual(available_tasks(self.viewer()), [])
        self.assertEqual(available_tasks(self.viewer(self.other)), [self.task])        # у другого игрока своя

    def test_progress_is_per_player(self):
        from mail.compose import TaskError, send

        with self.assertRaises(TaskError):
            send(self.user, self.task, "nope")
        send(self.other, self.task, self.right)                                         # его счётчик чистый
        self.assertEqual(ComposeProgress.objects.get(user=self.user).attempts, 1)


@override_settings(FORCE_SCRIPT_NAME=None)
class ComposeApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from machines.models import MachineProfile
        from mail.models import ComposeTask

        cls.machine = Machine.objects.create(name="Staff", hostname="apollo-staff")
        MachineApp.objects.create(machine=cls.machine, label="intercom", glyph="@", path="/apps/mail/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.profile = MachineProfile.objects.create(machine=cls.machine, user=cls.user, name="I", login="will_smith", freq=1)
        cls.reply = make_message(slug="r1", recipients="will_smith@apollo-staff", subject="re")
        cls.task = ComposeTask.objects.create(
            profile=cls.profile, recipients="olga@apollo-staff", subject="s", target="hello {{abc}}", max_attempts=2
        )
        cls.task.replies.add(cls.reply)

    def setUp(self):
        cache.clear()      # кэш пережил бы откат базы между тестами
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)

    def player(self):
        from machines.current import SESSION_KEY
        from machines.models import Session

        self.client.force_login(self.user)
        stored = self.client.session
        stored[SESSION_KEY] = Session.objects.create(user=self.user, profile=self.profile).pk
        stored.save()

    def post(self, text):
        response = self.client.post(
            reverse("mail:send", args=[self.task.pk]), data=json.dumps({"text": text}), content_type="application/json"
        )
        ok = response["Content-Type"].startswith("application/json")
        return response, (json.loads(response.content) if ok else None)

    def test_the_list_gives_the_text_without_the_secret(self):
        self.player()
        response = self.client.get(reverse("mail:tasks"))
        data = json.loads(response.content)
        self.assertEqual(data["from"], "will_smith@apollo-staff")
        (task,) = data["tasks"]
        self.assertEqual((task["to"], task["subject"], task["attempts_left"]), ("olga@apollo-staff", "s", 2))
        self.assertEqual(task["segments"], [{"text": "hello "}, {"hidden": 3}])
        self.assertNotIn("abc", response.content.decode())

    def test_a_witness_gets_the_authorization_error_for_everything(self):
        from users.aether_auth import AUTH_REQUIRED

        session = self.client.session
        session["guest"] = True
        session.save()
        null = Machine.objects.create(name="Null", hostname="aether-null")
        MachineApp.objects.create(machine=null, label="intercom", glyph="@", path="/apps/mail/")
        for response in (self.client.get(reverse("mail:tasks")), self.client.post(reverse("mail:send", args=[self.task.pk]))):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(json.loads(response.content)["error"], AUTH_REQUIRED)

    def test_a_right_text_is_sent_and_the_copy_lands_in_sent(self):
        self.player()
        response, data = self.post("hello abc")
        self.assertEqual((response.status_code, data), (200, {"sent": True}))
        rows = json.loads(self.client.get(reverse("mail:messages")).content)["messages"]
        self.assertEqual([(r["folder"], r["subject"]) for r in rows if r["folder"] == "sent"], [("sent", "s")])

    def test_a_wrong_text_is_rejected_and_counts(self):
        self.player()
        response, data = self.post("hello abd")
        self.assertEqual((response.status_code, data["error"], data["attempts_left"]), (422, "message rejected", 1))

    def test_the_task_locks_after_the_limit(self):
        self.player()
        self.post("x")
        self.post("y")
        response, data = self.post("hello abc")
        self.assertEqual(response.status_code, 423)

    def test_a_second_send_is_refused_and_the_task_is_gone(self):
        self.player()
        self.post("hello abc")
        self.assertEqual(self.post("hello abc")[0].status_code, 404)           # задача уже недоступна
        self.assertEqual(json.loads(self.client.get(reverse("mail:tasks")).content)["tasks"], [])

    def test_a_bad_body_is_a_400(self):
        self.player()
        for body in (b"not json", b"{}", b'{"text": 5}'):
            response = self.client.post(reverse("mail:send", args=[self.task.pk]), data=body, content_type="application/json")
            self.assertEqual(response.status_code, 400, body)

    def test_a_task_of_another_mailbox_does_not_exist(self):
        from mail.models import ComposeTask

        self.player()
        someone = MachineProfile.objects.create(machine=self.machine, name="S", login="someone_else", freq=1)
        other = ComposeTask.objects.create(profile=someone, recipients="x@y", target="x")
        self.assertEqual(self.client.post(reverse("mail:send", args=[other.pk]), data="{}", content_type="application/json").status_code, 404)

    def test_the_script_has_the_typing_machinery(self):
        js = (Path(__file__).resolve().parent / "static/mail/mail.js").read_text(encoding="utf-8")
        for word in ("t-wrong", "t-ghost", "t-done", "typing-input", '"paste"', "paintTyping", "sendComposed", "attempts left"):
            self.assertIn(word, js)
        css = (Path(__file__).resolve().parent / "static/mail/mail.css").read_text(encoding="utf-8")
        for word in (".t-wrong", ".t-ghost", ".t-caret", "var(--status-error)"):
            self.assertIn(word, css)
