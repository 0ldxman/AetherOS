"""Справка автора: markdown-страницы в docs/guide, оглавление, поиск и подстановка картинок и видео.

Страница это файл `docs/guide/<имя>.md` с шапкой (title, section, order). В тексте, кроме обычного markdown:
  ![подпись](shot:имя)   картинка docs/guide/media/имя.png (снимает команда docs_media)
  ![подпись](clip:имя)   короткое видео docs/guide/media/имя.webm
  [текст](page:имя)      ссылка на другую страницу справки
Нет файла картинки или видео: на его месте заглушка, а не битая ссылка. Файлы страниц читаются при каждом запросе,
поэтому правка текста видна сразу.
"""
import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown
from django.conf import settings

ROOT = Path(settings.BASE_DIR) / "docs" / "guide"
MEDIA = ROOT / "media"
KINDS = {"shot": ("png", "img"), "clip": ("webm", "video")}
TOKEN = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<kind>shot|clip):(?P<name>[\w-]+)\)\s*$", re.M)
PAGE_LINK = re.compile(r"\]\(page:([\w-]+)(#[\w-]+)?\)")
HEAD = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass
class Page:
    slug: str
    title: str
    section: str
    order: int
    source: str = field(repr=False, default="")


def _read(path):
    text = path.read_text(encoding="utf-8")
    meta, found = {}, HEAD.match(text)
    if found:
        for line in found.group(1).splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        text = text[found.end():]
    try:
        order = int(meta.get("order", 1000))
    except ValueError:
        order = 1000
    return Page(slug=path.stem, title=meta.get("title") or path.stem, section=meta.get("section") or "Прочее", order=order, source=text)


def pages():
    """Все страницы справки по порядку (order, затем имя файла)."""
    found = [_read(path) for path in ROOT.glob("*.md")] if ROOT.is_dir() else []
    return sorted(found, key=lambda page: (page.order, page.slug))


def get(slug):
    return next((page for page in pages() if page.slug == slug), None)


def sections():
    """[(раздел, [страницы])] в порядке первой страницы раздела."""
    grouped = {}
    for page in pages():
        grouped.setdefault(page.section, []).append(page)
    return list(grouped.items())


def media_path(name):
    """Файл из docs/guide/media по имени или None: имя без путей, чужое не отдаём."""
    if not re.fullmatch(r"[\w-]+\.(png|webm)", name or ""):
        return None
    path = MEDIA / name
    return path if path.is_file() else None


def _figure(match, media_url):
    kind, name, alt = match["kind"], match["name"], match["alt"]
    extension, tag = KINDS[kind]
    file = f"{name}.{extension}"
    caption = f"<figcaption>{html.escape(alt)}</figcaption>" if alt else ""
    if media_path(file) is None:
        what = "снимок" if kind == "shot" else "видео"
        return f'\n<figure class="missing"><div>{what} не сделан: {html.escape(name)}</div>{caption}</figure>\n'
    url = media_url(file)
    if tag == "img":
        body = f'<img src="{url}" alt="{html.escape(alt)}" loading="lazy">'
    else:
        body = f'<video src="{url}" autoplay loop muted playsinline controls preload="metadata"></video>'
    return f"\n<figure>{body}{caption}</figure>\n"


def media_names(source):
    """[(вид, имя)] картинок и видео, которые страница ждёт."""
    return [(m["kind"], m["name"]) for m in TOKEN.finditer(source)]


def missing_media():
    """[(страница, файл)] без файла: что ещё должна снять команда docs_media."""
    out = []
    for page in pages():
        for kind, name in media_names(page.source):
            file = f"{name}.{KINDS[kind][0]}"
            if media_path(file) is None:
                out.append((page.slug, file))
    return out


def render(page, media_url):
    """(html, заголовки) страницы; media_url(файл) даёт адрес картинки."""
    source = TOKEN.sub(lambda m: _figure(m, media_url), page.source)
    source = PAGE_LINK.sub(lambda m: f"](#/guide/{m.group(1)})", source)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "attr_list"], extension_configs={"toc": {"toc_depth": "2-3"}})
    out = md.convert(source)
    heads = [{"id": item["id"], "title": item["name"], "level": item["level"]} for item in _flatten(md.toc_tokens)]
    return out, heads


def _flatten(tokens):
    for token in tokens:
        yield token
        yield from _flatten(token["children"])


def _plain(source):
    """Текст страницы без разметки: для поиска и фрагментов."""
    text = TOKEN.sub("", source)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[#*`>|]+|\s+", " ", text).strip()


def search(query, limit=20):
    """[(страница, фрагмент)] по вхождению слов запроса в заголовок и текст; заголовок весомее текста."""
    words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
    if not words:
        return []
    scored = []
    for page in pages():
        text = _plain(page.source)
        low, title = text.lower(), page.title.lower()
        if not all(w in low or w in title for w in words):
            continue
        score = sum(5 for w in words if w in title) + sum(low.count(w) for w in words)
        at = min((low.find(w) for w in words if w in low), default=0)
        start = text.rfind(" ", 0, max(0, at - 40)) + 1 if at > 40 else 0
        snippet = ("… " if start else "") + text[start:start + 150].strip()
        scored.append((score, page, snippet))
    scored.sort(key=lambda item: -item[0])
    return [(page, snippet) for _, page, snippet in scored[:limit]]
