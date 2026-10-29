"""Мир игры в цифрах: даты, на которые ссылаются журналы консоли.

Пока это константы. Игровая дата потом переедет в базу (настройка мира), а
остальное станет данными машины и сети.

Хронология (лор): 2013 волна терактов, 2027 мировая война, во время неё операция
«Большая охота» почти уничтожила организацию. Игрок приходит уже после, около
2030-2031. Версия Aether старая (2020): прошивку и ядро не меняют каждый год.
"""
from datetime import date, datetime, timezone

GAME_DATE = date(2030, 11, 14)
GAME_NOW = datetime(2030, 11, 14, 3, 14, tzinfo=timezone.utc)   # «сейчас» в мире игры (часы узла)
CORE_LAST_CONTACT = date(2027, 10, 29)  # с тех пор центральный узел не отвечает (конец октября 2027)
BEACON_LAST_SYNC = date(2027, 10, 27)   # когда в последний раз обновлялись списки станций и мостов
CERT_NOT_AFTER = date(2021, 11, 2)      # сертификат узла давно просрочен


# Лестница допусков Aether: три буквы, греческие названия ступеней посвящения
# (латынь у «Нового Эдема», функциональные названия слишком очевидны).
# Числа в коде (0..5) остаются, игрок видит только код.
CLEARANCE = {
    0: ("MRT", "martys"),        # свидетель: так входит игрок без регистрации
    1: ("AKR", "akroates"),      # слушатель
    2: ("MYS", "mystes"),        # посвящённый
    3: ("EPO", "epoptes"),       # видевший
    4: ("HIE", "hierophant"),    # жрец
    5: ("ARC", "archon"),        # правитель
}


def clearance_code(level):
    return CLEARANCE.get(level, ("???", "unknown"))[0]


def world():
    """Настройки мира (machines.World): одна запись; один раз за запрос. Константы выше только начальные значения."""
    from machines import memo
    from machines.models import World

    return memo.cached(("world",), World.current)


def days_since(day):
    """Сколько дней прошло с этой даты до игровой, с разделителем тысяч: «1,169»."""
    return f"{(world().game_date - day).days:,}"


def ago(moment):
    """Сколько прошло от момента до игровых «сейчас»: «3 min», «5 h», «2 d», «1,114 d»."""
    seconds = int((world().game_now - moment).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400:,} d"
