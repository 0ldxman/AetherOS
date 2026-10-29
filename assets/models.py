from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
import uuid


slug_validator = RegexValidator(
    regex=r"^[a-z0-9][a-z0-9_-]*$",
    message=(
        "Только строчные латинские буквы, цифры, «-» и «_»; "
        "начинаться нужно с буквы или цифры."
    ),
)


class Asset(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Asset name",
    )

    # Читаемый идентификатор для разметки: ::asset theme-01
    # Пусто = на ассет нельзя сослаться по slug (остаётся UUID).
    slug = models.CharField(
        max_length=64,
        blank=True,
        default="",
        validators=[slug_validator],
        verbose_name="Slug",
        help_text="Для ссылок из вики: ::asset slug",
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

    # Кэш метаданных файла из Nextcloud: вики-виджеты определяют
    # тип ассета без запроса в Nextcloud на каждый рендер.
    filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        editable=False,
        verbose_name="File name",
    )

    content_type = models.CharField(
        max_length=127,
        blank=True,
        default="",
        editable=False,
        verbose_name="Content type",
    )

    size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Size (bytes)",
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
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=~Q(slug=""),
                name="assets_asset_unique_slug",
            ),
        ]

    def __str__(self):
        return self.name

    def refresh_metadata(self, client=None):
        """Подтягивает filename / content_type / size из Nextcloud.

        Сам объект не сохраняет: это делает вызывающий код.
        Бросает ValueError, если файла нет или это папка.
        """
        from assets.nextcloud import NextcloudClient

        client = client or NextcloudClient.from_settings()
        file = client.get_file_by_id(self.file_id)

        if file is None or file.is_directory:
            raise ValueError("Файл в Nextcloud не найден.")

        self.apply_file(file)

    def apply_file(self, file):
        """Копирует метаданные из файла Nextcloud в кэш.

        Возвращает True, если что-то изменилось. Не сохраняет объект.
        """
        from assets.services import guess_content_type

        values = {
            "filename": file.filename,
            "content_type": guess_content_type(file.filename),
            "size": file.size,
        }
        changed = any(getattr(self, k) != v for k, v in values.items())
        for key, value in values.items():
            setattr(self, key, value)
        return changed