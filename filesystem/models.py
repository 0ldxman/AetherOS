from django.db import models


class MachineFile(models.Model):
    class FileType(models.TextChoices):
        FILE = "FILE", "File"
        DIRECTORY = "DIRECTORY", "Directory"

    id = models.BigAutoField(
        primary_key=True,
    )

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        related_name="files",
    )

    path = models.CharField(
        max_length=2048,
    )

    file_type = models.CharField(
        max_length=16,
        choices=FileType.choices,
        default=FileType.FILE,
    )

    state = models.TextField(
        blank=True,
        default="",
    )

    url = models.CharField(
        max_length=2048,
        blank=True,
        default="",
        verbose_name="Content URL",
        help_text=(
            "Внутренний URL интерфейса, открываемого после снятия "
            "всех блокирующих слоёв. Например: apps/assets/12/"
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "machine",
                    "path",
                ),
                name="unique_machine_file_path",
            ),
        ]

    def __str__(self):
        return f"{self.machine.hostname}:{self.path}"


class SessionFile(models.Model):
    """Что сделала сессия с файлом машины.

    Файл без записи здесь выглядит в сессии так, как лежит на машине.
    Запись появляется, когда с файлом что-то случилось: игрок снял слой,
    переименовал, скопировал или удалил его.

    На один файл машины может быть несколько записей (копии, =>): каждая
    живёт под своим path и со своим прогрессом.
    """

    id = models.BigAutoField(
        primary_key=True,
    )

    session = models.ForeignKey(
        "machines.Session",
        on_delete=models.CASCADE,
        related_name="files",
    )

    file = models.ForeignKey(
        "filesystem.MachineFile",
        on_delete=models.CASCADE,
        related_name="session_files",
    )

    path = models.CharField(
        max_length=2048,
        blank=True,
        help_text=(
            "Путь файла в этой сессии. Пусто при создании = путь файла "
            "на машине."
        ),
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Файл удалён игроком в этой сессии (надгробие).",
    )

    state = models.TextField(
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "session",
                    "path",
                ),
                name="unique_session_path",
            ),
        ]

        indexes = [
            models.Index(
                fields=(
                    "session",
                    "file",
                ),
                name="sessionfile_session_file_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.path:
            self.path = self.file.path

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session} : {self.path}"


class FileKey(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    file = models.ForeignKey(
        "filesystem.MachineFile",
        on_delete=models.CASCADE,
        related_name="keys",
    )

    key = models.ForeignKey(
        "secure.Key",
        on_delete=models.CASCADE,
        related_name="files",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "file",
                    "key",
                ),
                name="unique_file_key",
            ),
        ]
