"""Новости команды игрокам: объявления вне мира игры. Видны всем игрокам с приложением news на столе."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Post(models.Model):
    title = models.CharField("Заголовок", max_length=200)
    body = models.TextField("Текст", blank=True, help_text="Простая разметка: # заголовок, - список, > цитата, **жирный**, *курсив*, `код`.")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="news_posts")
    publish_at = models.DateTimeField("Публикация", null=True, blank=True, db_index=True, help_text="Пусто: черновик. В будущем: запланирована.")
    pinned = models.BooleanField("Закреплена", default=False)
    important = models.BooleanField("Важная", default=False, help_text="Всплывает уведомлением на столе, пока игрок её не прочтёт.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-pinned", "-publish_at", "-pk")
        verbose_name = "Новость"
        verbose_name_plural = "Новости"

    def __str__(self):
        return self.title

    @property
    def status(self):
        if self.publish_at is None:
            return "draft"
        return "scheduled" if self.publish_at > timezone.now() else "published"


class PostRead(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="news_reads")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("post", "user"), name="unique_post_read")]
