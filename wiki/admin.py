from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.template.response import TemplateResponse
from django.utils.html import format_html

from .admin_preview import DocumentPreviewMixin
from .admin_revisions import DocumentRevisionsMixin
from .models import Document, Namespace
from .views import _doc_url


def _chain_names(namespace):
    return " / ".join(n.name for n in namespace.chain()) if namespace else "~"


def _protection(obj):
    """Кратко: чем закрыта запись или раздел (сами условия, без цепочки родителей)."""
    marks = []
    if obj.access:
        marks.append("закрыта")
    if obj.visibility:
        marks.append("скрыта")
    return " · ".join(marks) or "—"


# =========================================================
# Фильтры
# =========================================================

class NamespaceTreeFilter(admin.SimpleListFilter):
    """Раздел вместе со всеми вложенными; список с отступами по глубине."""

    title = "раздел"
    parameter_name = "ns"

    def _tree(self):
        everything = list(Namespace.objects.all())
        children = {}
        for ns in everything:
            children.setdefault(ns.parent_id, []).append(ns)
        rows = []

        def walk(parent_id, depth):
            for ns in sorted(children.get(parent_id, []), key=lambda n: n.name):
                rows.append((ns, depth))
                walk(ns.pk, depth + 1)

        walk(None, 0)
        return rows, children

    def lookups(self, request, model_admin):
        rows, _ = self._tree()
        return [("root", "~ (корень)")] + [
            (str(ns.pk), " " * depth + ns.name) for ns, depth in rows
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        if value == "root":
            return queryset.filter(namespace__isnull=True)
        _, children = self._tree()
        ids, stack = [], [int(value)]
        while stack:
            current = stack.pop()
            ids.append(current)
            stack.extend(n.pk for n in children.get(current, []))
        return queryset.filter(namespace_id__in=ids)


class ProtectionFilter(admin.SimpleListFilter):
    title = "защита"
    parameter_name = "protection"

    def lookups(self, request, model_admin):
        return [
            ("access", "Закрытые ключом"),
            ("hidden", "Скрытые ключом"),
            ("open", "Без условий"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "access":
            return queryset.exclude(access={})
        if value == "hidden":
            return queryset.exclude(visibility={})
        if value == "open":
            return queryset.filter(access={}, visibility={})
        return queryset


# =========================================================
# Массовые действия
# =========================================================

class MoveForm(forms.Form):
    namespace = forms.ModelChoiceField(
        Namespace.objects.all(),
        required=False,
        empty_label="~ (корень)",
        label="Новый раздел",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["namespace"].label_from_instance = lambda ns: ns.path().replace(":", " / ")


# =========================================================
# Админки
# =========================================================

@admin.register(Namespace)
class NamespaceAdmin(admin.ModelAdmin):
    list_display = ("path_display", "slug", "documents_count", "children_count", "protection")
    list_display_links = ("path_display",)
    search_fields = ("name", "slug")
    list_filter = ("parent", ProtectionFilter)
    list_select_related = ("parent__parent__parent",)
    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .annotate(
                _documents=Count("documents", distinct=True),
                _children=Count("children", distinct=True),
            )
        )

    @admin.display(description="Раздел", ordering="name")
    def path_display(self, obj):
        return _chain_names(obj)

    @admin.display(description="Записей", ordering="_documents")
    def documents_count(self, obj):
        return obj._documents

    @admin.display(description="Вложенных", ordering="_children")
    def children_count(self, obj):
        return obj._children

    @admin.display(description="Защита")
    def protection(self, obj):
        return _protection(obj)


@admin.register(Document)
class DocumentAdmin(DocumentRevisionsMixin, DocumentPreviewMixin, admin.ModelAdmin):
    list_display = ("title", "section", "type", "protection", "updated_at", "updated_by", "as_player")
    list_filter = (NamespaceTreeFilter, "type", ProtectionFilter)
    list_select_related = ("namespace__parent__parent__parent", "updated_by")
    search_fields = ("title", "body", "infobox")
    readonly_fields = ("created_at", "created_by", "updated_at", "updated_by")
    actions = ("move_to_namespace",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Раздел", ordering="namespace__name")
    def section(self, obj):
        return _chain_names(obj.namespace)

    @admin.display(description="Защита")
    def protection(self, obj):
        return _protection(obj)

    @admin.display(description="Открыть как игрок")
    def as_player(self, obj):
        url = _doc_url(obj)
        return format_html(
            '<a href="{0}?as=none" target="_blank" rel="noopener">без ключей</a>'
            " · "
            '<a href="{0}?as=all" target="_blank" rel="noopener">все ключи</a>',
            url,
        )

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if change and obj is not None:
            url = _doc_url(obj)
            context["player_links"] = [
                ("Как игрок без ключей", f"{url}?as=none"),
                ("Как игрок со всеми ключами", f"{url}?as=all"),
            ]
        return super().render_change_form(request, context, add, change, form_url, obj)

    @admin.action(description="Переместить в другой раздел…")
    def move_to_namespace(self, request, queryset):
        form = MoveForm(request.POST if "apply" in request.POST else None)
        if "apply" in request.POST and form.is_valid():
            target = form.cleaned_data["namespace"]
            moved, problems = 0, []
            for doc in queryset.select_related("namespace"):
                doc.namespace = target
                doc.updated_by = request.user
                try:
                    with transaction.atomic():
                        doc.full_clean(exclude=["created_by", "updated_by"])
                        doc.save()
                except (ValidationError, IntegrityError) as exc:
                    detail = "; ".join(getattr(exc, "messages", None) or [str(exc)])
                    problems.append(f"«{doc.title}»: {detail}")
                else:
                    moved += 1
            if moved:
                self.message_user(request, f"Перемещено записей: {moved}.", messages.SUCCESS)
            for problem in problems:
                self.message_user(request, f"Не перемещена {problem}", messages.WARNING)
            return None

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Переместить записи",
            "form": form,
            "documents": list(queryset.select_related("namespace")),
            "selected": request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME),
            "action_name": "move_to_namespace",
        }
        return TemplateResponse(request, "admin/wiki/document/move.html", context)
