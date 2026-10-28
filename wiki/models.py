from django.core.exceptions import ValidationError


def validate_no_colon(value):
    # остался для старых миграций: двоеточие разделяло путь в ссылках
    if ":" in value:
        raise ValidationError("Двоеточие в названии запрещено: оно разделяет путь.")
