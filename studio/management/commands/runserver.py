"""runserver вместе со сборкой студии: пока работает сервер, Vite пересобирает фронт при каждой правке (npm run watch).

Сборка запускается один раз, в главном процессе: перезапуски Django при правке Python её не трогают. Без Node сервер
работает как раньше и говорит, чего не хватает. --no-studio отключает сборку.
"""
import atexit
import os
import shutil
import subprocess
import threading
from pathlib import Path

from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
LOCAL_NODE = Path.home() / ".local" / "node" / "bin"


def npm():
    found = shutil.which("npm")
    if found:
        return found
    local = LOCAL_NODE / "npm"
    return str(local) if local.exists() else None


class Command(RunserverCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--no-studio", action="store_true", help="Не собирать фронт студии вместе с сервером.")

    def handle(self, *args, **options):
        # с автоперезапуском Django handle идёт дважды: в главном процессе и в дочернем (RUN_MAIN); сборке нужен один
        if not options["no_studio"] and os.environ.get("RUN_MAIN") != "true":
            self.start_studio()
        return super().handle(*args, **options)

    def start_studio(self):
        command = npm()
        if command is None:
            self.stderr.write("studio: Node не найден, фронт студии не собирается (см. README, раздел про студию).")
            return
        env = {**os.environ, "PATH": f"{Path(command).parent}{os.pathsep}{os.environ.get('PATH', '')}"}
        if not (FRONTEND / "node_modules").exists():
            self.stdout.write("studio: ставлю зависимости фронта (npm ci)…")
            subprocess.run([command, "ci"], cwd=FRONTEND, env=env, check=False)
        process = subprocess.Popen(
            [command, "run", "watch"], cwd=FRONTEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        atexit.register(stop, process)
        threading.Thread(target=relay, args=(process, self.stdout), daemon=True).start()


QUIET = ("> ", "transforming", "rendering chunks", "computing gzip", "../static/", "vite v", "build started")


def relay(process, out):
    """Вывод Vite в консоль сервера: готово, пересобрано, ошибки. Список файлов сборки не нужен."""
    for line in process.stdout:
        line = line.rstrip()
        if line and not line.lstrip().startswith(QUIET):
            out.write(f"studio: {line}")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
