"""Помощники для тестов: выдать игроку ключи так, как их получает игра, то есть файлами в /home/.secrets."""
from filesystem import keystore


def give_keys(user, *slugs):
    """Сессия игрока user с ключами slugs в папке секретов. Возвращает словарь сессии запроса (SESSION_KEY: id)."""
    from machines.current import SESSION_KEY
    from machines.models import Machine, MachineProfile, Session

    session = Session.objects.filter(user=user).order_by("-pk").first()          # уже начатая игроком сессия
    if session is None:
        machine = Machine.objects.create(name=f"keys-{user.pk}", hostname=f"keys-{user.pk}")
        profile = MachineProfile.objects.create(machine=machine, user=user, name=user.get_username(), login="keys", freq=1)
        session = Session.objects.create(user=user, profile=profile)
        from machines.models import VolumeMount
        from wiki.models import Namespace

        for order, root in enumerate(Namespace.objects.filter(parent=None)):             # вики машины видна целиком
            VolumeMount.objects.create(machine=machine, namespace=root, order=order)
    for slug in slugs:
        keystore.put(session, slug)
    return {SESSION_KEY: session.pk}
