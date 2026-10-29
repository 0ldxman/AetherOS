from django.db import models

from machines.world import dates


class World(models.Model):
    """Настройки мира: «сейчас» в игре, когда центр замолчал, сколько станций в эфире. Одна запись на игру (pk=1).

    От них считаются даты и числа в экранах входа, загрузки и приветствия. Пока записи нет, действуют значения из machines/world/dates.py."""

    game_now = models.DateTimeField("«Сейчас» в мире (UTC)", default=dates.GAME_NOW, help_text="Дата и время, от которых считаются «N дней назад».")
    core_last_contact = models.DateField("Последний контакт с центром", default=dates.CORE_LAST_CONTACT)
    beacon_last_sync = models.DateField("Последнее обновление списков станций и мостов", default=dates.BEACON_LAST_SYNC)
    cert_not_after = models.DateField("Сертификат узла действует до", default=dates.CERT_NOT_AFTER)
    stations_known = models.PositiveSmallIntegerField("Станций в каталоге", default=31)
    stations_reachable = models.PositiveSmallIntegerField("Станций отвечает", default=17)
    audit_per_day = models.PositiveSmallIntegerField("Записей аудита за сутки", default=34, help_text="Сколько копит узел с тех пор, как центр замолчал.")

    class Meta:
        verbose_name = "Мир"
        verbose_name_plural = "Мир"

    def __str__(self):
        return f"Мир на {self.game_now:%Y-%m-%d}"

    @property
    def game_date(self):
        return self.game_now.date()

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]
