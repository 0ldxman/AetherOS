"""Письма и задачи на набор переходят от «машина + логин» к адресам профилей.

Адрес профиля это логин@hostname машины (так их заполнила миграция профилей).
"""
from django.db import migrations


def _host(machine):
    return machine.hostname or machine.name


def convert(apps, schema_editor):
    Message = apps.get_model("mail", "Message")
    Task = apps.get_model("mail", "ComposeTask")
    Profile = apps.get_model("machines", "MachineProfile")

    for message in Message.objects.select_related("machine"):
        machine = message.machine
        host = _host(machine) if machine else "*"

        if message.sender_login and machine is not None:
            sender = f"{message.sender_login}@{host}"
        elif message.sender_address:
            sender = message.sender_address
        else:
            sender = f"{message.sender_name or 'system'}@{host}".replace(" ", "_")

        if message.is_draft:
            recipients = ""
        elif message.to_login:
            recipients = f"{message.to_login}@{host}"
        else:
            recipients = f"*@{host}" if machine else "*"

        message.sender = sender
        message.recipients = recipients
        message.status = "draft" if message.is_draft else "ok"

        if message.status_note:
            message.body = f"> {message.status_note}\n\n{message.body}"

        if message.delivery == "trigger" and not message.slug:
            message.slug = f"letter-{message.pk}"

        message.save()

    for task in Task.objects.select_related("machine"):
        profile = Profile.objects.filter(machine=task.machine, login__iexact=task.login).first()

        if profile is None:
            task.delete()
            continue

        task.profile = profile
        task.recipients = f"{task.to_login}@{_host(task.machine)}"
        task.save()


class Migration(migrations.Migration):

    dependencies = [
        ("mail", "0006_addresses_add"),
    ]

    operations = [
        migrations.RunPython(convert, migrations.RunPython.noop),
    ]
