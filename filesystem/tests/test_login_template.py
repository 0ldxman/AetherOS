"""Шаблонные папки {login} в томе: у каждой учётки на их месте свой логин, правки игрока только у него."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem.machine_view import MachineView, view_for
from filesystem.testing import make_file
from machines.models import Machine, MachineProfile, Session


class LoginTemplateTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(name="Main", hostname="main")
        make_file(self.machine, "/home/{login}/Desktop/console.app", body="console")
        make_file(self.machine, "/home/{login}/Desktop/readme.txt", body="hello")
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")
        for user in (self.ivan, self.olga):
            profile = MachineProfile.objects.create(machine=self.machine, user=user, name=user.username, login=user.username, freq=0)
            Session.objects.create(user=user, profile=profile)

    def view(self, user):
        return MachineView(self.machine, user)

    def names(self, user, path):
        return [entry.name for entry in self.view(user).children(path)]

    def test_every_account_sees_the_template_at_its_own_login(self):
        self.assertEqual(self.names(self.ivan, "/home/ivan/Desktop"), ["console.app", "readme.txt"])
        self.assertEqual(self.names(self.olga, "/home/olga/Desktop"), ["console.app", "readme.txt"])
        self.assertEqual(self.names(self.ivan, "/home"), ["ivan"])                     # сам шаблон игроку не виден
        self.assertEqual(self.names(None, "/home"), ["{login}"])                       # автору виден как есть
        self.assertEqual(self.names(self.ivan, "/home/olga/Desktop"), [])               # чужой дом из шаблона не появляется
        guest = MachineView(self.machine, None, login="witness")
        self.assertEqual([e.name for e in guest.children("/home/witness/Desktop")], ["console.app", "readme.txt"])

    def test_edits_and_removals_stay_with_one_player(self):
        self.view(self.ivan).edit_text("/home/ivan/Desktop/readme.txt", "mine")
        self.view(self.ivan).remove("/home/ivan/Desktop/console.app")
        self.assertEqual(self.view(self.ivan).entries["/home/ivan/Desktop/readme.txt"].player.content, "mine")
        self.assertIsNone(self.view(self.olga).entries["/home/olga/Desktop/readme.txt"].player)
        self.assertEqual(self.names(self.ivan, "/home/ivan/Desktop"), ["readme.txt"])
        self.assertEqual(self.names(self.olga, "/home/olga/Desktop"), ["console.app", "readme.txt"])
        self.assertEqual(self.names(None, "/home/{login}/Desktop"), ["console.app", "readme.txt"])     # шаблон не изменился

    def test_a_real_folder_wins_over_the_template(self):
        make_file(self.machine, "/home/ivan/Desktop/readme.txt", body="real")
        make_file(self.machine, "/home/ivan/Desktop/own.txt", body="own")
        view = self.view(self.ivan)
        self.assertEqual(sorted(e.name for e in view.children("/home/ivan/Desktop")), ["console.app", "own.txt", "readme.txt"])
        found = view.entries["/home/ivan/Desktop/readme.txt"]
        self.assertEqual(found.item.body if found.item else found.text, "real")
        self.assertEqual(self.names(self.olga, "/home/olga/Desktop"), ["console.app", "readme.txt"])

    def test_view_for_takes_the_login_of_the_session(self):
        self.assertEqual(view_for(self.machine, self.ivan).login, "ivan")
        self.assertEqual(view_for(self.machine, self.ivan, login="other").login, "other")
