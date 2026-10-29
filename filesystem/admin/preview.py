"""Предпросмотр объекта в админке: тот же редактор и рендер, что у окна документа (documents.editor), поля объекта вместо полей записи.

Редактор документа ищет поля формы по id (title, type, body, infobox); у объекта они называются name, format, body, meta, и
filesystem/static/filesystem/item_admin.js переименовывает их до запуска редактора. Для форматов, которые умеют быть страницей вики
(FileFormat.markup), текст рендерится разметкой вики; остальные показываются как есть.
"""
import json
import logging

from django.http import HttpResponseNotAllowed, JsonResponse

from documents.editor import MAX_REQUEST_BYTES, DocumentPreviewMixin, _error, _preview_keys, _text, render_preview

from filesystem.models import KEY_FORMAT, FileFormat, Item

logger = logging.getLogger(__name__)


def format_table():
    """Формат -> что вводится и страница ли это; редактор переключает поля содержимого по этой таблице."""
    return {
        found.name: {"content": found.content, "markup": found.markup, "title": found.title}
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
        if obj is not None and obj.format == KEY_FORMAT:
            from secure.usage import key_usage

            data["key_usage"] = key_usage(obj.slug)
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

        try:
            found = render_preview(
                _text(data.get("type")), _text(data.get("title")), _text(data.get("body")), _text(data.get("infobox")),
                _preview_keys(data.get("keys")),
            )
        except Exception as exc:                                              # предпросмотр не должен ронять админку
            logger.exception("Ошибка предпросмотра объекта")
            return _error(f"{type(exc).__name__}: {exc}"[:300], 500)

        return JsonResponse({"ok": True, **found})
