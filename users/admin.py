from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from wiki.key_usage import key_usage

from .models import Key, User, UserKey

HOLDERS_SHOWN = 50


class UserKeyInline(admin.TabularInline):
    model = UserKey
    extra = 0


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = [UserKeyInline]


class KeyHoldersForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        User.objects.order_by("username"),
        label="Пользователи",
        widget=forms.SelectMultiple(attrs={"size": 12}),
    )


@admin.register(Key)
class KeyAdmin(admin.ModelAdmin):
    list_display = ("slug", "description", "holders_count", "updated_at")
    search_fields = ("slug", "description")
    readonly_fields = ("holders_list", "usage")
    actions = ("grant", "revoke")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_holders=Count("userkey", distinct=True))

    @admin.display(description="Держателей", ordering="_holders")
    def holders_count(self, obj):
        return obj._holders

    @admin.display(description="Есть у")
    def holders_list(self, obj):
        if obj.pk is None:
            return "—"
        links = UserKey.objects.filter(key=obj).select_related("user").order_by("user__username")
        shown = list(links[:HOLDERS_SHOWN])
        if not shown:
            return "Ни у кого."
        html = format_html_join(
            ", ",
            '<a href="{}">{}</a>',
            (
                (reverse("admin:users_user_change", args=[link.user_id]), link.user)
                for link in shown
            ),
        )
        extra = links.count() - len(shown)
        return format_html("{} (и ещё {})", html, extra) if extra > 0 else html

    @admin.display(description="Где используется")
    def usage(self, obj):
        if obj.pk is None:
            return "—"
        documents, namespaces = key_usage(obj.slug)
        if not documents and not namespaces:
            return "Нигде: ни в условиях доступа, ни в тексте записей."
        rows = [
            (reverse("admin:wiki_document_change", args=[d.pk]), f"запись: {d.path()}")
            for d in documents
        ] + [
            (reverse("admin:wiki_namespace_change", args=[n.pk]), f"раздел: {n.path()}")
            for n in namespaces
        ]
        return format_html(
            "<ul>{}</ul>",
            format_html_join("", '<li><a href="{}">{}</a></li>', rows),
        )

    def _choose_users(self, request, queryset, action, title):
        form = KeyHoldersForm(request.POST if "apply" in request.POST else None)
        if "apply" in request.POST and form.is_valid():
            users = form.cleaned_data["users"]
            if action == "grant":
                have = set(
                    UserKey.objects.filter(key__in=queryset, user__in=users)
                    .values_list("user_id", "key_id")
                )
                new = [
                    UserKey(user=u, key=k)
                    for k in queryset for u in users
                    if (u.pk, k.pk) not in have
                ]
                UserKey.objects.bulk_create(new)
                self.message_user(request, f"Выдано ключей: {len(new)}.", messages.SUCCESS)
            else:
                deleted, _ = UserKey.objects.filter(key__in=queryset, user__in=users).delete()
                self.message_user(request, f"Забрано ключей: {deleted}.", messages.SUCCESS)
            return None

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": title,
            "form": form,
            "keys": list(queryset),
            "selected": request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME),
            "action_name": action,
        }
        return TemplateResponse(request, "admin/users/key/choose_users.html", context)

    @admin.action(description="Выдать выбранные ключи пользователям…")
    def grant(self, request, queryset):
        return self._choose_users(request, queryset, "grant", "Выдать ключи")

    @admin.action(description="Забрать выбранные ключи у пользователей…")
    def revoke(self, request, queryset):
        return self._choose_users(request, queryset, "revoke", "Забрать ключи")
