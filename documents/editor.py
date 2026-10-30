"""Редактор документа в админке: предпросмотр разметки и поиск ассетов для вставки.

Подключается к админке как примесь (у объекта это filesystem.admin.preview.ItemPreviewMixin, она же задаёт шаблон
страницы с редактором documents/editor.js), поэтому save_model и остальной код админки не трогаются.

Что делает:
- эндпоинт preview/ принимает JSON с ещё не сохранённым текстом и отдаёт
  готовые html-страницы документа и инфобокса. Рендер тот же, что у игрока
  (markup.render и шаблоны documents/document.html, documents/infobox.html), поэтому
  закрытые спойлеры замазываются на сервере, а не в браузере;
- «смотреть как»: набор ключей игрока задаётся в запросе, проверка доступа
  к записи в предпросмотре не выполняется (это админка).

Поиск ассетов для вставки (GET assets/?q=текст):
    {"ok": true, "items": [{"ref", "name", "filename", "kind"}]}
    ref - то, что пишется в разметке (slug, а если его нет, UUID);
    kind - имя виджета для этого ассета (audio, video, image, file).

Запрос (POST, JSON):
    {"title": "...", "type": "doc", "body": "...", "infobox": "...",
     "keys": {"mode": "all" | "none" | "custom", "list": ["key_a", ...]}}
Ответ:
    {"ok": true, "body": "<html>", "infobox": "<html>",
     "issues": {"body": [проблема, ...], "infobox": [...]}}
    проблема: {"line", "level": "error" | "warning", "code", "message"},
    список строится markup.lint и не влияет на предпросмотр
    {"ok": false, "error": "текст"}  и статус 4xx/5xx
"""
import json
import logging
from types import SimpleNamespace

from django.db.models import Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils.safestring import mark_safe

from assets.models import Asset
from assets.services import asset_widget_kind
from secure.keys import key_rows

from documents import markup
from secure.requestkeys import keys_for_mode

DOC_TYPES = ("doc", "scan", "web", "rec")

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 400_000   # тело запроса целиком
MAX_TITLE_LEN = 200
MAX_KEYS = 500                # сколько ключей принимаем в режиме custom
MAX_ASSET_RESULTS = 20        # сколько ассетов отдаёт поиск для вставки


def _error(message, status):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _text(value):
    return value if isinstance(value, str) else ""


def _preview_keys(spec):
    """Набор slug'ов ключей, под которым рисуется предпросмотр."""
    if not isinstance(spec, dict):
        return frozenset()
    listed = spec.get("list")
    if not isinstance(listed, list):
        listed = []
    listed = [s for s in listed[:MAX_KEYS] if isinstance(s, str)]
    return keys_for_mode(spec.get("mode"), listed)


def _lint_fields(data):
    """Проблемы текста и инфобокса; сбой проверки не должен ломать предпросмотр."""
    result = {}
    for field in ("body", "infobox"):
        try:
            result[field] = [i.as_dict() for i in markup.lint(_text(data.get(field)))]
        except Exception:
            logger.exception("Ошибка проверки текста документа (%s)", field)
            result[field] = []
    return result


def render_preview(format_name, title, body, meta, keys, only=""):
    """Страницы документа и врезки для предпросмотра (не сохранённый текст) и проблемы разметки.

    Формат с разметкой рисуется парсером, остальные показываются текстом как есть. Общая для админки и студии.
    only="body" или "infobox" рисует только эту страницу (вторая приходит пустой): студии нужна открытая вкладка."""
    from django.utils.html import escape

    from documents.kinds import doc_type
    from filesystem.models import FileFormat

    found = FileFormat.objects.filter(name=format_name).first()
    doc = SimpleNamespace(title=title[:MAX_TITLE_LEN], type=doc_type(found.name) if found else "doc", pk="")
    page, infobox = "", ""
    if only != "infobox":
        if found is not None and found.markup:
            body_html = mark_safe(markup.render(body, keys, "body"))
        else:
            body_html = mark_safe(f"<pre style=\"white-space:pre-wrap;font:13px/1.5 monospace\">{escape(body)}</pre>")
        page = render_to_string("documents/document.html", {"doc": doc, "body_html": body_html})
    if only != "body":
        infobox = render_to_string("documents/infobox.html", {"doc": doc, "infobox_html": mark_safe(markup.render(meta, keys, "infobox"))})
    return {
        "body": page,
        "infobox": infobox,
        "issues": _lint_fields({"body": body, "infobox": meta}),
    }


def _asset_item(asset):
    return {
        "ref": asset.slug or str(asset.public_id),
        "name": asset.name,
        "filename": asset.filename,
        "kind": asset_widget_kind(asset),
    }


class DocumentPreviewMixin:
    def _url_name(self, suffix):
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_{suffix}"

    def _admin_url(self, suffix):
        return reverse(f"{self.admin_site.name}:{self._url_name(suffix)}")

    def get_urls(self):
        # свой адрес должен идти раньше стандартных: иначе preview/ примется за id записи
        custom = [
            path(
                "preview/",
                self.admin_site.admin_view(self.preview_view),
                name=self._url_name("preview"),
            ),
            path(
                "assets/",
                self.admin_site.admin_view(self.assets_view),
                name=self._url_name("assets"),
            ),
        ]
        return custom + super().get_urls()

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["preview_url"] = self._admin_url("preview")
        context["assets_url"] = self._admin_url("assets")
        try:
            from django.urls import reverse

            context["scenes_url"] = reverse("admin:map_mapscene_find")
        except Exception:
            context["scenes_url"] = ""
        context["preview_keys"] = key_rows()
        return super().render_change_form(request, context, add, change, form_url, obj)

    def assets_view(self, request):
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            return _error("Нет прав на редактирование записей.", 403)
        query = request.GET.get("q", "").strip()[:100]
        found = Asset.objects.order_by("name")
        if query:
            found = found.filter(
                Q(name__icontains=query)
                | Q(slug__icontains=query)
                | Q(filename__icontains=query)
            )
        items = [_asset_item(a) for a in found[:MAX_ASSET_RESULTS]]
        return JsonResponse({"ok": True, "items": items})

    def preview_view(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            return _error("Нет прав на редактирование записей.", 403)
        if len(request.body) > MAX_REQUEST_BYTES:
            return _error("Текст слишком большой для предпросмотра.", 413)

        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return _error("Некорректный запрос.", 400)
        if not isinstance(data, dict):
            return _error("Некорректный запрос.", 400)

        doc_type = data.get("type")
        if doc_type not in DOC_TYPES:
            doc_type = "doc"
        doc = SimpleNamespace(title=_text(data.get("title"))[:MAX_TITLE_LEN], type=doc_type, pk="")
        keys = _preview_keys(data.get("keys"))

        try:
            body_html = mark_safe(markup.render(_text(data.get("body")), keys, "body"))
            infobox_html = mark_safe(markup.render(_text(data.get("infobox")), keys, "infobox"))
            page_body = render_to_string(
                "documents/document.html", {"doc": doc, "body_html": body_html}
            )
            page_infobox = render_to_string(
                "documents/infobox.html", {"doc": doc, "infobox_html": infobox_html}
            )
        except Exception as exc:  # предпросмотр не должен ронять админку
            logger.exception("Ошибка предпросмотра документа")
            return _error(f"{type(exc).__name__}: {exc}"[:300], 500)

        return JsonResponse(
            {
                "ok": True,
                "body": page_body,
                "infobox": page_infobox,
                "issues": _lint_fields(data),
            }
        )