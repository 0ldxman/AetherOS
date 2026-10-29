from django.core.exceptions import ValidationError
from django.db import models


class SceneScript(models.Model):
    """Сцена, написанная в студии: текст на языке сцен (scenes/script.py). Привязывается к событиям ОС (SystemScene) и вставляется
    в другие сцены (@include слаг)."""

    slug = models.SlugField("Слаг", max_length=64, unique=True, help_text="По нему сцену вставляют: @include слаг.")
    title = models.CharField("Название", max_length=128, blank=True)
    body = models.TextField("Текст сцены", blank=True)
    note = models.TextField("Заметка", blank=True, help_text="Для себя: что это и где используется.")

    class Meta:
        ordering = ("slug",)
        verbose_name = "Сцена"
        verbose_name_plural = "Сцены"

    def __str__(self):
        return self.title or self.slug

    def problems(self, names):
        """Ошибки текста: [(номер строки, текст)]. names: какие подстановки разрешены."""
        from scenes.script import check_script

        return check_script(self.body, names, resolve_script)

    def clean(self):
        super().clean()
        from machines.world.slots import all_params

        found = self.problems(all_params())
        if found:
            raise ValidationError({"body": [f"Строка {number}: {text}" for number, text in found]})


def resolve_script(slug):
    """Текст сцены по слагу (для @include) или None."""
    return SceneScript.objects.filter(slug=slug).values_list("body", flat=True).first()


class SystemScene(models.Model):
    """Какая сцена играется у ОС вместо встроенной на событии (слот, например bridge.connect). Нет записи: встроенная."""

    system_type = models.ForeignKey("machines.SystemType", on_delete=models.CASCADE, related_name="scenes")
    slot = models.CharField("Событие", max_length=32)
    script = models.ForeignKey(SceneScript, on_delete=models.CASCADE, related_name="bindings", verbose_name="Сцена")

    class Meta:
        ordering = ("system_type", "slot")
        verbose_name = "Сцена ОС"
        verbose_name_plural = "Сцены ОС"
        constraints = [models.UniqueConstraint(fields=("system_type", "slot"), name="unique_system_scene")]

    def __str__(self):
        return f"{self.system_type.code}: {self.slot} = {self.script.slug}"

    def clean(self):
        super().clean()
        from machines.world.slots import SLOTS

        if self.slot not in SLOTS:
            raise ValidationError({"slot": "Нет такого события."})
        found = self.script.problems(SLOTS[self.slot].params)
        if found:
            raise ValidationError({"script": [f"Сцена не подходит событию «{SLOTS[self.slot].label}»: строка {n}: {t}" for n, t in found]})
