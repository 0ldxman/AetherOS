"""Эфир: открытый радиоэфир сети узлов. Игроки слушают и передают почти на любой частоте; приватность в том, чтобы найти
свободную. Слушатель видит только то, что пришло после его выхода на частоту. Система хранит передачи 24 часа (модерация и скан).
Логика в air/radio.py."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Callsign(models.Model):
    """Позывной игрока в эфире. Настоящее имя (Discord) видят только авторы."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="callsign")
    name = models.CharField("Позывной", max_length=16, unique=True)
    changed_at = models.DateTimeField("Сменён игроком", null=True, blank=True)
    muted_until = models.DateTimeField("Заглушён до", null=True, blank=True)
    rx_only = models.BooleanField("Только приём", default=False, help_text="Передатчик отобран: игрок слушает, но не передаёт.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Позывной"
        verbose_name_plural = "Позывные"

    def __str__(self):
        return self.name


class CallsignChange(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="callsign_changes")
    old = models.CharField(max_length=16)
    new = models.CharField(max_length=16)
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                           help_text="Автор, если сменил он; пусто: сам игрок.")

    class Meta:
        ordering = ("-at", "-pk")


class Station(models.Model):
    """Станция или персонаж: от их имени передают авторы. Имя зарезервировано, игрок его не займёт."""

    class Kind(models.TextChoices):
        STATION = "station", "Станция"
        CHARACTER = "character", "Персонаж"

    name = models.CharField("Позывной", max_length=16, unique=True)
    label = models.CharField("Подпись для авторов", max_length=120, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.STATION)

    class Meta:
        ordering = ("name",)
        verbose_name = "Станция"
        verbose_name_plural = "Станции и персонажи"

    def __str__(self):
        return self.name


class Band(models.Model):
    """Полоса частот с особым правилом: зарезервирована (игроки не передают) или слышна только по условию на ключи."""

    class Kind(models.TextChoices):
        OPEN = "open", "Обычная"
        RESERVED = "reserved", "Зарезервирована"
        CONDITIONAL = "conditional", "Слышна по условию"

    low = models.DecimalField("С частоты", max_digits=6, decimal_places=3)
    high = models.DecimalField("По частоту", max_digits=6, decimal_places=3)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.RESERVED)
    condition = models.JSONField("Условие слушать", null=True, blank=True, help_text="Условие на ключи (secure.access). Пусто: слышат все.")
    label = models.CharField("Подпись", max_length=120, blank=True)
    window = models.TextField(
        "Окно прохождения", blank=True,
        help_text="Когда полоса проходит, по игровому времени в поясе полосы: «mon-fri: 21:00-23:30», «except sun: *». "
                  "Пусто: всегда. Вне окна тишина, у краёв (±10 минут) сигнал рассыпается.")
    time_zone = models.CharField("Часовой пояс окна", max_length=64, default="UTC")

    class Meta:
        ordering = ("low",)
        verbose_name = "Полоса"
        verbose_name_plural = "Полосы"

    def __str__(self):
        return f"{self.low}–{self.high} {self.label}"


class Transmission(models.Model):
    freq = models.DecimalField("Частота", max_digits=6, decimal_places=3, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="transmissions")
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.CASCADE, related_name="transmissions")
    callsign = models.CharField("Позывной в момент передачи", max_length=16)
    machine = models.ForeignKey("machines.Machine", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    text = models.CharField(max_length=400)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hidden_reason = models.CharField(max_length=200, blank=True)
    sandbox = models.BooleanField(default=False, help_text="Передал песочный игрок автора: слышит только его песочница.")
    broadcast = models.ForeignKey("air.Broadcast", null=True, blank=True, on_delete=models.SET_NULL, related_name="transmissions")
    slot = models.DateTimeField("Слот расписания (игровое UTC)", null=True, blank=True)
    condition = models.JSONField("Кому слышно", null=True, blank=True, help_text="Условие на ключи (secure.access). Пусто: всем.")
    on_air = models.CharField("Как звучит в эфире", max_length=400, blank=True, help_text="Шифровка, если передали с ключом; пусто: открытый текст.")
    key = models.CharField("Ключ шифра", max_length=32, blank=True, help_text="Видят только авторы.")
    key_mark = models.CharField(max_length=16, blank=True, help_text="Отпечаток ключа: с тем же ключом слушатель видит открытый текст.")

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [models.UniqueConstraint(fields=("broadcast", "slot"), name="unique_air_broadcast_slot")]
        indexes = [models.Index(fields=("freq", "created_at"), name="air_freq_time_idx")]

    def __str__(self):
        return f"{self.freq} {self.callsign}: {self.text[:40]}"


class Report(models.Model):
    transmission = models.ForeignKey(Transmission, on_delete=models.CASCADE, related_name="reports")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="air_reports")
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("transmission", "user"), name="unique_air_report")]


