from django.conf import settings
from django.db import models


class MachineClock(models.Model):
    """Часы машины в мире игрока: сдвиг от мирового времени. Двигает их запись с привилегией clock (команда tmset)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="machine_clocks")
    machine = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="clocks")
    offset = models.BigIntegerField("Сдвиг, с", default=0)

    class Meta:
        verbose_name = "Часы машины"
        verbose_name_plural = "Часы машин"
        constraints = [models.UniqueConstraint(fields=("user", "machine"), name="unique_machine_clock")]

    def __str__(self):
        return f"{self.user_id}@{self.machine_id}: {self.offset:+d} с"
