from django.core.validators import MinValueValidator
from django.db import models


class World(models.Model):
    """Мир: игровое время. Одна запись на игру (pk=1)."""

    class Meta:
        verbose_name = "Мир"
        verbose_name_plural = "Мир"

    def __str__(self):
        return f"Мир на {self.game_now:%Y-%m-%d}"

    @property
    def game_now(self):
        """Игровое «сейчас» (UTC): считается по опорным точкам времени (machines/world/chrono.py)."""
        from machines.world import chrono

        return chrono.game_now()

    @property
    def game_date(self):
        return self.game_now.date()

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]


class TimeAnchor(models.Model):
    """Опорная точка игрового времени: с реального момента real_at в мире game_at, и дальше время идёт со скоростью rate.

    Наступившие точки не правятся (на них держится игровое время всех прошлых записей), будущие можно править и удалять."""

    real_at = models.DateTimeField("Реальный момент (UTC)", unique=True)
    game_at = models.DateTimeField("Игровой момент (UTC)")
    rate = models.DecimalField("Скорость", max_digits=9, decimal_places=4, default=1, validators=[MinValueValidator(0)],
                               help_text="1: как в жизни; 0: время стоит; 0.5: вдвое медленнее; 24: игровые сутки за реальный час.")
    note = models.CharField("Заметка", max_length=200, blank=True)

    class Meta:
        ordering = ("real_at",)
        verbose_name = "Точка игрового времени"
        verbose_name_plural = "Игровое время"

    def __str__(self):
        return f"{self.real_at:%Y-%m-%d %H:%M} → {self.game_at:%Y-%m-%d %H:%M} ×{self.rate}"
