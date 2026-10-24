"""Общие настройки разметки: варианты, лимиты, символ замазки.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).
"""


# =========================================================
# Общие настройки
# =========================================================

VARIANTS = ("body", "infobox")

MASK_CHAR = "█"

EXPR_MAX_LEN = 200

PARAM_MAX_LEN = 300
RAW_MAX_LEN = 5000

CONTAINERS = ("section", "box", "grid", "fold")

FOLD_DEFAULT_TITLE = "Подробнее"

GRID_MAX_COLS = 12
GRID_MAX_CELLS = 200

BOX_FLAGS = (
    "border",
    "dark",
    "center",
    "right",
    "small",
    "big",
    "bold",
    "muted",
    "flush",
)
