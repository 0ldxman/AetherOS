"""Почта на файлах (mail.boxes): письма лежат в ящиках учёток на машинах, здесь только состояние игрока.

MailMark: прочитано ли письмо и когда оно пришло (для доставленных); своё у каждого игрока (гость witness: по сессии).
MailQueue: письма, которые придут игроку позже (задержка исхода или хука).
"""
from django.conf import settings
from django.db import models


class MailMark(models.Model):
    machine = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="mail_marks")
    path = models.CharField("Путь письма", max_length=1024)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="mail_marks")
    session_key = models.CharField(max_length=64, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True, help_text="Время машины игрока, когда письмо пришло.")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("machine", "path", "user", "session_key"), name="unique_mail_mark")]
        indexes = [models.Index(fields=("user", "machine"), name="mailmark_user_machine_idx")]
        verbose_name = "Отметка письма"
        verbose_name_plural = "Отметки писем"

    def __str__(self):
        return f"{self.path} ({self.user_id or self.session_key[:8]})"


class MailQueue(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mail_queue")
    profile = models.ForeignKey("machines.MachineProfile", on_delete=models.CASCADE, related_name="mail_queue")
    item = models.ForeignKey("filesystem.Item", on_delete=models.CASCADE, related_name="mail_queue")
    folder = models.CharField(max_length=16, default="inbox")
    available_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("available_at", "pk")
        verbose_name = "Письмо в очереди"
        verbose_name_plural = "Очередь писем"

    def __str__(self):
        return f"{self.item_id} -> {self.user_id} at {self.available_at:%Y-%m-%d %H:%M:%S}"


# ---- переписка с персонажами (mail.talk) ------------------------------------------------------------------------------

class Persona(models.Model):
    """Персонаж мира с почтовым адресом: ему пишут и он отвечает по сценариям переписки."""

    address = models.CharField("Адрес", max_length=255, unique=True)
    name = models.CharField("Имя", max_length=120, blank=True)
    signature = models.TextField("Подпись", blank=True)
    note = models.TextField("Заметка автора", blank=True)

    class Meta:
        ordering = ("address",)
        verbose_name = "Персонаж"
        verbose_name_plural = "Персонажи"

    def __str__(self):
        return f"{self.name} <{self.address}>" if self.name else self.address

    def save(self, *args, **kwargs):
        self.address = self.address.strip().lower()
        super().save(*args, **kwargs)


class Conversation(models.Model):
    """Сценарий переписки персонажа: шаги, на каждом письмо персонажа и варианты ответа игрока.

    Начинается хуком «mail <slug>» (первый шаг) или письмом игрока на адрес персонажа (шаг «начало переписки»)."""

    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="conversations")
    slug = models.SlugField("Идентификатор", max_length=64, unique=True)
    title = models.CharField("Название", max_length=200)
    note = models.TextField("Заметка автора", blank=True)

    class Meta:
        ordering = ("persona", "slug")
        verbose_name = "Сценарий переписки"
        verbose_name_plural = "Сценарии переписки"

    def __str__(self):
        return self.title or self.slug


class Step(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="steps")
    name = models.CharField("Имя шага", max_length=64, help_text="На него ссылаются исходы: goto <имя>.")
    order = models.PositiveSmallIntegerField(default=0)
    letter = models.ForeignKey("filesystem.Item", null=True, blank=True, on_delete=models.SET_NULL, related_name="talk_steps",
                               verbose_name="Письмо персонажа", help_text="Приходит игроку, когда он попадает на шаг.")
    letter_delay = models.PositiveIntegerField("Задержка письма, с", default=0)
    opening = models.BooleanField("Начало переписки", default=False,
                                  help_text="Его варианты видит игрок, который сам пишет на адрес персонажа (переписки ещё нет).")

    class Meta:
        ordering = ("conversation", "order", "pk")
        constraints = [models.UniqueConstraint(fields=("conversation", "name"), name="unique_step_name")]
        verbose_name = "Шаг переписки"
        verbose_name_plural = "Шаги переписки"

    def __str__(self):
        return f"{self.conversation.slug}:{self.name}"


class Variant(models.Model):
    """Вариант ответа игрока на шаге: текст для набора ({{секрет}}, [[выбор|слова]]), когда доступен, что нужно приложить,
    что случится (исходы по ключам ok, word:<слово>, wrong, exhausted)."""

    class Mode(models.TextChoices):
        REPLY = "reply", "Ответ"
        FORWARD = "forward", "Пересылка"

    class Closed(models.TextChoices):
        MYSTERY = "mystery", "Показать как «???»"
        HIDDEN = "hidden", "Скрыть"

    step = models.ForeignKey(Step, on_delete=models.CASCADE, related_name="variants")
    order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField("Подпись в списке", max_length=200)
    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.REPLY)
    text = models.TextField("Текст для набора", blank=True)
    forward_of = models.ForeignKey("filesystem.Item", null=True, blank=True, on_delete=models.SET_NULL, related_name="talk_forwards",
                                   verbose_name="Какое письмо переслать")
    condition = models.JSONField("Условие по ключам", null=True, blank=True)
    need_flags = models.JSONField("Нужны метки", default=list, blank=True)
    deny_flags = models.JSONField("Мешают метки", default=list, blank=True)
    account = models.ForeignKey("machines.MachineProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="talk_variants",
                                verbose_name="Писать с учётки", help_text="Вариант доступен, только если игрок пишет с этой учётки.")
    closed = models.CharField("Если недоступен", max_length=8, choices=Closed.choices, default=Closed.MYSTERY)
    attachment = models.JSONField("Вложение", default=dict, blank=True, help_text='{"item": слаг} | {"key": слаг} | {"signed": слаг ключа}')
    max_attempts = models.PositiveSmallIntegerField("Попыток", default=0, help_text="0: без ограничения.")
    outcomes = models.JSONField("Исходы", default=dict, blank=True)

    class Meta:
        ordering = ("step", "order", "pk")
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"

    def __str__(self):
        return self.title


class TalkState(models.Model):
    """Где игрок в переписке: текущий шаг, попытки по вариантам и учётка, в ящик которой идут письма персонажа."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="talks")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="states")
    step = models.ForeignKey(Step, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    profile = models.ForeignKey("machines.MachineProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    attempts = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "conversation"), name="unique_talk_state")]
        verbose_name = "Переписка игрока"
        verbose_name_plural = "Переписки игроков"


class Flag(models.Model):
    """Метка прогресса игрока: персонажи «помнят», что он сделал (условия вариантов, исходы)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="flags")
    name = models.CharField(max_length=64)
    set_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "name"), name="unique_player_flag")]
        verbose_name = "Метка игрока"
        verbose_name_plural = "Метки игроков"

    def __str__(self):
        return f"{self.user_id}:{self.name}"
