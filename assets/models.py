from django.db import models


class Asset(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Asset name",
    )

    file_id = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nextcloud file ID",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Asset"
        verbose_name_plural = "Assets"

    def __str__(self):
        return self.name