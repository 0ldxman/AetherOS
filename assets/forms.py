from django import forms

from .models import Asset


class AssetAdminForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = (
            "name",
            "file_id",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["file_id"].widget = forms.HiddenInput()