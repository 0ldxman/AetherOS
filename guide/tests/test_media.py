"""Съёмка справки: список сценариев, выбор, демо-мир автора и игрока, служебный режим команды.

Запуск: python manage.py test guide
"""
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import Client, TestCase

from guide import media, pages


class SelectTests(TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        (root / "shots").mkdir()
        (root / "media").mkdir()
        for name in ("a.shot.js", "b.clip.js", "run.js", "notes.txt", "c.other.js"):
            (root / "shots" / name).write_text("")
        for patch in (mock.patch.object(media, "SHOTS", root / "shots"), mock.patch.object(pages, "MEDIA", root / "media")):
            patch.start()
            self.addCleanup(patch.stop)
        self.root = root

    def test_shots_by_file_name(self):
        self.assertEqual(media.shots(), [media.Shot("a", "shot"), media.Shot("b", "clip")])
        self.assertEqual([s.file for s in media.shots()], ["a.png", "b.webm"])

    def test_select_names_and_missing(self):
        self.assertEqual([s.name for s in media.select()], ["a", "b"])
        self.assertEqual([s.name for s in media.select(["b"])], ["b"])
        (self.root / "media" / "a.png").write_bytes(b"x")
        self.assertEqual([s.name for s in media.select(only_missing=True, media_dir=self.root / "media")], ["b"])
        with self.assertRaisesMessage(ValueError, "nope"):
            media.select(["nope"])

    def test_command_list_and_unknown_name(self):
        (self.root / "media" / "a.png").write_bytes(b"x")
        out = StringIO()
        call_command("docs_media", "--list", "--out", str(self.root / "media"), stdout=out)
        self.assertIn("есть  a.png", out.getvalue())
        self.assertIn("нет   b.webm", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("docs_media", "nope", stdout=StringIO())


class WorldTests(TestCase):
    def test_author_and_player_can_sign_in(self):
        call_command("seed_demo", stdout=StringIO())
        out = StringIO()
        call_command("docs_media", "--prepare-world", stdout=out)
        world = json.loads(out.getvalue())
        author = Client()
        self.assertTrue(author.login(username=world["author"]["username"], password=world["author"]["password"]))
        self.assertEqual(author.get("/studio/api/me").status_code, 200)
        player = Client()
        player.cookies["sessionid"] = world["player_cookie"]
        self.assertEqual(player.get("/desktop/").status_code, 200)
        self.assertTrue(get_user_model().objects.filter(username=media.PLAYER).exists())


class RepoTests(TestCase):
    def test_every_media_token_of_the_real_pages_has_a_script_and_a_file(self):
        """Страница не должна ждать снимок, который никто не снимает или который ещё не лежит в репозитории."""
        scripted = {s.file for s in media.shots()}
        wanted = {file for _, file in pages.missing_media()}
        self.assertEqual(wanted, set(), "нет файлов в docs/guide/media: запустите manage.py docs_media --missing")
        for page in pages.pages():
            for kind, name in pages.media_names(page.source):
                file = f"{name}.{pages.KINDS[kind][0]}"
                self.assertIn(file, scripted, f"{page.slug}: для {file} нет сценария съёмки в docs/guide/shots")
