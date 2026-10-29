from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class EntryPolicy(models.Model):
    """Политика входа: правила, по которым запись принимает игрока. Назначается типу системы, машине или профилю; действует самая
    конкретная. Пароль, условие по ключам и токены остаются у профиля: политика говорит, как их сочетать и когда, откуда и сколько раз
    можно входить. Решение принимает machines/access/entry.py."""

    class Mode(models.TextChoices):
        ALL = "all", "Нужны и пароль, и ключ"
        ANY = "any", "Хватает пароля или ключа"

    name = models.CharField("Название", max_length=64, unique=True)
    description = models.TextField("Заметка", blank=True, help_text="Для автора, игрок её не видит.")
    mode = models.CharField(
        "Пароль и ключ", max_length=3, choices=Mode.choices, default=Mode.ALL,
        help_text="Как сочетаются способы записи. Токен пускает мимо обоих.",
    )
    sources = models.TextField(
        "Откуда можно", blank=True,
        help_text="Хосты, с которых можно входить, по одному в строке. * в имени заменяет любые знаки: gw-*. Пусто: откуда угодно.",
    )
    via = models.TextField(
        "Только через", blank=True, help_text="Хосты, через которые вход обязан пройти (цепочка мостов игрока), по одному в строке.",
    )
    max_attempts = models.PositiveSmallIntegerField(
        "Неверных попыток", null=True, blank=True, help_text="Сколько ошибок подряд до блокировки. Пусто: без блокировки.",
    )
    attempts_window = models.PositiveIntegerField("Окно попыток, с", default=600, help_text="Ошибки считаются за это время.")
    lock_seconds = models.PositiveIntegerField(
        "Блокировка, с", default=300, help_text="Сколько запись не принимает игрока после серии ошибок или обрыва по сроку.",
    )
    ttl = models.PositiveIntegerField(
        "Срок подключения, с", null=True, blank=True, help_text="Сколько держится подключение. Пусто: без ограничения.",
    )
    windows = models.TextField(
        "Окна времени", blank=True,
        help_text="mon-fri: 9:00-13:00 14:00-17:00. Дни: mon-fri, sat,sun, *. except sun: * закрывает день. Пусто: в любое время.",
    )
    denied_text = models.TextField("Текст отказа", blank=True, help_text="Пусто: стандартный для системы.")
    locked_text = models.TextField("Текст блокировки", blank=True)
    window_text = models.TextField("Текст вне окна", blank=True)
    kick_text = models.TextField("Текст при обрыве", blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Политика входа"
        verbose_name_plural = "Политики входа"

    def __str__(self):
        return self.name

    @staticmethod
    def lines(text):
        return [line.split("#", 1)[0].strip() for line in (text or "").splitlines() if line.split("#", 1)[0].strip()]

    def clean(self):
        from machines.access import windows

        try:
            windows.parse(self.windows)
        except windows.WindowError as error:
            raise ValidationError({"windows": str(error)})
        if self.max_attempts is not None and self.max_attempts < 1:
            raise ValidationError({"max_attempts": "Не меньше одной попытки."})


class LoginEvent(models.Model):
    """Событие входа на запись: успех, отказ и его причина. Из событий считается блокировка после ошибок, и они же журнал хоста."""

    class Kind(models.TextChoices):
        OK = "ok", "Вход"
        BAD_PASSWORD = "bad_password", "Неверный пароль"
        BAD_KEY = "bad_key", "Нет ключа"
        BAD_TOKEN = "bad_token", "Токен отвергнут"
        SOURCE = "source", "Не с того хоста"
        ROUTE = "route", "Не через тот хост"
        WINDOW = "window", "Вне окна времени"
        LOCKED = "locked", "Блокировка"

    FAILURES = ("bad_password", "bad_key")

    profile = models.ForeignKey("machines.MachineProfile", on_delete=models.CASCADE, related_name="events")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_events")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    shown_at = models.DateTimeField(
        "Время на машине", default=timezone.now, help_text="Время, которое показывали часы машины игрока, когда это случилось (журнал пишет его).",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    source = models.CharField("Откуда", max_length=128, blank=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("at", "id")
        indexes = [models.Index(fields=("profile", "user", "at"), name="loginevent_pair_idx")]
        verbose_name = "Событие входа"
        verbose_name_plural = "События входа"

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M:%S} {self.profile.login} {self.kind}"


class Group(models.Model):
    """Группа записей: набор привилегий. Умолчание задаёт тип системы, машина может переопределить группу или отключить её.

    Какие группы есть у машины, см. machines/access/groups.py."""

    system_type = models.ForeignKey("machines.SystemType", null=True, blank=True, on_delete=models.CASCADE, related_name="groups")
    machine = models.ForeignKey("machines.Machine", null=True, blank=True, on_delete=models.CASCADE, related_name="groups")
    name = models.SlugField("Имя", max_length=32)
    privileges = models.JSONField("Привилегии", default=list, blank=True)
    everyone = models.BooleanField("Все записи", default=False, help_text="В группе все записи машины, включая созданные позже.")
    disabled = models.BooleanField(
        "Отключена", default=False, help_text="Только у машины: группа типа системы с этим именем на этой машине не действует.",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        constraints = [
            models.CheckConstraint(
                condition=(Q(system_type__isnull=False, machine__isnull=True) | Q(system_type__isnull=True, machine__isnull=False)),
                name="group_system_xor_machine",
            ),
            models.UniqueConstraint(fields=("system_type", "name"), condition=Q(system_type__isnull=False), name="unique_system_group"),
            models.UniqueConstraint(fields=("machine", "name"), condition=Q(machine__isnull=False), name="unique_machine_group"),
        ]

    def __str__(self):
        return f"{self.system_type or self.machine}: {self.name}"

    def clean(self):
        from machines.access.privileges import PRIVILEGES

        unknown = [code for code in self.privileges if code not in PRIVILEGES]
        if unknown:
            raise ValidationError({"privileges": f"Нет таких привилегий: {', '.join(unknown)}."})
        if self.disabled and self.machine_id is None:
            raise ValidationError({"disabled": "Отключить можно только группу у машины."})
