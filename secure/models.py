from django.db import models

# Create your models here.
class Key(models.Model):
    slug = models.SlugField(
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("slug",)

    def __str__(self):
        return self.slug