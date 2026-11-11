"""Общий рабочий стол: приложения из места desktop_shared есть у каждой записи вместе с личными, личный файл главнее."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem import appfile
from filesystem.testing import make_file, remove_apps
from machines.models import Machine, Place


@override_settings(FORCE_SCRIPT_NAME=None)
class SharedDesktopTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main")
        remove_apps()
        Place.objects.filter(name="desktop").delete()
        self.app("/etc/skel/Desktop/console.app", "console", "/apps/terminal/")
        self.app("/etc/skel/Desktop/mail.app", "intercom", "/apps/mail/")

    def app(self, path, label, url):
        make_file(self.main, path, body=appfile.render(label, "terminal", url, "", 0, ()), format="app")

    def page(self, login):
        """Подписи значков на столе записи."""
        import re

        user = get_user_model().objects.get_or_create(username=login)[0]
        self.client.force_login(user)
        return re.findall(r'class="icon-label">([^<]*)<', self.client.get(reverse("desktop")).content.decode())

    def test_every_account_gets_the_shared_apps_without_copies(self):
        from filesystem.models import Placement

        before = Placement.objects.count()
        for login in ("ivan", "olga"):
            self.assertEqual(sorted(self.page(login)), ["console", "intercom"])
        self.assertEqual(Placement.objects.count(), before)            # новым записям ничего не копируется

    def test_personal_files_are_added_and_win_by_name(self):
        self.app("/home/ivan/Desktop/notes.app", "notes", "/apps/wiki/")
        self.app("/home/ivan/Desktop/mail.app", "my-mail", "/apps/mail/")
        self.assertEqual(sorted(self.page("ivan")), ["console", "my-mail", "notes"])     # личный mail.app закрыл общий
        self.assertEqual(sorted(self.page("olga")), ["console", "intercom"])

    def test_the_shared_place_can_be_moved_or_be_the_desktop_itself(self):
        from machines.world import places

        self.assertEqual(places.resolve(self.main, "desktop_shared", "ivan"), "/etc/skel/Desktop")
        Place.objects.create(machine=self.main, name="desktop", path="/etc/skel/Desktop")       # общий стол без личного (как раньше)
        self.assertEqual(sorted(self.page("ivan")), ["console", "intercom"])                # одно место не читается дважды
