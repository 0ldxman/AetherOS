from django.db import models

# Create your models here.
class Key(models.Model):
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    suffix = models.TextField(default=".pem")
