from django import forms
from django.utils.html import format_html

from filesystem.models import FileEncoding, FileFormat
from filesystem.states.registry import registry
from filesystem.states.validators import validate_state_text


def _check_hex(text, label):
    try:
        bytes.fromhex(text or "")
    except ValueError:
        raise forms.ValidationError(f"{label}: только hex-байты через пробел, например 9e 53 43 41")


def _check_template(text, label):
    import string

    from filesystem.rawview.formats import PLACEHOLDERS, _Context

    try:
        used = [name for _, name, _, _ in string.Formatter().parse(text or "") if name]
        unknown = [name for name in used if name not in PLACEHOLDERS]
        if unknown:
            raise forms.ValidationError(
                f"{label}: нет подстановки {{{unknown[0]}}}. Есть: " + ", ".join("{" + name + "}" for name in PLACEHOLDERS)
            )
        string.Formatter().vformat(text or "", (), _Context())
    except forms.ValidationError:
        raise
    except (ValueError, IndexError, KeyError) as exc:
        raise forms.ValidationError(f"{label}: шаблон не разбирается ({exc}); фигурные скобки текста удваиваются: {{{{ }}}}")


class FileFormatForm(forms.ModelForm):
    class Meta:
        model = FileFormat
        fields = "__all__"

    def _check_aliases(self, data):
        """Псевдоним не должен совпадать с именем или псевдонимом другого формата, а расширение с чужим."""
        from filesystem.rawview.registry import aliases

        mine = {data.get("name", "")} | set(aliases(data.get("aliases", "")))
        taken = {}
        for item in FileFormat.objects.exclude(pk=self.instance.pk):
            for word in {item.name, *aliases(item.aliases), item.extension.lstrip(".").lower()} - {""}:
                taken[word] = item.name
        clash = sorted(word for word in mine - {""} if word in taken)
        if clash:
            self.add_error("aliases", f"«{clash[0]}» уже занят форматом {taken[clash[0]]}.")

    def clean_name(self):
        return self.cleaned_data["name"].strip().lower()

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        magic = data.get("magic", "")
        self._check_aliases(data)
        try:
            _check_hex(magic, "Сигнатура")
        except forms.ValidationError as exc:
            self.add_error("magic", exc)
            return data

        if kind in ("signature", "chunks", "package") and not magic.strip():
            self.add_error("magic", "Для этого вида нужна сигнатура.")
        if kind == "text":
            if not data.get("template", "").strip():
                self.add_error("template", "Для текстового шаблона нужен шаблон.")
            else:
                try:
                    _check_template(data["template"], "Шаблон")
                except forms.ValidationError as exc:
                    self.add_error("template", exc)
        return data


class FormatPartFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        kind = self.instance.kind if self.instance and self.instance.pk else self.data.get("kind", "")
        live = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]

        if kind in ("chunks", "package", "zip") and not live and not self.errors:
            raise forms.ValidationError("Для блоков и пакета нужна хотя бы одна часть.")

        for form in live:
            name, source, value = (form.cleaned_data.get(k, "") for k in ("name", "source", "value"))
            if kind == "chunks" and len(name) != 4:
                form.add_error("name", "Метка блока ровно 4 символа.")
            if kind == "package" and len(name) > 8:
                form.add_error("name", "Имя части пакета до 8 символов.")
            if not name.isascii():
                form.add_error("name", "Только латиница и цифры.")
            try:
                if source == "hex":
                    _check_hex(value, "Значение")
                elif source == "template":
                    _check_template(value, "Значение")
                elif source == "noise":
                    int(value or 0)
            except forms.ValidationError as exc:
                form.add_error("value", exc)
            except ValueError:
                form.add_error("value", "Для шума нужна длина числом.")


class FileEncodingForm(forms.ModelForm):
    class Meta:
        model = FileEncoding
        fields = "__all__"

    def clean_name(self):
        return self.cleaned_data["name"].strip().lower()

    def clean(self):
        from filesystem.rawview.encodings import valid_param

        data = super().clean()
        if data.get("kind"):
            error = valid_param(data["kind"], data.get("param", ""))
            if error:
                self.add_error("param", error)
        return data