class Broadcast(models.Model):
    """Передача станции по расписанию игрового времени. Выпуск появляется в эфире сам, когда наступает слот (air/events.py)."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="broadcasts")
    freq = models.DecimalField("Частота", max_digits=6, decimal_places=3)
    texts = models.JSONField("Тексты", default=list, help_text="Один или несколько: выпуски идут по кругу.")
    schedule = models.TextField("Расписание", help_text="Строки: «daily 21:00», «mon,fri 21:00 23:30», «hourly :15», «every 30m», «once 2031-03-01 21:00».")
    time_zone = models.CharField("Часовой пояс расписания", max_length=64, default="UTC")
    condition = models.JSONField("Кому слышно", null=True, blank=True, help_text="Условие на ключи (secure.access). Пусто: всем на частоте.")
    active = models.BooleanField("Включена", default=True)
    note = models.CharField("Заметка", max_length=200, blank=True)
    key = models.CharField("Ключ шифра", max_length=32, blank=True, help_text="Пусто: открытым текстом. Иначе выпуск идёт шифровкой Виженера.")
    last_slot = models.DateTimeField("Последний выпуск (игровое UTC)", null=True, blank=True)
    turn = models.PositiveIntegerField("Номер следующего текста", default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("freq", "pk")
        verbose_name = "Передача по расписанию"
        verbose_name_plural = "Передачи по расписанию"

    def __str__(self):
        return f"{self.station.name} {self.freq}: {self.schedule.splitlines()[0] if self.schedule else ''}"


class Responder(models.Model):
    """Станция слушает частоту и отвечает на передачу игрока по шаблону. Ответ слышат все на частоте, исходы достаются передавшему."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="responders")
    freq = models.DecimalField("Частота", max_digits=6, decimal_places=3)
    pattern = models.TextField("На что отвечает", help_text="Строки-варианты: слово или фраза целиком, без учёта регистра. Или регулярное выражение.")
    regex = models.BooleanField("Регулярное выражение", default=False)
    condition = models.JSONField("Кому отвечает", null=True, blank=True, help_text="Условие на ключи передавшего. Пусто: всем.")
    cooldown = models.PositiveIntegerField("Пауза для игрока, мин", default=10)
    reply = models.TextField("Ответ в эфир", blank=True, help_text="Можно {callsign}: позывной передавшего. Пусто: молча.")
    delay = models.PositiveIntegerField("Задержка ответа, с", default=5)
    actions = models.JSONField("Исходы", default=list, blank=True, help_text="Как в почте: flag, unflag, key, file, hook.")
    key = models.CharField("Ключ шифра", max_length=32, blank=True,
                           help_text="Станция слушает и отвечает этим ключом: шаблон сверяется с расшифровкой. Пусто: слышит эфир как есть.")
    active = models.BooleanField("Включён", default=True)
    note = models.CharField("Заметка", max_length=200, blank=True)

    class Meta:
        ordering = ("freq", "pk")
        verbose_name = "Ответчик"
        verbose_name_plural = "Ответчики"

    def __str__(self):
        return f"{self.station.name} {self.freq}: {self.pattern.splitlines()[0] if self.pattern else ''}"


class ResponderFire(models.Model):
    """Когда ответчик сработал на игрока: для паузы."""

    responder = models.ForeignKey(Responder, on_delete=models.CASCADE, related_name="fires")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    fired_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=("responder", "user", "fired_at"), name="air_fire_idx")]


class PendingReply(models.Model):
    """Ответ станции, который выйдет в эфир позже (задержка ответчика). Выходит при первом приёме после due_at."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="+")
    freq = models.DecimalField(max_digits=6, decimal_places=3)
    text = models.CharField(max_length=400)
    due_at = models.DateTimeField(db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                             help_text="Для песочницы: ответ слышит только песочный игрок.")
    sandbox = models.BooleanField(default=False)
    key = models.CharField(max_length=32, blank=True)
