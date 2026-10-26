"""Значки меток карты: формы без смысла («звезда», «флажок»), а не категории.

Каждый значок это контур в сетке 24x24. На бумажной карте (scan) он рисуется ручкой, на остальных
плоско с лёгкой заливкой замкнутых фигур. «pin» булавка: рисуется отдельно и в списке только ради имени.
Страница карты отдаёт этот словарь в JSON (map.js, редактор), так что правится он в одном месте.
"""

MARKER_ICONS = {
    "cross": {"label": "Крест", "d": "M5 5L19 19M19 5L5 19", "closed": False},
    "ring": {"label": "Кольцо", "d": "M3.5 12a8.5 8.5 0 1 0 17 0a8.5 8.5 0 1 0 -17 0Z", "closed": True},
    "dot": {"label": "Точка", "d": "M7.5 12a4.5 4.5 0 1 0 9 0a4.5 4.5 0 1 0 -9 0Z", "closed": True, "solid": True},
    "square": {"label": "Квадрат", "d": "M5 5H19V19H5Z", "closed": True},
    "triangle": {"label": "Треугольник", "d": "M12 4L21 19H3Z", "closed": True},
    "diamond": {"label": "Ромб", "d": "M12 3L21 12L12 21L3 12Z", "closed": True},
    "star": {
        "label": "Звезда",
        "d": "M12 3L14.6 9.2L21.3 9.7L16.2 14L17.8 20.5L12 17L6.2 20.5L7.8 14L2.7 9.7L9.4 9.2Z",
        "closed": True,
    },
    "flag": {"label": "Флажок", "d": "M6 21V3M6 4H18L15 8.5L18 13H6", "closed": False},
    "exclaim": {"label": "Восклицательный знак", "d": "M12 3.5V14M12 18.5V19", "closed": False},
    "question": {"label": "Вопросительный знак", "d": "M8 8.5C8 4.5 16 4.5 16 9C16 12.5 12 12.5 12 15.5M12 19V19.5", "closed": False},
    "target": {
        "label": "Прицел",
        "d": "M3.5 12a8.5 8.5 0 1 0 17 0a8.5 8.5 0 1 0 -17 0ZM12 2V7M12 17V22M2 12H7M17 12H22",
        "closed": False,
    },
    "check": {"label": "Галочка", "d": "M4 12.5L9.5 18L20 6", "closed": False},
}

# «pin» булавка (вид по умолчанию на светлой и терминальной карте)
ICON_NAMES = ("pin", *MARKER_ICONS)

ICON_ALIASES = {
    "булавка": "pin", "крест": "cross", "крестик": "cross", "кольцо": "ring", "круг": "ring",
    "точка": "dot", "квадрат": "square", "треугольник": "triangle", "ромб": "diamond",
    "звезда": "star", "флаг": "flag", "флажок": "flag", "восклицание": "exclaim",
    "вопрос": "question", "прицел": "target", "галочка": "check",
}


def icon_name(word):
    """Слово из разметки (star, звезда) -> имя значка или '' (неизвестное и пустое)."""
    word = (word or "").strip().lower()
    word = ICON_ALIASES.get(word, word)
    return word if word in ICON_NAMES else ""
