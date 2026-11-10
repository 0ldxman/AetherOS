from django.test import SimpleTestCase, TestCase

from desktop import icons
from filesystem import appfile
from filesystem.testing import make_app
from machines.world.styles import STYLES


class PackTests(SimpleTestCase):
    def test_every_style_with_pictures_has_every_icon_of_the_catalog(self):
        for style in STYLES:
            if style in icons.TEXT_ONLY:
                self.assertEqual(icons.icon_url(style, "terminal"), "")
                continue
            for name in icons.NAMES:
                self.assertTrue(icons.icon_url(style, name).endswith(f"/{icons.pack_of(style)}/{name}.svg"), (style, name))

    def test_the_glitched_style_takes_the_pack_of_aether_and_unknown_names_have_no_picture(self):
        self.assertIn("/aether/", icons.icon_url("glitched", "mail"))
        self.assertEqual(icons.icon_url("aether", "no-such-icon"), "")
        self.assertEqual(icons.glyph("no-such-icon"), icons.glyph("app"))

    def test_the_text_of_a_glyph_fits_the_old_limit(self):
        self.assertTrue(all(len(text) <= 8 for text in icons.ASCII.values()))


class AppFileTests(SimpleTestCase):
    def test_an_app_names_an_icon_of_the_catalog(self):
        self.assertEqual(appfile.parse("label a\nicon Mail\npath /apps/mail/\n").icon, "mail")
        with self.assertRaises(Exception) as caught:
            appfile.parse("label a\nicon sparkles\npath /apps/mail/\n")
        self.assertIn("каталоге", str(caught.exception))
        with self.assertRaises(Exception):
            appfile.parse("label a\nglyph W\npath /apps/mail/\n")             # значка-текста больше нет: нужна иконка

    def test_the_text_round_trips(self):
        text = appfile.render("console", "terminal", "/apps/terminal/", ".sh", 3)
        spec = appfile.parse(text)
        self.assertEqual((spec.label, spec.icon, spec.suffix, spec.order), ("console", "terminal", ".sh", 3))
