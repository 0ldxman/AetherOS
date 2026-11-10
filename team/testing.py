"""Помощники тестов команды."""


def full_role():
    """Роль «Полный доступ» (её создаёт миграция team): всё, кроме управления командой."""
    from team.models import Role

    return Role.objects.get(name="Полный доступ")
