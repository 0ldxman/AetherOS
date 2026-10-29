"""Политика входа: источники, маршрут, окна времени, блокировка после ошибок, режим пароля и ключа, журнал.

Запуск: python manage.py test machines.tests.test_entry
"""
import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix
from django.utils import timezone
from unittest import mock

from filesystem.testing import give_key_to_session, key_item, make_app
from machines import entry, windows
from machines.models import EntryPolicy, LoginEvent, Machine, MachineProfile, Session, SystemType
from terminal.testing import TerminalClient


class WindowTests(TestCase):
    def moment(self, day, hour, minute=0):
        return datetime(2026, 11, day, hour, minute)          # 2 ноября 2026 понедельник

    def test_days_and_several_intervals_with_a_break(self):
        rules = windows.parse("mon-fri: 9:00-13:00 14:00-17:00")
        self.assertTrue(windows.allows(rules, self.moment(2, 9)))
        self.assertFalse(windows.allows(rules, self.moment(2, 13, 30)))
        self.assertTrue(windows.allows(rules, self.moment(2, 16, 59)))
        self.assertFalse(windows.allows(rules, self.moment(7, 10)))          # суббота

    def test_a_line_is_added_to_the_others_and_except_closes_a_day(self):
        rules = windows.parse("mon-fri: 9:00-17:00\nsat: 10:00-12:00\nexcept wed: *")
        self.assertTrue(windows.allows(rules, self.moment(7, 11)))
        self.assertFalse(windows.allows(rules, self.moment(4, 10)))           # среда закрыта
        self.assertTrue(windows.allows(rules, self.moment(3, 10)))

    def test_an_interval_through_midnight_belongs_to_the_day_it_started(self):
        rules = windows.parse("sat: 22:00-6:00")
        self.assertTrue(windows.allows(rules, self.moment(7, 23)))
        self.assertTrue(windows.allows(rules, self.moment(8, 3)))
        self.assertFalse(windows.allows(rules, self.moment(8, 7)))

    def test_no_windows_and_only_except_lines(self):
        self.assertTrue(windows.allows(windows.parse(""), self.moment(2, 3)))
        rules = windows.parse("except sun: *")
        self.assertTrue(windows.allows(rules, self.moment(2, 3)))
        self.assertFalse(windows.allows(rules, self.moment(8, 3)))

    def test_bad_lines_are_reported_with_their_number(self):
        for text in ("mon-fri 9:00-17:00", "funday: 9:00-17:00", "mon: 9-17", "mon: 25:00-26:00"):
            with self.assertRaises(windows.WindowError, msg=text):
                windows.parse(text)
        with self.assertRaises(ValidationError):
            EntryPolicy(name="x", windows="mon: nine").full_clean()


