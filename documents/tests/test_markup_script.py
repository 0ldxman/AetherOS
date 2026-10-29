import contextlib
import io
import runpy
from pathlib import Path

from django.test import SimpleTestCase


class LegacyMarkupChecksTests(SimpleTestCase):
    """Прогоняет старый скрипт documents/tests/check_markup.py: его проверок больше сотни."""

    def test_no_failures(self):
        out = io.StringIO()
        script = Path(__file__).with_name("check_markup.py")
        with contextlib.redirect_stdout(out):
            runpy.run_path(str(script), run_name="check_markup")
        failed = [l for l in out.getvalue().splitlines() if l.startswith("FAIL")]
        self.assertEqual(failed, [])
