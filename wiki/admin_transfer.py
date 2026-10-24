"""Экспорт и импорт записей в админке (формат и правила: wiki/transfer.py).

    class DocumentAdmin(DocumentTransferMixin, admin.ModelAdmin): ...

Адреса (относительно списка записей):
    export/            весь архив; ?ns=<id раздела> или ?ns=root: только этот раздел с вложенными
    import/            загрузка архива и сухой прогон (POST); показывает, что изменится
    import/<id>/apply/ подтверждение (POST): тот же код, но без отката

Действие «Экспортировать выбранные в ZIP» есть и в списке записей.
"""
from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from . import transfer
from .models import Document, ImportBatch, Namespace

BATCH_TTL = timedelta(days=1)
ERRORS_IN_MESSAGE = 5


class DocumentTransferMixin:
    def _t_name(self, suffix):
        opts = self.model._meta
        return f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_{suffix}"

    def get_urls(self):
        opts = self.model._meta
        prefix = f"{opts.app_label}_{opts.model_name}"
        custom = [
            path("export/", self.admin_site.admin_view(self.export_view), name=f"{prefix}_export"),
            path("import/", self.admin_site.admin_view(self.import_view), name=f"{prefix}_import"),
            path(
                "import/<uuid:batch_id>/apply/",
                self.admin_site.admin_view(self.import_apply_view),
                name=f"{prefix}_import_apply",
            ),
        ]
        # раньше стандартных: иначе export/ и import/ примутся за id записи
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        export_url = reverse(self._t_name("export"))
        section = request.GET.get("ns")
        if section and (section == "root" or section.isdigit()):
            export_url += f"?ns={section}"
        extra_context["export_url"] = export_url
        if self._can_import(request):
            extra_context["import_url"] = reverse(self._t_name("import"))
        return super().changelist_view(request, extra_context)

    def _can_import(self, request):
        return self.has_add_permission(request) and self.has_change_permission(request)

    # ---------- экспорт ----------

    def _zip_response(self, documents, namespaces):
        data = transfer.build_archive(list(documents), list(namespaces))
        name = f"wiki-{timezone.localtime():%Y%m%d-%H%M}.zip"
        response = HttpResponse(data, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    def export_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        section = request.GET.get("ns")
        if section == "root":
            return self._zip_response(Document.objects.filter(namespace__isnull=True), [])
        if section and section.isdigit():
            ids = transfer.subtree_ids(int(section))
            return self._zip_response(
                Document.objects.filter(namespace_id__in=ids),
                Namespace.objects.filter(pk__in=ids),
            )
        return self._zip_response(Document.objects.all(), Namespace.objects.all())

    @admin.action(description="Экспортировать выбранные в ZIP")
    def export_selected(self, request, queryset):
        return self._zip_response(queryset, [])

    # ---------- импорт ----------

    def _import_context(self, request, **extra):
        opts = self.model._meta
        return {
            **self.admin_site.each_context(request),
            "opts": opts,
            "title": "Импорт записей",
            "list_url": reverse(self._t_name("changelist")),
            "max_mb": transfer.MAX_ARCHIVE_BYTES // 1024 // 1024,
            **extra,
        }

    def import_view(self, request):
        if not self._can_import(request):
            raise PermissionDenied
        context = self._import_context(request)

        if request.method == "POST":
            upload = request.FILES.get("archive")
            if upload is None:
                context["error"] = "Выберите файл."
            elif upload.size > transfer.MAX_ARCHIVE_BYTES:
                context["error"] = f"Файл больше {context['max_mb']} МБ."
            else:
                data = upload.read()
                try:
                    archive = transfer.read_archive(data, upload.name)
                except transfer.ArchiveError as exc:
                    context["error"] = str(exc)
                else:
                    ImportBatch.objects.filter(created_at__lt=timezone.now() - BATCH_TTL).delete()
                    batch = ImportBatch.objects.create(
                        user=request.user, filename=upload.name[:255], data=data
                    )
                    rows = transfer.run(archive, request.user, commit=False)
                    counts = transfer.summary(rows)
                    context.update(
                        rows=[r for r in rows if r.action != "same"],
                        counts=counts,
                        notes=archive.notes,
                        batch=batch,
                        apply_url=reverse(self._t_name("import_apply"), args=[batch.pk]),
                        can_apply=bool(counts["create"] or counts["update"]),
                    )
        elif request.method != "GET":
            return HttpResponseNotAllowed(["GET", "POST"])

        return TemplateResponse(request, "admin/wiki/document/import.html", context)

    def import_apply_view(self, request, batch_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self._can_import(request):
            raise PermissionDenied
        batch = get_object_or_404(ImportBatch, pk=batch_id, user=request.user)
        archive = transfer.read_archive(bytes(batch.data), batch.filename)
        rows = transfer.run(archive, request.user, commit=True)
        batch.delete()

        counts = transfer.summary(rows)
        self.message_user(
            request,
            "Импорт завершён: создано {create}, обновлено {update}, "
            "без изменений {same}, с ошибками {error}.".format(**counts),
            messages.SUCCESS if not counts["error"] else messages.WARNING,
        )
        failed = [r for r in rows if r.action == "error"]
        for row in failed[:ERRORS_IN_MESSAGE]:
            self.message_user(
                request, f"Не записано {row.path}: {'; '.join(row.errors)}", messages.WARNING
            )
        if len(failed) > ERRORS_IN_MESSAGE:
            self.message_user(
                request, f"…и ещё записей с ошибками: {len(failed) - ERRORS_IN_MESSAGE}.", messages.WARNING
            )
        return HttpResponseRedirect(reverse(self._t_name("changelist")))
