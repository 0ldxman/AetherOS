"""Виджеты ассетов: картинка, звук, видео, файл, галерея и список файлов."""
from html import escape

from assets.services import asset_widget_kind, find_asset
from pathlib import PurePosixPath
from documents.widgets.base import ALIGNS, GALLERY_COLS, IMAGE_RATIOS, MAX_FILES, MAX_GALLERY, _asset_urls, _choice, _head_args, _human_size, _num, _src_lines, barcode_value, widget


def _asset_missing(ref, text="ASSET NOT FOUND"):
    return (
        '<div class="widget widget--asset-missing">'
        f'<span class="asset-missing-text">{text}</span>'
        f'<span class="asset-missing-ref">{escape(ref)}</span></div>\n'
    )


def _asset_figure(kind, inner, params, ctx):
    """Общая обёртка: width, align, caption."""
    default_width = 100 if kind == "audio" else 60
    width = _num(params.get("width"), default_width, 10, 100)
    align = _choice(params.get("align"), ALIGNS, "center")
    caption = ""
    if params.get("caption"):
        caption = f'<figcaption class="asset-caption">{ctx.inline(params["caption"])}</figcaption>'
    return (
        f'<figure class="widget widget--{kind} widget--align-{align}" style="--w: {width}%">'
        f'{inner}{caption}</figure>\n'
    )


def _render_image(asset, urls, params, ctx):
    content, viewer = urls
    alt = params.get("alt") or asset.name
    img = (
        f'<img class="image-img" src="{escape(content, quote=True)}" '
        f'alt="{escape(alt, quote=True)}" loading="lazy">'
    )
    if viewer:
        # href работает и без JS; main.js перехватывает клик и открывает окно
        img = (
            f'<a class="image-link" href="{escape(viewer, quote=True)}" '
            f'data-asset-viewer="{escape(viewer, quote=True)}" '
            f'data-asset-title="{escape(asset.name, quote=True)}">{img}</a>'
        )
    return _asset_figure("image", f'<div class="image-frame">{img}</div>', params, ctx)


def _render_audio(asset, urls, params, ctx):
    title = ctx.inline(params.get("title") or asset.name)

    filename = getattr(asset, "filename", None) or asset.name
    extension = PurePosixPath(filename).suffix.lower() or "—"

    audio_url, viewer_url = urls
    audio_id = escape(str(asset.public_id), quote=True)
    audio_src = escape(audio_url, quote=True)
    viewer_title = escape(str(filename), quote=True)
    extension_html = escape(extension, quote=True)

    # viewer_url может быть None (нет маршрута), поэтому escape() без проверки упадёт
    if viewer_url:
        viewer_href = escape(viewer_url, quote=True)
        id_html = (
            f'<a class="audio-id-link" href="{viewer_href}" '
            f'data-asset-viewer="{viewer_href}" '
            f'data-asset-title="{viewer_title}">{audio_id}</a>'
        )
        viewer_attr = f' data-viewer-url="{viewer_href}"'
    else:
        id_html = audio_id
        viewer_attr = ""

    # Универсальная часть: её используют web, doc, rec, infobox
    plain = (
        f'<div class="audio-title">{title}</div>'
        f'<audio class="audio-el" controls preload="none" src="{audio_src}"></audio>'
    )

    # Карточка: только для scan
    card = (
        '<div class="audio-card">'
        '<div class="audio-card-field audio-card-field--title">'
        '<span class="audio-card-label">TITLE:</span>'
        f'<span class="audio-card-value audio-card-title">{title}</span></div>'
        '<div class="audio-card-meta">'
        '<div class="audio-card-field audio-card-field--id">'
        '<span class="audio-card-label">ID:</span>'
        f'<span class="audio-card-value">{id_html}</span></div>'
        '<div class="audio-card-field audio-card-field--type">'
        '<span class="audio-card-label">TYPE:</span>'
        f'<span class="audio-card-value">{extension_html}</span></div>'
        '<div class="audio-card-field audio-card-field--duration">'
        '<span class="audio-card-label">DURATION:</span>'
        '<span class="audio-card-value audio-duration">—:—</span></div>'
        '</div>'
        f'<div class="audio-card-waveform" data-audio-src="{audio_src}" '
        'aria-label="Осциллограмма аудиозаписи">'
        '<svg class="audio-waveform-svg" viewBox="0 0 600 72" '
        'preserveAspectRatio="none" aria-hidden="true"></svg></div>'
        '</div>'
    )

    figure = _asset_figure("audio", plain + card, params, ctx)

    # Метаданные для встроенного плеера (audio-widget.js)
    metadata = (
        f'data-file-name="{viewer_title}" '
        f'data-asset-id="{audio_id}"'
        f'{viewer_attr}'
    )

    return figure.replace(
        'class="widget widget--audio',
        f'{metadata} class="widget widget--audio',
        1,
    )


