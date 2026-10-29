"""Версии и блокировка объекта в админке (вики делала то же для записей).

    class ItemAdmin(ItemHistoryMixin, admin.ModelAdmin): ...

Адреса (относительно списка объектов):
    <id>/revisions/             список версий
    <id>/revisions/<rev>/       что изменила версия; POST откатывает объект (откат не стирает историю)
    <id>/lock/, <id>/unlock/    мягкая блокировка на время правки (раз в несколько секунд подтверждается страницей)

Защита от потери правок: форма помнит updated_at на момент открытия. Если объект успели изменить, сохранение не проходит;
форма возвращается с текстом автора и ссылкой на то, что изменилось. Повторное «Сохранить» заменяет чужие правки осознанно.
"""
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html

from filesystem import history
from filesystem.models import Item, ItemRevision


class VersionedFormMixin(forms.ModelForm):
    """Форма объекта, которая помнит версию, с которой её открыли."""

    base_version = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.initial["base_version"] = self.instance.updated_at.isoformat()

    def clean(self):
        cleaned = super().clean()
        base = cleaned.get("base_version")
        if not (self.instance.pk and base):
            return cleaned

        current = Item.objects.filter(pk=self.instance.pk).values("updated_at", "updated_by__username").first()
        if current is None or current["updated_at"].isoformat() == base:
            return cleaned

        data = self.data.copy()                                    # форма возвращается с новой версией: повторное сохранение осознанное
        data["base_version"] = current["updated_at"].isoformat()
        self.data = data

        when = date_format(timezone.localtime(current["updated_at"]), "d.m.Y H:i")
        who = current["updated_by__username"] or "кто-то"
        latest = ItemRevision.objects.filter(item=self.instance).first()
        link = ""
        if latest is not None:
            link = format_html(
                ' <a href="{}" target="_blank" rel="noopener">Что изменилось</a>.',
                reverse("admin:filesystem_item_revision", args=[self.instance.pk, latest.pk]),
            )
        raise ValidationError(format_html(
            "Объект изменён после того, как вы его открыли ({}, {}).{} Ваш текст сохранён в форме: если нажать «Сохранить» ещё раз, "
            "он заменит чужие правки (в истории версий они останутся).", who, when, link,
        ))


class ItemHistoryMixin:
    def _url(self, name, *args):
        opts = self.model._meta
        return reverse(f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_{name}", args=args)

    def get_urls(self):
        prefix = f"{self.model._meta.app_label}_{self.model._meta.model_name}"
        custom = [
            path("<path:object_id>/revisions/", self.admin_site.admin_view(self.revisions_view), name=f"{prefix}_revisions"),
            path("<path:object_id>/revisions/<int:revision_id>/", self.admin_site.admin_view(self.revision_view), name=f"{prefix}_revision"),
            path("<path:object_id>/lock/", self.admin_site.admin_view(self.lock_view), name=f"{prefix}_lock"),
            path("<path:object_id>/unlock/", self.admin_site.admin_view(self.unlock_view), name=f"{prefix}_unlock"),
        ]
        return custom + super().get_urls()                          # раньше стандартных: иначе revisions/ примется за часть id

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        response = super().render_change_form(request, context, add, change, form_url, obj)
        if change and obj is not None:
            data = response.context_data
            data["revisions_url"] = self._url("revisions", obj.pk)
            data["lock_url"] = self._url("lock", obj.pk)
            data["unlock_url"] = self._url("unlock", obj.pk)
            data["lock_interval_ms"] = history.HEARTBEAT_SECONDS * 1000
        return response

    # ---- версии ---------------------------------------------------------------------------------------------------

    def _page(self, request, obj, title, **extra):
        return {
            **self.admin_site.each_context(request), "opts": self.model._meta, "original": obj, "title": title,
            "change_url": self._url("change", obj.pk), "labels": history.LABELS, **extra,
        }

    def _object(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def revisions_view(self, request, object_id):
        obj = self._object(request, object_id)
        revisions = list(ItemRevision.objects.filter(item=obj).select_related("saved_by"))
        for newer, older in zip(revisions, revisions[1:]):             # что изменила версия, считается относительно предыдущей
            newer.changed = [history.LABELS[f] for f in history.SNAPSHOT_FIELDS if getattr(newer, f) != getattr(older, f)]
        if revisions:
            revisions[-1].changed = ["создана"]
        for revision in revisions:
            revision.url = self._url("revision", obj.pk, revision.pk)
        return TemplateResponse(request, "admin/filesystem/item/revisions.html", self._page(request, obj, f"История: {obj}", revisions=revisions))

    def revision_view(self, request, object_id, revision_id):
        obj = self._object(request, object_id)
        revision = get_object_or_404(ItemRevision, pk=revision_id, item=obj)
        if request.method == "POST":
            return self._restore(request, obj, revision)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET", "POST"])

        if request.GET.get("against") == "current":
            base, target, heading = revision, obj, "Версия → текущий объект"
        else:
            base = ItemRevision.objects.filter(item=obj, pk__lt=revision.pk).order_by("-pk").first()
            target = revision
            heading = "Предыдущая версия → эта версия" if base else "Первая версия"

        diff = history.compare(base, target) if base is not None else None
        return TemplateResponse(request, "admin/filesystem/item/revision.html", self._page(
            request, obj, f"Версия от {revision.saved_at:%d.%m.%Y %H:%M}", revision=revision, heading=heading, diff=diff,
            against_current=request.GET.get("against") == "current", can_restore=self.has_change_permission(request, obj),
            list_url=self._url("revisions", obj.pk), self_url=self._url("revision", obj.pk, revision.pk),
        ))

    def _restore(self, request, obj, revision):
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        for name in history.SNAPSHOT_FIELDS:
            setattr(obj, name, getattr(revision, name))
        obj.updated_by = request.user
        try:
            with transaction.atomic():
                obj.full_clean(exclude=["created_by", "updated_by"])
                obj.save()
        except (ValidationError, IntegrityError) as exc:
            detail = "; ".join(getattr(exc, "messages", None) or [str(exc)])
            self.message_user(request, f"Не удалось восстановить версию: {detail}", level=messages.ERROR)
            return HttpResponseRedirect(self._url("revision", obj.pk, revision.pk))
        self.message_user(request, f"Версия от {revision.saved_at:%d.%m.%Y %H:%M} восстановлена.", level=messages.SUCCESS)
        return HttpResponseRedirect(self._url("revisions", obj.pk))

    # ---- блокировка -----------------------------------------------------------------------------------------------

    def _editable(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        return obj if self.has_change_permission(request, obj) else None

    def lock_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = self._editable(request, object_id)
        if obj is None:
            return JsonResponse({"ok": False}, status=403)
        other = history.acquire(obj, request.user)
        if other is None:
            return JsonResponse({"ok": True, "holder": None})
        since = timezone.localtime(other.acquired_at)
        return JsonResponse({"ok": True, "holder": {"name": other.user.get_username(), "since": date_format(since, "H:i")}})

    def unlock_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = self._editable(request, object_id)
        if obj is not None:
            history.release(obj, request.user)
        return JsonResponse({"ok": True})

    @admin.display(description="Правит сейчас")
    def editing(self, obj):
        try:
            lock = obj.lock
        except ObjectDoesNotExist:
            return "—"
        return lock.user.get_username() if history.is_active(lock, timezone.now()) else "—"
