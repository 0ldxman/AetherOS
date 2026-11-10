"""Команда авторов: роли с правами по разделам Студии (team.rights)."""
from django.core.exceptions import ValidationError
from django.db import models

from team import rights


class Role(models.Model):
    name = models.CharField("Название", max_length=64, unique=True)
    note = models.TextField("Заметка", blank=True)
    rights = models.JSONField("Права по разделам", default=dict, blank=True, help_text="{раздел: none|read|edit}")
    actions = models.JSONField("Действия", default=list, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Роль"
        verbose_name_plural = "Роли"

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        bad = [f"{section}={level}" for section, level in (self.rights or {}).items()
               if section not in rights.SECTIONS or level not in rights.LEVELS]
        if bad:
            errors["rights"] = "Неизвестные разделы или уровни: " + ", ".join(bad)
        unknown = [action for action in (self.actions or []) if action not in rights.ACTIONS]
        if unknown:
            errors["actions"] = "Неизвестные действия: " + ", ".join(unknown)
        if errors:
            raise ValidationError(errors)
