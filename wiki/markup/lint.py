"""Проверка текста записи: ошибки разметки и битые ссылки.

Часть пакета wiki.markup (описание синтаксиса: wiki/markup/__init__.py).

lint(text) -> список Issue. Рендер молча закрывает доступ при ошибке в
условии и рисует заглушку на месте виджета с неизвестным ассетом; здесь те
же случаи подсвечиваются автору до публикации. Для разбора берутся те же
правила открытия и закрытия блоков, что и у рендера (lines.py).
"""

import re
from dataclasses import asdict, dataclass
from urllib.parse import unquote, urlsplit

from django.conf import settings

from assets.services import asset_widget_kind, find_asset
from secure.access import condition_slugs
from secure.models import Key
from wiki.models import Document, Namespace
from wiki.widgets import WIDGETS

from .constants import CONTAINERS
from .expr import SpoilerSyntaxError, parse_expr
from .lines import _FENCE_OPEN, _OPEN, _opens_block, _widget_head
from .widget_rule import _parse_args, _parse_body

ERROR = "error"
WARNING = "warning"

# виджеты ассетов: имя -> ожидаемый вид ассета (None: любой)
ASSET_WIDGETS = {
    "asset": None,
    "audio": "audio",
    "video": "video",
    "file": "file",
    "image": "image",
}

# группы: по строке «src | подпись», каждый src проверяется как ассет своего вида
GROUP_WIDGETS = {"gallery": "image", "files": "file"}

_CLOSE = re.compile(r"::\s*$")
_INLINE_SPOILER = re.compile(r"\]\{([^}\n]*)\}")
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)")

# адреса вики на сайте; всё прочее (внешние ссылки, якоря) не проверяется
_WIKI_PREFIXES = ("/apps/wiki/", "/wiki/")


@dataclass(frozen=True)
class Issue:
    line: int
    level: str
    code: str
    message: str

    def as_dict(self):
        return asdict(self)


def _block_body(lines, start):
    """Строки блока после открытия до «::» (для параметров виджета)."""
    body = []
    for line in lines[start + 1:]:
        text = line.strip()
        if _CLOSE.match(text):
            break
        body.append(text)
    return body


class _Scan:
    """Первый проход: структура блоков и всё, что нужно проверить по базе."""

    def __init__(self, text):
        self.issues = []
        self.keys = []     # (строка, slug)
        self.assets = []   # (строка, виджет, ссылка)
        self.regions = []  # (строка, код провинции) из ::map regions=...
        self.links = []    # (строка, адрес)
        self._run(text.splitlines())

    def issue(self, line, level, code, message):
        self.issues.append(Issue(line, level, code, message))

    def _run(self, lines):
        stack = []          # открытые блоки: (имя, строка)
        fence = None        # (символ, длина, строка) открытого блока кода

        for index, raw in enumerate(lines):
            number = index + 1
            text = raw.strip()

            marker = _FENCE_OPEN.match(raw)
            if marker:
                char, length = marker.group(1)[0], len(marker.group(1))
                if fence is None:
                    fence = (char, length, number)
                    continue
                if char == fence[0] and length >= fence[1]:
                    fence = None
                    continue
            if fence is not None:
                continue

            if _CLOSE.match(text):
                if stack:
                    stack.pop()
                else:
                    self.issue(number, WARNING, "stray-close", "Лишняя «::»: нет открытого блока.")
                continue

            if text.startswith("::"):
                self._directive(lines, index, text, stack)

            self._inline(number, text)

        for name, number in stack:
            self.issue(number, ERROR, "unclosed-block", f"Блок ::{name} не закрыт строкой «::».")
        if fence is not None:
            self.issue(fence[2], WARNING, "unclosed-fence", "Блок кода не закрыт: он поглотит весь текст ниже.")

    def _directive(self, lines, index, text, stack):
        number = index + 1
        spoiler = _OPEN.match(text)

        if spoiler:
            self._condition(number, spoiler.group(1) or "")
            stack.append(("spoiler", number))
            return

        head = _widget_head(text)
        if head is None:
            return
        name, args, is_block = head

        if name not in WIDGETS and name not in CONTAINERS:
            self.issue(number, ERROR, "unknown-widget", f"Неизвестный виджет ::{name}.")

        if name in ASSET_WIDGETS:
            entry = WIDGETS[name]
            params = (
                _parse_args(args, entry.positional)
                if args
                else _parse_body(_block_body(lines, index))
            )
            self.assets.append((number, name, (params.get("src") or "").strip()))

        if name == "map" and args:
            for code in re.split(r"[\s,;]+", _parse_args(args, None).get("regions", "")):
                if code:
                    self.regions.append((number, code))

        if name in GROUP_WIDGETS:
            for offset, row in enumerate(_block_body(lines, index), 1):
                src = row.partition("|")[0].strip()
                if src:
                    self.assets.append((number + offset, GROUP_WIDGETS[name], src))

        if _opens_block(text):
            stack.append((name, number))

    def _condition(self, number, source):
        try:
            condition = parse_expr(source)
        except SpoilerSyntaxError as exc:
            self.issue(number, ERROR, "bad-condition", f"Условие спойлера: {exc}")
            return
        self.keys.extend((number, slug) for slug in condition_slugs(condition))

    def _inline(self, number, text):
        text = _CODE_SPAN.sub("", text)
        for match in _INLINE_SPOILER.finditer(text):
            self._condition(number, match.group(1))
        for match in _LINK.finditer(text):
            self.links.append((number, match.group(1)))


