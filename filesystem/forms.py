from django import forms
from django.utils.html import format_html

from filesystem.models import MachineFile
from filesystem.states.registry import registry
from filesystem.states.validators import validate_state_text


class MachineFileForm(forms.ModelForm):
    """Форма админки: поле state проверяется как текст стека слоёв.

    Поле объявлено здесь, а не в модели, поэтому миграция не нужна.
    """

    state = forms.CharField(
        required=False,
        label="State",
        widget=forms.Textarea(
            attrs={
                "rows": 18,
                "cols": 100,
                "style": "font-family: monospace;",
                "spellcheck": "false",
            }
        ),
        validators=[validate_state_text],
        help_text=format_html(
            "Слои стека, первый сверху виден игроку первым. Доступные слои:"
            "<pre>{}</pre>",
            registry.describe(),
        ),
    )

    class Meta:
        model = MachineFile
        fields = "__all__"