"""Страница «Сводка автора» в админке записей: wiki/dashboard.py.

    class DocumentAdmin(DocumentDashboardMixin, admin.ModelAdmin): ...

Адрес: <список записей>/dashboard/; ссылка на неё стоит в шапке списка.
"""
from django.template.response import TemplateResponse
from django.urls import path, reverse

from . import dashboard


class DocumentDashboardMixin:
    change_list_template = "admin/wiki/document/change_list.html"

    def _dashboard_name(self):
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_dashboard"

    def get_urls(self):
        custom = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name=self._dashboard_name(),
            ),
        ]
        # раньше стандартных: иначе dashboard/ примется за id записи
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["dashboard_url"] = reverse(
            f"{self.admin_site.name}:{self._dashboard_name()}"
        )
        return super().changelist_view(request, extra_context)

    def dashboard_view(self, request):
        if not self.has_view_or_change_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        opts = self.model._meta
        context = {
            **self.admin_site.each_context(request),
            "opts": opts,
            "title": "Сводка автора",
            "data": dashboard.build(),
            "limit": dashboard.LIST_LIMIT,
            "list_url": reverse(f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_changelist"),
        }
        return TemplateResponse(request, "admin/wiki/document/dashboard.html", context)
