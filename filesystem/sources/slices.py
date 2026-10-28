"""Вырезка (blk): окно в байтах другого файла."""
from filesystem.sources.base import Content, Payload, Source

ADDRESS = "slice"


class SliceSource(Source):
    """Вырезка (blk): окно в байтах источника с тем прогрессом по слоям, какой был при вырезке."""

    name = "slice"

    def accepts(self, address):
        return address.parts == [ADDRESS]

    def payload(self, machine_file, address, keys, reader, viewer):
        from filesystem.models import FileSlice
        from filesystem.rawview.generate import build_raw

        cut = FileSlice.objects.filter(file=machine_file).select_related("source", "source__machine").first()
        if cut is None:
            return Payload()
        data = build_raw(cut.source, cut.state, keys, reader, viewer).data
        return Payload(
            kind="slice", layout="raw", body=data[cut.start:cut.end], stamp=f"slice:{cut.pk}:{cut.source.updated_at.timestamp()}",
        )

    def shows(self, url):
        return url.strip() == ADDRESS

    def window(self, url, path):
        return Content(error="empty")                 # адреса нет, вырезки читаются как байты (cnt -r)
