from django.db import models
from django.contrib.auth.models import AbstractUser
from secure.models import Key

# Create your models here.
class User(AbstractUser):
    keys = models.ManyToManyField(
        Key, through="UserKey", related_name="holders", blank=True
    )
 
 
class UserKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    key = models.ForeignKey(Key, on_delete=models.CASCADE)
    obtained_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="unique_user_key"),
        ]
 
    def __str__(self):
        return f"{self.user} -> {self.key}"
