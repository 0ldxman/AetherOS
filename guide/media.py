"""Снимки и видео для справки: какие сценарии есть, и демо-мир с автором и игроком, под которыми их снимают.

Сценарий съёмки это файл docs/guide/shots/<имя>.shot.js (картинка png) или <имя>.clip.js (видео webm). Запускает их
команда docs_media через docs/guide/shots/run.js (playwright). Здесь только то, что можно проверить без браузера.
"""
from dataclasses import dataclass

from guide import pages

SHOTS = pages.ROOT / "shots"
AUTHOR = ("docs-author", "docs-pass")
PLAYER = "docs-player"


@dataclass(frozen=True)
class Shot:
    name: str
    kind: str                      # shot | clip

    @property
    def file(self):
        return f"{self.name}.{'png' if self.kind == 'shot' else 'webm'}"


def shots():
    """Все сценарии съёмки по имени."""
    found = []
    for path in sorted(SHOTS.glob("*.js")) if SHOTS.is_dir() else []:
        name, _, rest = path.name.partition(".")
        if rest in ("shot.js", "clip.js"):
            found.append(Shot(name, rest.split(".")[0]))
    return found


def select(names=(), only_missing=False, media_dir=None):
    """Сценарии для запуска: по именам (неизвестное имя это ошибка) и, если нужно, только те, чьего файла ещё нет."""
    media_dir = media_dir or pages.MEDIA
    everything = shots()
    known = {s.name for s in everything}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(f"Нет сценария съёмки: {', '.join(unknown)}")
    chosen = [s for s in everything if not names or s.name in names]
    if only_missing:
        chosen = [s for s in chosen if not (media_dir / s.file).is_file()]
    return chosen


def prepare_world():
    """Автор Студии и игрок на демо-машине aether-main (мир уже создан seed_demo); возвращает вход автора и куку игрока.

    Игрок входит как ivan: учётка Django привязана к профилю машины и у неё открыта сессия, как после входа на экране блокировки."""
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.backends.db import SessionStore

    from machines.current import SESSION_KEY
    from machines.models import MachineProfile, Session

    User = get_user_model()
    author, _ = User.objects.get_or_create(username=AUTHOR[0], defaults={"is_staff": True, "is_superuser": True})
    author.is_staff = author.is_superuser = True
    author.set_password(AUTHOR[1])
    author.save()
    player, _ = User.objects.get_or_create(username=PLAYER)
    profile = MachineProfile.objects.get(machine__hostname="aether-main", login="ivan")
    profile.user = player
    profile.save()
    machine_session = Session.objects.create(user=player, profile=profile)
    store = SessionStore()
    store["_auth_user_id"] = str(player.pk)
    store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    store["_auth_user_hash"] = player.get_session_auth_hash()
    store[SESSION_KEY] = machine_session.pk
    store.save()
    return {"author": {"username": AUTHOR[0], "password": AUTHOR[1]}, "player_cookie": store.session_key}
