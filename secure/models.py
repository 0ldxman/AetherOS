"""Модели secure: сборка ключа из частей. Сами ключи — объекты формата key (filesystem), реестр в secure/keys.py."""
from django.db import models


class KeyRecipe(models.Model):
    """Ключ, который игрок собирает из частей командой kjoin (secure/recipes.py). Части — обычные ключи."""

    result = models.OneToOneField("filesystem.Item", on_delete=models.CASCADE, related_name="recipe", limit_choices_to={"format": "key"})
    consume = models.BooleanField("Части расходуются", default=False, help_text="После сборки файлы частей пропадают из секретов игрока.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сборка ключа"
        verbose_name_plural = "Сборки ключей"

    def __str__(self):
        return f"{self.result.slug} из частей"


class KeyPart(models.Model):
    recipe = models.ForeignKey(KeyRecipe, on_delete=models.CASCADE, related_name="parts")
    item = models.ForeignKey("filesystem.Item", on_delete=models.CASCADE, related_name="part_of", limit_choices_to={"format": "key"})
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = [models.UniqueConstraint(fields=("recipe", "item"), name="unique_key_part")]
