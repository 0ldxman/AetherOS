"""Защита от потери правок при совместной работе над записью.

Подключается к DocumentAdmin примесью (вместе с форм-классом):

    class DocumentAdmin(DocumentLocksMixin, admin.ModelAdmin): ...

Два уровня:
- мягкая блокировка: страница редактора раз в несколько секунд сообщает,
  что запись открыта (lock/), и показывает, если её правит кто-то ещё;
  при закрытии страницы блокировка снимается (unlock/);
- проверка версии при сохранении: форма помнит updated_at записи на момент
  открытия. Если запись успели изменить, сохранение не проходит; форма
  возвращается с текстом автора и ссылкой на то, что изменилось. Повторное
  «Сохранить» заменяет чужие правки осознанно (в истории версий они остаются).
"""
from django import forms
from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html

from . import locks
from .models import Document, DocumentRevision


class VersionedDocumentForm(forms.ModelForm):
    base_version = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Document
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.initial["base_version"] = self.instance.updated_at.isoformat()

    def clean(self):
        cleaned = super().clean()
        base = cleaned.get("base_version")
        if not (self.instance.pk and base):
            return cleaned

        current = (
            Document.objects.filter(pk=self.instance.pk)
            .values("updated_at", "updated_by__username")
            .first()
        )
        if current is None or current["updated_at"].isoformat() == base:
            return cleaned

        # возвращаем форму с новой версией: повторное сохранение будет осознанным
        data = self.data.copy()
        data["base_version"] = current["updated_at"].isoformat()
        self.data = data

        when = date_format(timezone.localtime(current["updated_at"]), "d.m.Y H:i")
        who = current["updated_by__username"] or "кто-то"
        latest = (
            DocumentRevision.objects.filter(document=self.instance)
            .order_by("-saved_at", "-id")
            .first()
        )
        link = ""
        if latest is not None:
            link = format_html(
                ' <a href="{}" target="_blank" rel="noopener">Что изменилось</a>.',
                reverse(
                    "admin:wiki_document_revision",
                    args=[self.instance.pk, latest.pk],
                ),
            )
        raise ValidationError(
            format_html(
                "Запись изменена после того, как вы её открыли ({}, {}).{} "
                "Ваш текст сохранён в форме: если нажать «Сохранить» ещё раз, "
                "он заменит чужие правки (в истории версий они останутся).",
                who, when, link,
            )
        )


class DocumentLocksMixin:
    form = VersionedDocumentForm

    def _lock_url(self, name, *args):
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
                "<path:object_id>/lock/",
                self.admin_site.admin_view(self.lock_view),
                name=f"{prefix}_lock",
            ),
            path(
                "<path:object_id>/unlock/",
                self.admin_site.admin_view(self.unlock_view),
                name=f"{prefix}_unlock",
            ),
        ]
        return custom + super().get_urls()

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if change and obj is not None:
            context["lock_url"] = self._lock_url("lock", obj.pk)
            context["unlock_url"] = self._lock_url("unlock", obj.pk)
            context["lock_interval_ms"] = locks.HEARTBEAT_SECONDS * 1000
        return super().render_change_form(request, context, add, change, form_url, obj)

    def _editable(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_change_permission(request, obj):
            return None
        return obj

    def lock_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = self._editable(request, object_id)
        if obj is None:
            return JsonResponse({"ok": False}, status=403)
        other = locks.acquire(obj, request.user)
        if other is None:
            return JsonResponse({"ok": True, "holder": None})
        since = timezone.localtime(other.acquired_at)
        return JsonResponse(
            {
                "ok": True,
                "holder": {
                    "name": other.user.get_username(),
                    "since": date_format(since, "H:i"),
                },
            }
        )

    def unlock_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = self._editable(request, object_id)
        if obj is not None:
            locks.release(obj, request.user)
        return JsonResponse({"ok": True})

    @admin.display(description="Правит сейчас")
    def editing(self, obj):
        try:
            lock = obj.lock
        except ObjectDoesNotExist:
            return "—"
        return lock.user.get_username() if locks.is_active(lock, timezone.now()) else "—"
