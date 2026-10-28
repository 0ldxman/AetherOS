"""Файловый менеджер в админке: том и машина редактируются деревом и списком, как в проводнике.

Страница одна на оба случая (admin/filesystem/filemanager.html + static filemanager.js). Данные и операции идут по JSON:
    GET  .../files/data/    всё дерево
    POST .../files/op/      {"op": "...", ...}, ответ {"ok": true, ...} или {"ok": false, "error": "текст"}
    GET  .../files/objects/?q=   поиск объектов для «положить существующий»
"""
import json

from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.csrf import ensure_csrf_cookie

from filesystem import filemanager, overlay
from filesystem.filemanager import FileManagerError
from filesystem.models import Item

MAX_BODY = 100_000


def parse_body(request):
    try:
        body = json.loads(request.body[:MAX_BODY] or b"{}")
    except ValueError:
        raise FileManagerError("Некорректный запрос.")
    if not isinstance(body, dict):
        raise FileManagerError("Некорректный запрос.")
    return body


def answer(handler):
    try:
        return JsonResponse({"ok": True, **(handler() or {})})
    except FileManagerError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


def ids_of(body):
    ids = body.get("ids")
    if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
        raise FileManagerError("Ничего не выбрано.")
    return ids


class FileManagerMixin:
    """Подмешивается в ModelAdmin: страница менеджера, данные и операции. Наследник задаёт data_for, run и config_for."""

    files_name = ""

    def _url(self, suffix):
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_{suffix}"

    def get_urls(self):
        custom = [
            path("<int:pk>/files/", self.admin_site.admin_view(ensure_csrf_cookie(self.files_page)), name=self._url("files")),
            path("<int:pk>/files/data/", self.admin_site.admin_view(self.files_data), name=self._url("files_data")),
            path("<int:pk>/files/op/", self.admin_site.admin_view(self.files_op), name=self._url("files_op")),
            path("files/objects/", self.admin_site.admin_view(self.files_objects), name=self._url("files_objects")),
        ]
        return custom + super().get_urls()

    def _object(self, request, pk):
        found = self.get_object(request, str(pk))
        if found is None or not self.has_view_or_change_permission(request, found):
            raise Http404
        return found

    def files_page(self, request, pk):
        found = self._object(request, pk)
        name = self.admin_site.name
        config = {
            "mode": self.files_name,
            "title": str(found),
            "dataUrl": reverse(f"{name}:{self._url('files_data')}", args=[pk]),
            "opUrl": reverse(f"{name}:{self._url('files_op')}", args=[pk]),
            "objectsUrl": reverse(f"{name}:{self._url('files_objects')}"),
            "itemUrl": reverse("admin:filesystem_item_change", args=[0]).replace("/0/", "/__id__/"),
            "newItemUrl": reverse("admin:filesystem_item_add"),
            "canChange": self.has_change_permission(request, found),
            **self.config_for(found),
        }
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Файлы: {found}",
            "object": found,
            "config": config,
            "change_url": reverse(f"{name}:{self._url('change')}", args=[pk]),
            "list_url": reverse(f"{name}:{self._url('changelist')}"),
        }
        return TemplateResponse(request, "admin/filesystem/filemanager.html", context)

    def files_data(self, request, pk):
        found = self._object(request, pk)
        return JsonResponse({"ok": True, **self.data_for(found)})

    def files_op(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        found = self._object(request, pk)
        if not self.has_change_permission(request, found):
            return JsonResponse({"ok": False, "error": "Нет прав на изменение."}, status=403)

        def work():
            body = parse_body(request)
            return self.run(found, body.pop("op", ""), body)

        return answer(work)

    def files_objects(self, request):
        if not self.has_view_or_change_permission(request):
            raise Http404
        query = request.GET.get("q", "").strip()[:100]
        found = Item.objects.order_by("name")
        if query:
            from django.db.models import Q

            found = found.filter(Q(name__icontains=query) | Q(slug__icontains=query))
        return JsonResponse({"ok": True, "items": [
            {"id": item.pk, "slug": item.slug, "name": item.name, "format": item.format} for item in found[:30]
        ]})


class VolumeFiles(FileManagerMixin):
    files_name = "volume"

    def data_for(self, volume):
        return {**filemanager.data(volume), "formats": filemanager.formats()}

    def config_for(self, volume):
        return {"rootName": volume.name or volume.label or volume.slug, "formats": filemanager.formats()}

    def run(self, volume, op, body):
        if op == "new_folder":
            filemanager.new_folder(volume, body.get("parent"), body.get("name"))
        elif op == "new_file":
            placement = filemanager.new_file(volume, body.get("parent"), body.get("name"), body.get("format") or "")
            return {"item": placement.item_id}
        elif op == "link":
            filemanager.link(volume, body.get("parent"), body.get("item"), body.get("name") or "")
        elif op == "rename":
            filemanager.rename(volume, body.get("id"), body.get("name"))
        elif op == "delete":
            return {"count": filemanager.delete(volume, ids_of(body))}
        elif op == "move":
            return {"count": filemanager.move(volume, ids_of(body), body.get("parent"))}
        elif op == "copy":
            return {"count": filemanager.copy(volume, ids_of(body), body.get("parent"))}
        elif op == "set":
            filemanager.set_flags(volume, body.get("id"), **{key: body[key] for key in ("hidden", "system") if key in body})
        else:
            raise FileManagerError("Неизвестная операция.")


class MachineFiles(FileManagerMixin):
    files_name = "machine"

    def data_for(self, machine):
        return {**overlay.machine_data(machine), "formats": filemanager.formats()}

    def config_for(self, machine):
        return {"rootName": machine.label, "formats": filemanager.formats()}

    def run(self, machine, op, body):
        if op == "new_folder":
            overlay.new_folder(machine, body.get("parent") or "/", body.get("name"))
        elif op == "new_file":
            placement = overlay.new_file(machine, body.get("parent") or "/", body.get("name"), body.get("format") or "")
            return {"item": placement.item_id}
        elif op == "override":
            return {"item": overlay.override(machine, body.get("path") or "").pk}
        elif op == "delete":
            overlay.delete(machine, body.get("path") or "")
        elif op == "restore":
            overlay.restore(machine, body.get("path") or "")
        elif op == "reset":
            overlay.reset(machine, body.get("path") or "")
        elif op == "rename":
            overlay.rename(machine, body.get("path") or "", body.get("name"))
        else:
            raise FileManagerError("Неизвестная операция.")
