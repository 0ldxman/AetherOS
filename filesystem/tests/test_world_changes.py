"""Изменения мира для автора: список (кто, что), откат, «игрок не может удалить»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from filesystem import rights
from filesystem.machine_view import MachineView
from filesystem.manager import world
from filesystem.models import Placement
from filesystem.testing import make_file
from machines.access.groups import principal_for
from machines.models import Machine, MachineProfile


class WorldChangesTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(name="Core", hostname="core")
        self.ivan = get_user_model().objects.create_user("ivan")
        make_file(self.machine, "/srv/evidence.txt", body="улика")
        make_file(self.machine, "/srv/note.txt", body="записка")
        self.guest = MachineProfile.objects.create(machine=self.machine, login="guest", name="guest", freq=1)

    def view(self):
        return MachineView(self.machine, self.ivan, principal_for(self.guest))

    def test_the_author_sees_who_changed_what_and_reverts_it(self):
        view = self.view()
        view.edit_text("/srv/note.txt", "переписал")
        view.put_text("/srv/mine.txt", "моё")
        view.remove("/srv/evidence.txt")
        kinds = {row["path"]: (row["kind"], row["by"]) for row in world.changes(self.machine)}
        self.assertEqual(kinds, {"/srv/note.txt": ("edited", "ivan"), "/srv/mine.txt": ("added", "ivan"), "/srv/evidence.txt": ("deleted", "ivan")})
        self.assertEqual(world.revert(self.machine, "/srv/evidence.txt"), 1)
        self.assertTrue(MachineView(self.machine, self.ivan).exists("/srv/evidence.txt"))                # снова как в базе
        self.assertEqual(world.revert(self.machine), 2)
        self.assertEqual(MachineView(self.machine, self.ivan).get("/srv/note.txt").body, "записка")
        self.assertEqual(world.changes(self.machine), [])

    def test_a_kept_file_cannot_be_deleted_or_moved_by_a_player(self):
        self.assertTrue(world.set_keep(self.machine, "/srv/evidence.txt", True))
        with self.assertRaises(rights.NotPermitted):
            self.view().remove("/srv/evidence.txt")
        with self.assertRaises(rights.NotPermitted):
            self.view().move("/srv/evidence.txt", "/srv/gone.txt")
        MachineView(self.machine, self.ivan).remove("/srv/evidence.txt")                                 # сценарию (без прав) можно
        self.assertFalse(world.set_keep(self.machine, "/srv/none.txt", True))