# =========================================================
# Проверка по базе
# =========================================================

def _wiki_target(href):
    """Путь внутри вики из адреса ссылки или None, если ссылка не на вики."""
    path = unquote(urlsplit(href).path)
    prefix = (settings.FORCE_SCRIPT_NAME or "").rstrip("/")
    if prefix and path.startswith(prefix + "/"):
        path = path[len(prefix):]
    for start in _WIKI_PREFIXES:
        if path.startswith(start):
            return path[len(start):]
    return None


class _Wiki:
    """Существование записей и разделов по пути; считает базу лениво."""

    def __init__(self):
        self._by_name = None

    def _namespaces(self):
        if self._by_name is None:
            self._by_name = {
                (n.parent_id, n.name): n for n in Namespace.objects.all()
            }
        return self._by_name

    def exists(self, target):
        if target.startswith("go/"):
            slug = target[3:].strip("/")
            return Document.objects.filter(direct_link=slug).exists()
        parts = [p for p in target.split("/") if p]
        if not parts or parts == ["search"]:
            return True
        by_name = self._namespaces()
        current = None
        for part in parts[:-1]:
            current = by_name.get((current.pk if current else None, part))
            if current is None:
                return False
        last = parts[-1]
        if (current.pk if current else None, last) in by_name:
            return True
        return Document.objects.filter(namespace=current, title=last).exists()


def lint(text):
    """Проблемы в тексте записи, по порядку строк."""
    scan = _Scan(text or "")
    issues = list(scan.issues)

    known = set(
        Key.objects.filter(slug__in={slug for _, slug in scan.keys}).values_list("slug", flat=True)
    )
    for number, slug in scan.keys:
        if slug not in known:
            issues.append(Issue(number, WARNING, "unknown-key", f"Ключа «{slug}» нет в базе."))

    found = {}
    for number, widget, ref in scan.assets:
        if ref not in found:
            found[ref] = find_asset(ref)
        asset = found[ref]
        if asset is None:
            shown = ref or "(src не указан)"
            issues.append(Issue(number, ERROR, "asset-missing", f"Ассет {shown} не найден."))
            continue
        wanted = ASSET_WIDGETS[widget]
        if wanted and asset_widget_kind(asset) != wanted:
            issues.append(Issue(
                number, ERROR, "asset-type",
                f"::{widget} не подходит ассету «{ref}»: это {asset_widget_kind(asset)}.",
            ))

    if scan.regions:
        from map.models import Province

        known = {code.upper() for code in Province.objects.filter(
            code__in={code.upper() for _, code in scan.regions}
        ).values_list("code", flat=True)}
        for number, code in scan.regions:
            if code.upper() not in known:
                issues.append(Issue(number, ERROR, "region-missing", f"Провинции {code} нет в базе карты."))

    wiki = _Wiki()
    checked = {}
    for number, href in scan.links:
        target = _wiki_target(href)
        if target is None:
            continue
        if target not in checked:
            checked[target] = wiki.exists(target)
        if not checked[target]:
            issues.append(Issue(number, WARNING, "broken-link", f"Запись или раздел не найдены: {target}."))

    issues.sort(key=lambda i: (i.line, i.level != ERROR))
    return issues
