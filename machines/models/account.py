from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import models

from mail.addresses import validate_address


def endpoint(value):
    """Точка входа строкой с тремя знаками («14.230», «22.000»); не число — None."""
    try:
        return f"{Decimal(str(value).strip().replace(',', '.')):.3f}"
    except (InvalidOperation, ValueError):
        return None


class MachineProfile(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        related_name="profiles",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="machine_profiles",
    )

    name = models.CharField(
        max_length=255,
    )

    endpoints = models.JSONField(
        "Точки входа",
        default=list,
        blank=True,
        help_text="Где на учётку заходят удалённо: у систем Aether частоты в МГц (14.230), у остальных порты (22). Пусто — извне не зайти.",
    )

    login = models.CharField(
        max_length=128,
    )

    mail = models.CharField(
        "Почта",
        max_length=255,
        validators=[validate_address],
        help_text="Адрес этого профиля, например will_smith@apollo.mail. Игрок под профилем читает и пишет от его лица.",
    )

    password_hash = models.CharField(
        max_length=128,
        blank=True,
    )

    key_condition = models.JSONField(
        null=True,
        blank=True,
    )

    ttl = models.PositiveIntegerField(
        "Срок подключения, с",
        null=True,
        blank=True,
        help_text="Сколько секунд держится подключение игрока на эту запись (с момента входа). Пусто: без ограничения.",
    )

    cooldown = models.PositiveIntegerField(
        "Блокировка после обрыва, с",
        null=True,
        blank=True,
        help_text="Сколько секунд после обрыва по сроку запись не принимает этого игрока (для него это блокировка аккаунта).",
    )

    groups = models.JSONField(
        "Группы", default=list, blank=True,
        help_text="Группы записи по имени. Группы «все записи» входят всегда; привилегии складываются по группам.",
    )

    root = models.BooleanField(
        "root", default=False, help_text="Все привилегии и обход прав файлов.",
    )

    entry_policy = models.ForeignKey(
        "machines.EntryPolicy", null=True, blank=True, on_delete=models.SET_NULL, related_name="profiles", verbose_name="Политика входа",
        help_text="Пусто: действует политика машины, иначе типа системы.",
    )

    kick_message = models.TextField(
        "Сообщение при обрыве",
        blank=True,
        help_text="Текст в окне на чёрном экране, когда игрока выбросило с рабочего стола этой записи. Пусто: стандартный для системы.",
    )

    login_scene = models.ForeignKey(
        "machines.SceneScript", null=True, blank=True, on_delete=models.SET_NULL, related_name="accounts", verbose_name="Сцена после входа",
        help_text="Играет после приветствия, когда игрок входит под эту учётку. Пусто: общая сцена ОС (слот login.account), если она задана.",
    )

    class Meta:
        ordering = ("machine", "login")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "machine",
                    "login",
                ),
                name="unique_machine_profile_login",
            ),
        ]

    def __str__(self):
        return f"{self.login}@{self.machine.label}"

    @property
    def freq(self):
        """Первая точка входа (Decimal); 0 — извне не зайти. Задать — точки входа станут этой одной (0 — ни одной)."""
        return Decimal(self.endpoints[0]) if self.endpoints else Decimal("0")

    @freq.setter
    def freq(self, value):
        found = endpoint(value)
        self.endpoints = [found] if found and Decimal(found) != 0 else []

    def serves(self, value):
        """Слушает ли учётка на этой частоте или порту."""
        found = endpoint(value)
        return found is not None and found in self.endpoints

    def save(self, *args, **kwargs):
        if not self.mail:
            self.mail = f"{self.login}@{self.machine.label}"

        super().save(*args, **kwargs)


class MachineProfileToken(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    profile = models.ForeignKey(
        MachineProfile,
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    token = models.CharField(
        max_length=255,
        unique=True,
    )

    max_usage = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    usage = models.PositiveIntegerField(
        default=0,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.profile.login} / {self.token}"


class Session(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    profile = models.ForeignKey(
        "machines.MachineProfile",
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    blocked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Запись не принимает игрока до этого момента (после обрыва по сроку).",
    )

    seen_at = models.DateTimeField(
        null=True, blank=True, help_text="Когда игрок последний раз работал в этой сессии (терминал отмечает раз в полминуты).",
    )

    kick_at = models.DateTimeField(
        null=True, blank=True, help_text="Автор попросил выкинуть игрока: подключение закроется при его следующем запросе.",
    )

    def __str__(self):
        return f"{self.user} @ {self.profile}"
