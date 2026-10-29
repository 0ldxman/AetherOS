"""Виджеты разметки: готовые части документа (шаг 1: листовые виджеты).

Виджет вставляется блоком в любое место тела документа или инфобокса.
Здесь описаны только листовые виджеты: stamp, signature, barcode, log, checks,
masthead (шапка сайта), bar (полоса «сохранено из»), ассеты (asset, image,
audio, video, file), divider (разделитель), а также page (его html пуст:
листы и футеры собирает пакет documents/markup).
Контейнеры (section, box, grid) целиком в пакете documents/markup.

Как работает виджет: на входе простые данные, на выходе готовый html.
Любой пользовательский текст проходит через ctx.inline(текст): это даёт
inline-markdown и строчные спойлеры [текст]{условие}, а всё остальное
экранируется. Значения, которые попадают в атрибуты (tone, angle, align),
сначала проверяются по белому списку или превращаются в число.

Чтобы добавить виджет, достаточно написать функцию с декоратором @widget."""
from documents.widgets import base, maps, media, simple  # noqa: F401  (регистрируют виджеты)
from documents.widgets.base import *  # noqa: F401,F403
from documents.widgets.maps import MARK_COLORS, parse_map_line, split_highlight_token  # noqa: F401
