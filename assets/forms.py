from django import forms

from assets.models import Asset


class AssetAdminForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = (
            "name",
            "slug",
            "file_id",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["file_id"].widget = forms.HiddenInput()

    def clean_slug(self):
        return (self.cleaned_data.get("slug") or "").strip().lower()