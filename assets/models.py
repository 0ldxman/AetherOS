from django.db import models
import uuid


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

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Public ID",
    )

    class ViewerType(models.TextChoices):
        AUTO = "AUTO", "Auto"
        AUDIO = "AUDIO", "Audio"
        VIDEO = "VIDEO", "Video"
        TEXT = "TEXT", "Text"
        IMAGE = "IMAGE", "Image"
        PDF = "PDF", "PDF"
        RAW = "RAW", "Raw file"

    viewer_type = models.CharField(
        max_length=16,
        choices=ViewerType.choices,
        default=ViewerType.AUTO,
        verbose_name="Viewer type",
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