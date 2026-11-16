from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Слой игрока становится изменениями мира: прежние записи игроков просто удаляются (прод не учитываем)."""

    dependencies = [
        ("filesystem", "0039_format_content_without_message"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(lambda apps, schema: apps.get_model("filesystem", "PlayerFile").objects.all().delete(), migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="playerfile", name="unique_player_file_path"),
        migrations.RemoveConstraint(model_name="playerfile", name="player_file_item_or_data"),
        migrations.RemoveIndex(model_name="playerfile", name="playerfile_user_instance_idx"),
        migrations.RemoveField(model_name="playerfile", name="user"),
        migrations.RenameModel(old_name="PlayerFile", new_name="FileChange"),
        migrations.AlterModelOptions(name="filechange", options={"verbose_name": "Изменение файла", "verbose_name_plural": "Изменения файлов"}),
        migrations.AddField(
            model_name="filechange", name="sandbox",
            field=models.ForeignKey(blank=True, help_text="Пусто: мир. Иначе песочница автора (его песочный игрок).", null=True,
                                    on_delete=django.db.models.deletion.CASCADE, related_name="sandbox_files", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="filechange", name="changed_by",
            field=models.ForeignKey(blank=True, help_text="Кто изменил последним (для автора, в игре не видно).", null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name="file_changes", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="filechange", name="instance",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="file_changes", to="filesystem.volumeinstance"),
        ),
        migrations.AlterField(
            model_name="filechange", name="item",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="file_changes", to="filesystem.item"),
        ),
        migrations.AddConstraint(model_name="filechange", constraint=models.UniqueConstraint(
            condition=models.Q(("sandbox__isnull", True)), fields=("instance", "path"), name="unique_world_file_path")),
        migrations.AddConstraint(model_name="filechange", constraint=models.UniqueConstraint(
            condition=models.Q(("sandbox__isnull", False)), fields=("sandbox", "instance", "path"), name="unique_sandbox_file_path")),
        migrations.AddConstraint(model_name="filechange", constraint=models.CheckConstraint(
            condition=~(models.Q(item__isnull=False) & models.Q(data__isnull=False)), name="file_change_item_or_data")),
        migrations.AddIndex(model_name="filechange", index=models.Index(fields=["sandbox", "instance"], name="filechange_world_idx")),
    ]
