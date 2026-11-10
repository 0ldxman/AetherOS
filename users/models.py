from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # роль автора в Студии (team.rights); у игрока и суперадмина пусто
    role = models.ForeignKey("team.Role", null=True, blank=True, on_delete=models.SET_NULL, related_name="users", verbose_name="Роль в Студии")
