"""История версий записи в админке.

Подключается к DocumentAdmin примесью:

    class DocumentAdmin(DocumentRevisionsMixin, admin.ModelAdmin): ...

Адреса (относительно списка записей):
    <id>/revisions/                список версий
    <id>/revisions/<rev>/          что изменила версия; POST откатывает запись

Откат не стирает историю: восстановленный текст сохраняется как новая версия.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .models import DocumentRevision
from .revisions import SNAPSHOT_FIELDS, compare


class DocumentRevisionsMixin:
    def _revision_url(self, name, *args):
        opts = self.model._meta
        return reverse(
            f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_{name}",
            args=args,
        )

    def get_urls(self):
        opts = self.model._meta
        prefix = f"{opts.app_label}_{opts.model_name}"
        custom = [
            path(
                "<path:object_id>/revisions/",
                self.admin_site.admin_view(self.revisions_view),
                name=f"{prefix}_revisions",
            ),
            path(
                "<path:object_id>/revisions/<int:revision_id>/",
                self.admin_site.admin_view(self.revision_view),
                name=f"{prefix}_revision",
            ),
        ]
        # раньше стандартных: иначе revisions/ примется за часть id записи
        return custom + super().get_urls()

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if change and obj is not None:
            context["revisions_url"] = self._revision_url("revisions", obj.pk)
        return super().render_change_form(request, context, add, change, form_url, obj)

    def _page_context(self, request, obj, title, **extra):
        return {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": title,
            "change_url": reverse(
                f"{self.admin_site.name}:{self.model._meta.app_label}_"
                f"{self.model._meta.model_name}_change",
                args=[obj.pk],
            ),
            **extra,
        }

    def _get_document(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def revisions_view(self, request, object_id):
        obj = self._get_document(request, object_id)
        revisions = list(
            DocumentRevision.objects.filter(document=obj)
            .select_related("saved_by")
            .order_by("-saved_at", "-id")
        )
        # что изменила каждая версия, считается относительно предыдущей
        for newer, older in zip(revisions, revisions[1:]):
            newer.changed = [f for f in SNAPSHOT_FIELDS if getattr(newer, f) != getattr(older, f)]
        if revisions:
            revisions[-1].changed = ["создана"]
        for rev in revisions:
            rev.url = self._revision_url("revision", obj.pk, rev.pk)
        context = self._page_context(
            request, obj, f"История: {obj}", revisions=revisions
        )
        return TemplateResponse(request, "admin/wiki/document/revisions.html", context)

    def revision_view(self, request, object_id, revision_id):
        obj = self._get_document(request, object_id)
        revision = get_object_or_404(DocumentRevision, pk=revision_id, document=obj)

        if request.method == "POST":
            return self._restore(request, obj, revision)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET", "POST"])

        against = request.GET.get("against")
        if against == "current":
            base, target = revision, obj
            heading = "Версия → текущая запись"
        else:
            base = (
                DocumentRevision.objects.filter(document=obj)
                .filter(pk__lt=revision.pk)
                .order_by("-pk")
                .first()
            )
            target = revision
            heading = "Предыдущая версия → эта версия" if base else "Первая версия"

        diff = compare(base, target) if base is not None else None
        context = self._page_context(
            request,
            obj,
            f"Версия от {revision.saved_at:%d.%m.%Y %H:%M}",
            revision=revision,
            heading=heading,
            diff=diff,
            against_current=against == "current",
            can_restore=self.has_change_permission(request, obj),
            list_url=self._revision_url("revisions", obj.pk),
            self_url=self._revision_url("revision", obj.pk, revision.pk),
        )
        return TemplateResponse(request, "admin/wiki/document/revision.html", context)

    def _restore(self, request, obj, revision):
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        for name in SNAPSHOT_FIELDS:
            setattr(obj, name, getattr(revision, name))
        obj.updated_by = request.user
        try:
            with transaction.atomic():
                obj.full_clean(exclude=["created_by", "updated_by"])
                obj.save()
        except (ValidationError, IntegrityError) as exc:  # название могло стать занятым
            detail = "; ".join(getattr(exc, "messages", None) or [str(exc)])
            self.message_user(
                request, f"Не удалось восстановить версию: {detail}", level=messages.ERROR
            )
            return HttpResponseRedirect(self._revision_url("revision", obj.pk, revision.pk))
        self.message_user(
            request,
            f"Версия от {revision.saved_at:%d.%m.%Y %H:%M} восстановлена.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(self._revision_url("revisions", obj.pk))
