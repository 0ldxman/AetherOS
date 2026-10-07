"""Предпросмотр записи вики в админке (редактор, шаг 1).

Подключается к DocumentAdmin как примесь, поэтому save_model и остальной
код админки не трогаются:

    from .admin_preview import DocumentPreviewMixin

    class DocumentAdmin(DocumentPreviewMixin, admin.ModelAdmin):
        ...

Что делает:
- страница записи в админке получает панель предпросмотра справа
  (шаблон admin/wiki/document/change_form.html, static wiki/editor.js);
- эндпоинт preview/ принимает JSON с ещё не сохранённым текстом и отдаёт
  готовые html-страницы документа и инфобокса. Рендер тот же, что у игрока
  (markup.render и шаблоны wiki/document.html, wiki/infobox.html), поэтому
  закрытые спойлеры замазываются на сервере, а не в браузере;
- «смотреть как»: набор ключей игрока задаётся в запросе, проверка доступа
  к записи в предпросмотре не выполняется (это админка).

Запрос (POST, JSON):
    {"title": "...", "type": "doc", "body": "...", "infobox": "...",
     "keys": {"mode": "all" | "none" | "custom", "list": ["key_a", ...]}}
Ответ:
    {"ok": true, "body": "<html>", "infobox": "<html>"}
    {"ok": false, "error": "текст"}  и статус 4xx/5xx
"""
import json
import logging

from django.http import HttpResponseNotAllowed, JsonResponse
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils.safestring import mark_safe

from secure.models import Key

from . import markup
from .models import Document

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 400_000   # тело запроса целиком
MAX_TITLE_LEN = 200
MAX_KEYS = 500                # сколько ключей принимаем в режиме custom


def _error(message, status):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _text(value):
    return value if isinstance(value, str) else ""


def _preview_keys(spec):
    """Набор slug'ов ключей, под которым рисуется предпросмотр.

    Берутся только существующие ключи: удалённый или опечатанный slug
    просто не попадёт в набор.
    """
    if not isinstance(spec, dict):
        return frozenset()
    existing = set(Key.objects.values_list("slug", flat=True))
    mode = spec.get("mode")
    if mode == "all":
        return frozenset(existing)
    if mode == "custom":
        wanted = spec.get("list")
        if isinstance(wanted, list):
            return frozenset(s for s in wanted[:MAX_KEYS] if isinstance(s, str) and s in existing)
    return frozenset()


class DocumentPreviewMixin:
    change_form_template = "admin/wiki/document/change_form.html"

    def _preview_url_name(self):
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_preview"

    def get_urls(self):
        # свой адрес должен идти раньше стандартных: иначе preview/ примется за id записи
        custom = [
            path(
                "preview/",
                self.admin_site.admin_view(self.preview_view),
                name=self._preview_url_name(),
            ),
        ]
        return custom + super().get_urls()

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["preview_url"] = reverse(
            f"{self.admin_site.name}:{self._preview_url_name()}"
        )
        context["preview_keys"] = list(
            Key.objects.order_by("slug").values("slug", "description")
        )
        return super().render_change_form(request, context, add, change, form_url, obj)

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
        if doc_type not in Document.Type.values:
            doc_type = Document.Type.DOC.value
        doc = Document(title=_text(data.get("title"))[:MAX_TITLE_LEN], type=doc_type)
        keys = _preview_keys(data.get("keys"))

        try:
            body_html = mark_safe(markup.render(_text(data.get("body")), keys, "body"))
            infobox_html = mark_safe(markup.render(_text(data.get("infobox")), keys, "infobox"))
            page_body = render_to_string(
                "wiki/document.html", {"doc": doc, "body_html": body_html}
            )
            page_infobox = render_to_string(
                "wiki/infobox.html", {"doc": doc, "infobox_html": infobox_html}
            )
        except Exception as exc:  # предпросмотр не должен ронять админку
            logger.exception("Ошибка предпросмотра записи вики")
            return _error(f"{type(exc).__name__}: {exc}"[:300], 500)

        return JsonResponse({"ok": True, "body": page_body, "infobox": page_infobox})