def _render_video(asset, urls, params, ctx):
    filename = getattr(asset, "name", None) or asset.name
    source_name = getattr(asset, "filename", None)
    ext = (PurePosixPath(source_name).suffix if source_name else "") or ".mp4"

    asset_id = asset.public_id
    content, viewer = urls

    inner = (
        f'<video class="video-el" controls preload="metadata" '
        f'src="{escape(content, quote=True)}"></video>'
    )

    figure = _asset_figure("video", inner, params, ctx)

    viewer_attr = (
        f' data-viewer-url="{escape(viewer, quote=True)}"'
        if viewer else ""
    )

    metadata = (
        f'data-file-name="{escape(str(filename + ext), quote=True)}" '
        f'data-asset-id="{escape(str(asset_id), quote=True)}"'
        f'{viewer_attr}'
    )

    figure = figure.replace(
        'class="widget widget--video',
        f'{metadata} class="widget widget--video',
        1,
    )

    return figure


def _render_file(asset, urls, params, ctx):
    content, viewer = urls
    label = ctx.inline(params.get("label") or asset.filename or asset.name)
    size = _human_size(asset.size)

    code = barcode_value(str(asset.public_id))
    real_id = escape(str(asset.public_id), quote=True)
    real_name = escape(str(asset.name or asset.filename), quote=True)
    code_attr = f' data-barcode="{code}" data-id="{real_id}"' if code else ""

    source_name = getattr(asset, "filename", None) or asset.name or ""
    ext = PurePosixPath(str(source_name)).suffix.lstrip(".").upper()
    tag = escape(f"[{ext}]" if ext else "[FILE]", quote=True)

    main = (
        f'<a class="file-main" href="{escape(content, quote=True)}" download '
        f'data-filename="{real_name}" data-tag="{tag}">{label}</a>'
    )
    dots = '<span class="file-dots"></span>'
    size_html = f'<span class="file-size">{size}</span>' if size else ""
    open_html = ""
    v = escape(viewer, quote=True) if viewer else ""
    if viewer:
        open_html = (
            f'<a class="file-open" href="{v}" data-asset-viewer="{v}" '
            f'data-asset-title="{escape(asset.name, quote=True)}">Открыть</a>'
        )

    return (
        f'<div class="widget widget--file"{code_attr}>'
        f'{main}{dots}{size_html}{open_html}</div>\n'
    )


_ASSET_RENDERERS = {
    "image": _render_image,
    "audio": _render_audio,
    "video": _render_video,
    "file": _render_file,
}


def _asset_widget(params, ctx, forced=None):
    ref = (params.get("src") or "").strip()
    asset = find_asset(ref)
    if asset is None:
        return _asset_missing(ref)
    urls = _asset_urls(asset)
    if urls[0] is None:
        return _asset_missing(ref)
    kind = asset_widget_kind(asset)
    if forced and kind != forced:
        return _asset_missing(ref, "ASSET TYPE MISMATCH")
    return _ASSET_RENDERERS[kind](asset, urls, params, ctx)


@widget("asset", positional="src")
def asset(params, ctx):
    """Ассет любого вида: ::asset theme-01 caption="Тема". Вид выбирается по типу файла."""
    return _asset_widget(params, ctx)


@widget("audio", positional="src")
def audio(params, ctx):
    """::audio theme-01 title="Тема города" """
    return _asset_widget(params, ctx, "audio")


@widget("video", positional="src")
def video(params, ctx):
    """::video intro-01 width=80 caption="Вступление" """
    return _asset_widget(params, ctx, "video")


@widget("file", positional="src")
def file(params, ctx):
    """::file report-01 label="Отчёт (PDF)" """
    return _asset_widget(params, ctx, "file")


@widget("image", positional="src")
def image(params, ctx):
    """Картинка: src=slug или UUID, alt, caption, width (10-100, %),
    align (left/center/right), ratio (для рамки, если картинки нет).

    Если ассета нет или он не картинка, вместо неё рамка с подписью alt,
    как у непрогрузившейся картинки в сохранённой странице.
    """
    ref = (params.get("src") or "").strip()
    found = find_asset(ref)
    if found is not None and asset_widget_kind(found) == "image":
        urls = _asset_urls(found)
        if urls[0]:
            return _render_image(found, urls, params, ctx)

    alt = params.get("alt", "")
    ratio = IMAGE_RATIOS.get((params.get("ratio") or "").strip(), "16-9")
    shown = ctx.inline(alt) if alt else "NO IMAGE"
    inner = f'<div class="image-frame"><div class="image-missing image-ratio-{ratio}"><span>{shown}</span></div></div>'
    return _asset_figure("image", inner, params, ctx)


