"""Персонаж мира: одно лицо во всех каналах (почта, эфир, форум) и карточка для авторов, чтобы держать один голос."""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Character(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        SILENT = "silent", "Молчит"
        MISSING = "missing", "Пропал"
        DEAD = "dead", "Мёртв"

    code = models.CharField("Код", max_length=3, unique=True, validators=[RegexValidator(r"^[A-Z0-9]{3}$", "Три знака: латинские буквы и цифры.")],
                            help_text="Бейдж отправителя на форуме и в ленте кукловода: OP7, SYS, MAP.")
    name = models.CharField("Имя", max_length=120, help_text="Как персонажа зовут в мире.")
    callsign = models.CharField("Позывной", max_length=16, blank=True, help_text="Подпись в эфире и на форуме. Пусто: имя.")
    color = models.PositiveSmallIntegerField("Цвет кода", default=0, help_text="0 акцент, 1 зелёный, 2 предупреждение, 3 сведения (токены ОС).")
    status = models.CharField("Статус", max_length=8, choices=Status.choices, default=Status.ACTIVE)
    about = models.TextField("Кто это", blank=True)
    voice = models.TextField("Как говорит", blank=True, help_text="Манера, слова-паразиты, чего никогда не скажет.")
    knows = models.TextField("Что знает", blank=True, help_text="И чего не знает: чтобы не проговориться.")
    note = models.TextField("Заметка", blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="characters",
                              verbose_name="Ведёт", help_text="Автор, которому идут входящие персонажа. Пусто: всем.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Персонаж"
        verbose_name_plural = "Персонажи"

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def signature(self):
        """Как персонаж подписан на форуме и в эфире."""
        return self.callsign or self.name
