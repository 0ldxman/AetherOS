"""Снимает картинки и видео для справки (docs/guide/media) на демо-мире.

Поднимает отдельный сервер на временной базе (migrate, seed_demo), входит автором и игроком и гоняет сценарии
docs/guide/shots через playwright. Нужны node и playwright: PLAYWRIGHT_MODULE (путь к модулю, по умолчанию «playwright»)
и CHROMIUM_PATH, если браузер не в стандартном месте. Для видео playwright нужен его ffmpeg (npx playwright install ffmpeg).

  manage.py docs_media                 все сценарии
  manage.py docs_media mail-graph      только названные
  manage.py docs_media --missing       только те, чьих файлов ещё нет
  manage.py docs_media --list          что есть и снято ли
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from guide import media, pages


class Command(BaseCommand):
    help = "Снимает картинки и видео справки на демо-мире."

    def add_arguments(self, parser):
        parser.add_argument("names", nargs="*", help="имена сценариев (по умолчанию все)")
        parser.add_argument("--list", action="store_true", help="показать сценарии и есть ли их файлы")
        parser.add_argument("--missing", action="store_true", help="только те, чьих файлов нет")
        parser.add_argument("--out", default="", help="куда класть файлы (по умолчанию docs/guide/media)")
        parser.add_argument("--node", default="", help="путь к node")
        parser.add_argument("--prepare-world", action="store_true", help="служебное: создать автора и игрока, вывести вход")

    def handle(self, *args, **options):
        if options["prepare_world"]:
            self.stdout.write(json.dumps(media.prepare_world()))
            return
        out = Path(options["out"]) if options["out"] else pages.MEDIA
        if options["list"]:
            for shot in media.shots():
                self.stdout.write(f"{'есть' if (out / shot.file).is_file() else 'нет '}  {shot.file}")
            for slug, file in pages.missing_media():
                if file not in {s.file for s in media.shots()}:
                    self.stdout.write(f"без сценария  {file}  (страница {slug})")
            return
        try:
            chosen = media.select(options["names"], options["missing"], out)
        except ValueError as error:
            raise CommandError(str(error))
        if not chosen:
            self.stdout.write("Снимать нечего.")
            return
        node = options["node"] or shutil.which("node")
        if not node:
            raise CommandError("Не найден node: укажите путь в --node.")
        out.mkdir(parents=True, exist_ok=True)
        self.shoot(chosen, out, node)

    def shoot(self, chosen, out, node):
        base_dir = Path(settings.BASE_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp}/docs.sqlite3", REDIS_URL="", FORCE_SCRIPT_NAME="")
            manage = [sys.executable, str(base_dir / "manage.py")]
            for step in (["migrate", "--noinput"], ["seed_demo"]):
                subprocess.run(manage + step, env=env, cwd=base_dir, check=True, capture_output=True)
            world = json.loads(subprocess.run(manage + ["docs_media", "--prepare-world"], env=env, cwd=base_dir, check=True, capture_output=True, text=True).stdout.strip().splitlines()[-1])
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            server = subprocess.Popen(manage + ["runserver", f"127.0.0.1:{port}", "--noreload", "--no-studio"], env=env, cwd=base_dir,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                self.wait(base, server)
                runner_env = dict(os.environ, GUIDE_BASE=base, GUIDE_OUT=str(out), GUIDE_SHOTS=str(media.SHOTS),
                                  GUIDE_ONLY=",".join(s.name for s in chosen), GUIDE_WORLD=json.dumps(world))
                done = subprocess.run([node, str(media.SHOTS / "run.js")], env=runner_env, cwd=base_dir)
                if done.returncode:
                    raise CommandError("Не все снимки получились.")
            finally:
                server.terminate()
                server.wait(timeout=10)

    def wait(self, base, server):
        for _ in range(60):
            if server.poll() is not None:
                raise CommandError("Сервер для съёмки не запустился.")
            try:
                urllib.request.urlopen(f"{base}/studio/", timeout=2)
                return
            except Exception:
                time.sleep(0.5)
        raise CommandError("Сервер для съёмки не ответил за 30 секунд.")
