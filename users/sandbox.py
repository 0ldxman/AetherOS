"""Песочница автора: один временный игрок на автора, который ходит по настоящим машинам.

Почти всё изменяемое состояние игры привязано к пользователю (сессии и блокировки, события входа, часы машин, слой файлов,
подключённые диски, почта, переписки, метки, ключи), поэтому отдельный пользователь и есть вся песочница: копий машин нет.
Пока у автора стоит кука песочницы, игровые страницы в его браузере идут от имени песочного игрока со своей сессией Django
(users.middleware.SandboxMiddleware), а Студия и админка остаются за автором. Песочный игрок не виден в Студии и в мире (hide).
«Начать заново» стирает его вместе со всем состоянием.
"""
from django.contrib.auth import get_user_model  # noqa: F401 (им пользуется и studio/api/sandbox.py)
from django.core import signing

COOKIE = "aether_sandbox"              # подписанный id автора: песочница включена
SESSION_COOKIE = "aether_sbx_session"  # своя сессия Django песочного игрока
SALT = "aether.sandbox"
MAX_AGE = 12 * 3600                    # кука живёт полдня, потом песочница сама выключается
# пути, где автор всегда остаётся собой
OWN_PATHS = ("/studio/", "/admin/", "/accounts/", "/static/", "/media/")


def is_sandbox(user):
    return bool(getattr(user, "sandbox_of_id", None))


def sandbox_of(author):
    """Песочный игрок автора (создаётся при первом обращении)."""
    found = get_user_model().objects.filter(sandbox_of=author).first()
    if found is not None:
        return found
    base = f"sandbox-{author.get_username()}"[:140]
    name, n = base, 1
    while get_user_model().objects.filter(username=name).exists():
        n += 1
        name = f"{base}-{n}"
    user = get_user_model()(username=name, sandbox_of=author, is_staff=False, is_superuser=False)
    user.set_unusable_password()
    user.save()
    return user


def reset(author):
    """Стереть песочного игрока со всем его состоянием. Следующий вход создаст нового."""
    from machines.models import LoginEvent

    found = get_user_model().objects.filter(sandbox_of=author).first()
    if found is None:
        return False
    LoginEvent.objects.filter(user=found).delete()       # у событий входа связь SET_NULL: без этого они остались бы ничьими
    found.delete()                                       # остальное (сессии, учётки, файлы, почта, метки, часы) уходит каскадом
    return True


def token(author):
    return signing.dumps(author.pk, salt=SALT)


def author_of(value):
    """id автора из куки песочницы или None (кука подделана или устарела)."""
    if not value:
        return None
    try:
        return signing.loads(value, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None


def hide(queryset, field="user"):
    """Убрать из выборки строки песочных игроков (по полю пользователя; строки без пользователя остаются)."""
    return queryset.exclude(**{f"{field}__sandbox_of__isnull": False})


def real_users(queryset=None):
    return (queryset if queryset is not None else get_user_model().objects).filter(sandbox_of__isnull=True)
