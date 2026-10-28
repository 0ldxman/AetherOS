"""Предпросмотр объекта в админке: тот же редактор и рендер, что у записи вики (wiki.admin_preview), поля объекта вместо полей записи.

Редактор вики ищет поля формы по id (title, type, body, infobox); у объекта они называются name, format, body, meta, и
filesystem/static/filesystem/item_admin.js переименовывает их до запуска редактора. Для форматов, которые умеют быть страницей вики
(FileFormat.page), текст рендерится разметкой вики; остальные показываются как есть.
"""
import json
import logging

from django.http import HttpResponseNotAllowed, JsonResponse
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils.safestring import mark_safe

from wiki import markup
from wiki.admin_preview import (
    MAX_REQUEST_BYTES, MAX_TITLE_LEN, DocumentPreviewMixin, _error, _lint_fields, _preview_keys, _text,
)
from wiki.models import Document

from filesystem.models import KEY_FORMAT, FileFormat, Item

logger = logging.getLogger(__name__)


def format_table():
    """Формат -> что вводится и страница ли это; редактор переключает поля содержимого по этой таблице."""
    return {
        found.name: {"content": found.content, "page": found.page, "title": found.title}
        for found in FileFormat.objects.all()
    }


class ItemPreviewMixin(DocumentPreviewMixin):
    change_form_template = "admin/filesystem/item/change_form.html"

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        response = super().render_change_form(request, context, add, change, form_url, obj)
        data = response.context_data
        data["preview_keys"] = [
            {"slug": row["slug"], "description": row["name"]}
            for row in Item.objects.filter(format=KEY_FORMAT).order_by("slug").values("slug", "name")
        ]
        data["formats"] = format_table()
        data["revisions_url"] = ""
        return response

    def preview_view(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            return _error("Нет прав на редактирование объектов.", 403)
        if len(request.body) > MAX_REQUEST_BYTES:
            return _error("Текст слишком большой для предпросмотра.", 413)
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return _error("Некорректный запрос.", 400)
        if not isinstance(data, dict):
            return _error("Некорректный запрос.", 400)

        found = FileFormat.objects.filter(name=_text(data.get("type"))).first()
        keys = _preview_keys(data.get("keys"))
        doc = Document(title=_text(data.get("title"))[:MAX_TITLE_LEN], type=found.name if found and found.name in Document.Type.values else Document.Type.DOC.value)
        body, meta = _text(data.get("body")), _text(data.get("infobox"))

        try:
            if found is not None and found.page:
                body_html = mark_safe(markup.render(body, keys, "body"))
            else:
                body_html = mark_safe(f"<pre style=\"white-space:pre-wrap;font:13px/1.5 monospace\">{escape(body)}</pre>")
            infobox_html = mark_safe(markup.render(meta, keys, "infobox"))
            page_body = render_to_string("wiki/document.html", {"doc": doc, "body_html": body_html})
            page_meta = render_to_string("wiki/infobox.html", {"doc": doc, "infobox_html": infobox_html})
        except Exception as exc:                                              # предпросмотр не должен ронять админку
            logger.exception("Ошибка предпросмотра объекта")
            return _error(f"{type(exc).__name__}: {exc}"[:300], 500)

        return JsonResponse({"ok": True, "body": page_body, "infobox": page_meta, "issues": _lint_fields({"body": body, "infobox": meta})})
