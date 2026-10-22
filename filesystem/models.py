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

    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="machine_files",
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

    state = models.TextField(
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "session",
                    "file",
                ),
                name="unique_session_file",
            ),
        ]

    def __str__(self):
        return f"{self.session} : {self.file.path}"


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