@override_settings(FORCE_SCRIPT_NAME=None)
class EntryTests(TerminalClient, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Machine.objects.create(name="Main", hostname="aether-main")
        cls.gate = Machine.objects.create(name="Gate", hostname="gw-02")
        cls.core = Machine.objects.create(name="Core", hostname="aether-core")
        make_app(cls.main, label="console", glyph=">_", path="/apps/terminal/")
        cls.user = get_user_model().objects.create_user("ivan", password="pw")
        cls.home = MachineProfile.objects.create(machine=cls.main, user=cls.user, name="Ivan", login="ivan", freq=1)
        cls.gate_account = MachineProfile.objects.create(machine=cls.gate, login="relay", name="relay", freq=1)
        key_item("cardkey")

    def account(self, login, freq=14.0, **extra):
        return MachineProfile.objects.create(machine=self.core, login=login, name=login, freq=freq, **extra)

    def policy(self, **fields):
        return EntryPolicy.objects.create(name=f"p{EntryPolicy.objects.count()}", **fields)

    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        cache.clear()
        self.client.force_login(self.user)

    def kinds(self, profile):
        return list(LoginEvent.objects.filter(profile=profile).values_list("kind", flat=True))

    # ---- кто назначен ---------------------------------------------------------------------------------------------

    def test_the_most_specific_policy_wins_and_without_one_nothing_is_limited(self):
        profile = self.account("a")
        self.assertIsNone(entry.policy_of(profile))
        system_policy, machine_policy, own_policy = self.policy(), self.policy(), self.policy()
        SystemType.objects.update_or_create(code=self.core.system, defaults={"name": "Aether", "entry_policy": system_policy})
        self.assertEqual(entry.policy_of(profile), system_policy)
        Machine.objects.filter(pk=self.core.pk).update(entry_policy=machine_policy)
        profile.machine.refresh_from_db()
        self.assertEqual(entry.policy_of(profile), machine_policy)
        profile.entry_policy = own_policy
        self.assertEqual(entry.policy_of(profile), own_policy)

    def test_the_profile_fields_override_the_policy(self):
        profile = self.account("a", entry_policy=self.policy(ttl=60, lock_seconds=30, kick_text="from policy"))
        self.assertEqual((entry.ttl_of(profile), entry.lock_seconds_of(profile), entry.kick_text_of(profile)), (60, 30, "from policy"))
        profile.ttl, profile.cooldown, profile.kick_message = 5, 7, "own"
        self.assertEqual((entry.ttl_of(profile), entry.lock_seconds_of(profile), entry.kick_text_of(profile)), (5, 7, "own"))

    # ---- откуда, через что, когда ---------------------------------------------------------------------------------

    def test_sources_accept_a_pattern_and_refuse_other_hosts(self):
        self.account("walled", entry_policy=self.policy(sources="gw-*\nelsewhere"))
        self.assertIn("Permission denied", self.run_command("rshell walled@aether-core")["output"])
        self.assertEqual(self.kinds(MachineProfile.objects.get(login="walled")), ["source"])
        self.account("open", entry_policy=self.policy(sources="aether-*"))
        self.assertEqual(self.run_command("rshell open@aether-core")["exit_code"], 0)

    def test_via_demands_a_host_in_the_chain_of_bridges(self):
        self.account("inner", entry_policy=self.policy(via="gw-02"))
        self.assertIn("Permission denied", self.run_command("rshell inner@aether-core")["output"])
        self.assertEqual(self.run_command("rshell relay@gw-02")["exit_code"], 0)
        self.assertEqual(self.run_command("rshell inner@aether-core")["exit_code"], 0)
        self.assertEqual(self.kinds(MachineProfile.objects.get(login="inner")), ["route", "ok"])

    def test_outside_the_window_the_account_refuses_with_its_own_text(self):
        self.account("shift", entry_policy=self.policy(windows="mon-fri: 9:00-17:00", window_text="The office is closed."))
        night = timezone.make_aware(datetime(2026, 11, 2, 23, 0))
        with mock.patch("machines.entry.timezone.localtime", return_value=night):
            self.assertIn("The office is closed.", self.run_command("rshell shift@aether-core")["output"])
        day = timezone.make_aware(datetime(2026, 11, 2, 10, 0))
        with mock.patch("machines.entry.timezone.localtime", return_value=day):
            self.assertEqual(self.run_command("rshell shift@aether-core")["exit_code"], 0)
        self.assertEqual(self.kinds(MachineProfile.objects.get(login="shift")), ["window", "ok"])

    # ---- ошибки и блокировка --------------------------------------------------------------------------------------

    def test_wrong_passwords_lock_the_account_and_the_lock_passes(self):
        profile = self.account("vault", password_hash=make_password("right"), entry_policy=self.policy(max_attempts=2, lock_seconds=60))
        for _ in range(2):
            self.run_command("rshell vault@aether-core")
            last = self.answer("wrong")
        self.assertIn("account locked", last["output"])
        self.assertEqual(self.kinds(profile), ["bad_password", "bad_password", "locked"])
        locked = self.run_command("rshell vault@aether-core")
        self.assertIn("account locked", locked["output"])
        self.assertIn("retry in 01:0", locked["output"])
        LoginEvent.objects.filter(kind="locked").update(at=timezone.now() - timedelta(seconds=120))      # блокировка истекла
        self.run_command("rshell vault@aether-core")
        self.assertEqual(self.answer("right")["exit_code"], 0)
        self.assertEqual(self.kinds(profile)[-1], "ok")

    def test_the_count_starts_over_after_a_good_entry_and_the_lock_is_for_this_player_only(self):
        profile = self.account("vault", password_hash=make_password("right"), entry_policy=self.policy(max_attempts=2, lock_seconds=600))
        self.run_command("rshell vault@aether-core")
        self.answer("wrong")
        self.run_command("rshell vault@aether-core")
        self.assertEqual(self.answer("right")["exit_code"], 0)               # ошибка сброшена входом
        self.run_command("exit")
        for _ in range(2):
            self.run_command("rshell vault@aether-core")
            self.answer("wrong")
        other = get_user_model().objects.create_user("petr", password="pw")
        self.assertEqual(entry.locked_seconds(other, profile), 0)
        self.assertGreater(entry.locked_seconds(self.user, profile), 0)

    def test_without_a_limit_the_errors_never_lock(self):
        self.account("vault", password_hash=make_password("right"), entry_policy=self.policy())
        for _ in range(4):
            self.run_command("rshell vault@aether-core")
            self.assertIn("Permission denied", self.answer("wrong")["output"])

    # ---- пароль и ключ --------------------------------------------------------------------------------------------

    def test_any_mode_lets_a_key_in_without_the_password_and_all_mode_asks_for_both(self):
        both = self.account("both", password_hash=make_password("right"), key_condition="cardkey", entry_policy=self.policy(mode="any"))
        give_key_to_session(Session.objects.create(user=self.user, profile=self.home), "cardkey")
        self.assertEqual(self.run_command("rshell both@aether-core")["exit_code"], 0)         # ключ есть, пароль не спросили
        self.run_command("exit")
        EntryPolicy.objects.filter(pk=both.entry_policy_id).update(mode="all")
        self.assertEqual(self.run_command("rshell both@aether-core").get("prompt", {}).get("kind"), "password")

    def test_any_mode_asks_for_the_password_when_there_is_no_key(self):
        self.account("both", password_hash=make_password("right"), key_condition="cardkey", entry_policy=self.policy(mode="any"))
        self.assertEqual(self.run_command("rshell both@aether-core").get("prompt", {}).get("kind"), "password")
        self.assertEqual(self.answer("right")["exit_code"], 0)

    def test_a_token_goes_past_the_password_but_not_past_the_sources(self):
        from machines.models import MachineProfileToken

        profile = self.account("tok", password_hash=make_password("right"), entry_policy=self.policy(sources="elsewhere"))
        MachineProfileToken.objects.create(profile=profile, token="golden")
        self.assertIn("Permission denied", self.run_command("rshell --token golden tok@aether-core")["output"])
        EntryPolicy.objects.filter(pk=profile.entry_policy_id).update(sources="")
        self.assertEqual(self.run_command("rshell --token golden tok@aether-core")["exit_code"], 0)


@override_settings(FORCE_SCRIPT_NAME=None)
class JournalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from filesystem.testing import make_file

        cls.core = Machine.objects.create(name="Core", hostname="aether-core")
        cls.other_machine = Machine.objects.create(name="Other", hostname="other")
        cls.ivan = get_user_model().objects.create_user("ivan", password="pw")
        cls.petr = get_user_model().objects.create_user("petr", password="pw")
        cls.account = MachineProfile.objects.create(machine=cls.core, login="vault", name="v", freq=1)
        cls.elsewhere = MachineProfile.objects.create(machine=cls.other_machine, login="vault", name="v", freq=1)
        for user, kind, source in ((cls.ivan, "bad_password", "aether-main"), (cls.ivan, "ok", "aether-main"), (cls.petr, "window", "gw-02")):
            entry.record(cls.account, user, kind, source)
        entry.record(cls.elsewhere, cls.ivan, "ok", "aether-main")
        cls.made = make_file(cls.core, "/var/log/auth.log", format="log")

    def text(self, user):
        from filesystem.machine_view import MachineView
        from filesystem.content.rawview import build_raw

        view = MachineView(self.core, user)
        return build_raw(view.get(self.made.path), view).data.decode()

    def test_the_journal_lists_the_entries_on_this_host_for_this_player_only(self):
        mine = self.text(self.ivan)
        self.assertIn("Failed password for vault from aether-main", mine)
        self.assertIn("Accepted password for vault from aether-main", mine)
        self.assertNotIn("outside permitted hours", mine)
        self.assertEqual(len(mine.splitlines()), 2)                                  # события другой машины сюда не попадают
        self.assertIn("Refused vault from gw-02: outside permitted hours", self.text(self.petr))

    def test_a_new_event_changes_the_file(self):
        before = self.text(self.ivan)
        entry.record(self.account, self.ivan, "locked", "aether-main")
        self.assertIn("Account vault locked", self.text(self.ivan))
        self.assertNotEqual(before, self.text(self.ivan))