@widget("gallery", raw=True)
def gallery(text, ctx, args=""):
    """Несколько картинок: по строке «src | подпись». Параметры: cols (1-4, для плитки), caption.

    ::gallery cols=2 caption="Место происшествия"
    photo-01 | Вход
    photo-02 | Задний двор
    ::

    Вид зависит от документа (его выбирает wiki.js по классу страницы): у web, rec и инфобокса
    это карусель с кнопками, у doc и scan плитка из кадров, как фотографии на печатном листе.
    """
    head = _head_args(args)
    rows = _src_lines(text, MAX_GALLERY)
    if not rows:
        return ""

    cols = int(float(_num(head.get("cols"), 2, GALLERY_COLS[0], GALLERY_COLS[-1])))
    items = "".join(
        '<div class="gallery-item">'
        + image({"src": src, "caption": caption, "alt": caption, "width": "100", "align": "center"}, ctx)
        + "</div>"
        for src, caption in rows
    )
    controls = (
        '<div class="gallery-controls">'
        '<button type="button" class="gallery-prev" aria-label="Назад">&lsaquo;</button>'
        f'<span class="gallery-count">1 / {len(rows)}</span>'
        '<button type="button" class="gallery-next" aria-label="Вперёд">&rsaquo;</button>'
        "</div>"
    )
    caption = ""
    if head.get("caption"):
        caption = f'<div class="gallery-caption">{ctx.inline(head["caption"])}</div>'
    return (
        f'<div class="widget widget--gallery gallery--cols-{cols}" data-count="{len(rows)}">'
        f'{caption}<div class="gallery-items">{items}</div>{controls}</div>\n'
    )


@widget("files", raw=True)
def files(text, ctx, args=""):
    """Несколько файлов одной группой: по строке «src | подпись». Параметры: title.

    ::files title="Приложения"
    report-01 | Отчёт (PDF)
    photos-zip | Фотографии
    ::

    Одна цельная рамка с шапкой и строками; цвета и шрифты берёт у стиля документа.
    """
    head = _head_args(args)
    rows = _src_lines(text, MAX_FILES)
    if not rows:
        return ""

    items = "".join(_files_row(src, label, ctx) for src, label in rows)
    title = ctx.inline(head["title"]) if head.get("title") else "Приложения"
    return (
        '<div class="widget widget--files">'
        f'<div class="files-head"><span class="files-title">{title}</span>'
        f'<span class="files-count">{len(rows)}</span></div>{items}</div>\n'
    )


def _files_row(src, label, ctx):
    """Строка группы файлов: [PDF] название ..... размер  Открыть."""
    found = find_asset(src)
    urls = _asset_urls(found) if found is not None else (None, None)
    if found is None or urls[0] is None:
        return (
            '<div class="files-row files-row--missing">'
            '<span class="files-tag">?</span>'
            f'<span class="files-name">{escape(src)}</span>'
            '<span class="files-dots"></span><span class="files-size">ASSET NOT FOUND</span></div>'
        )
    content, viewer = urls
    source_name = getattr(found, "filename", None) or found.name or ""
    ext = PurePosixPath(str(source_name)).suffix.lstrip(".").upper() or "FILE"
    name = ctx.inline(label or found.filename or found.name)
    size = _human_size(found.size)
    size_html = f'<span class="files-size">{size}</span>' if size else ""
    code = barcode_value(str(found.public_id))
    code_attr = f' data-barcode="{code}" data-id="{escape(str(found.public_id), quote=True)}"' if code else ""
    open_html = ""
    if viewer:
        v = escape(viewer, quote=True)
        open_html = (
            f'<a class="files-open" href="{v}" data-asset-viewer="{v}" '
            f'data-asset-title="{escape(found.name, quote=True)}">Открыть</a>'
        )
    # вся этикетка scan кликабельна: открывает вьювер, а без вьювера скачивает (в остальных стилях скрыта)
    hit_url, hit_extra = (v, f' data-asset-viewer="{v}" data-asset-title="{escape(found.name, quote=True)}"') if viewer else (escape(content, quote=True), " download")
    hit = f'<a class="files-hit" href="{hit_url}"{hit_extra} aria-label="{escape(source_name or found.name, quote=True)}"></a>'
    return (
        f'<div class="files-row"{code_attr}>{hit}'
        f'<span class="files-tag">{escape(ext[:5])}</span>'
        f'<a class="files-name" href="{escape(content, quote=True)}" download>{name}</a>'
        f'<span class="files-dots"></span>{size_html}{open_html}</div>'
    )
