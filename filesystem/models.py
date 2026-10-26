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

    size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Размер в байтах, который видит игрок (ls -l, cnt). Пусто: размер выдумывается из пути файла и всегда один и тот же."
        ),
    )

    system = models.BooleanField(
        default=False,
        help_text="Системный файл: игрок не может его удалить (del). Базовые папки защищает список «Защищённые пути».",
    )

    delivered_only = models.BooleanField(
        default=False,
        help_text=(
            "Файл не лежит на машине сам по себе: он появляется у игрока, когда ему его "
            "доставили (например, вложением письма «сохранить на машину»)."
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
        return f"{self.machine.label}:{self.path}"


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

    # Корзина (del): файл лежит в /trash, пока не истечёт purge_at. Потом запись остаётся надгробием (deleted_at)
    # или исчезает, если файл пришёл с другой машины. origin_path и trashed_at нужны для rcvr.
    origin_path = models.CharField(max_length=2048, blank=True, default="")
    trashed_at = models.DateTimeField(null=True, blank=True)
    purge_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Когда файл из корзины удалится насовсем. Пусто: файл не в корзине.",
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

    def __str__(self):
        return f"{self.file} — {self.key}"


class ProtectedPath(models.Model):
    """Путь, который игрок не может удалить командой del (и никто внутри него тоже): базовые папки.

    Без машины действует на всех машинах. Начальный список (/, /home, /bin, /trash) создаёт миграция.
    """

    path = models.CharField(max_length=2048)
    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="protected_paths",
        help_text="Пусто: путь защищён на всех машинах.",
    )

    class Meta:
        ordering = ("path",)
        verbose_name = "Защищённый путь"
        verbose_name_plural = "Защищённые пути"
        constraints = [
            models.UniqueConstraint(fields=("path", "machine"), name="unique_protected_path_machine"),
            models.UniqueConstraint(
                fields=("path",), condition=models.Q(machine__isnull=True), name="unique_protected_path_global"
            ),
        ]

    def __str__(self):
        return self.path + (f" ({self.machine.label})" if self.machine_id else "")

    def save(self, *args, **kwargs):
        text = "/" + "/".join(part for part in (self.path or "").split("/") if part)
        self.path = text
        super().save(*args, **kwargs)

