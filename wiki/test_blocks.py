from django.test import TestCase

from assets.models import Asset
from wiki.markup import render
from wiki.markup.lint import lint


def codes(text):
    return [(i.line, i.code) for i in lint(text)]


class BlocksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.one = Asset.objects.create(name="One", slug="pic-1", file_id="1", viewer_type=Asset.ViewerType.IMAGE)
        cls.two = Asset.objects.create(name="Two", slug="pic-2", file_id="2", viewer_type=Asset.ViewerType.IMAGE)
        cls.doc = Asset.objects.create(name="Report", slug="rep-1", file_id="3", viewer_type=Asset.ViewerType.RAW)

    def test_gallery_renders_each_picture_with_its_caption(self):
        html = render("::gallery cols=3\npic-1 | Вход\npic-2 | Двор\n::\n")
        self.assertIn("widget--gallery", html)
        self.assertIn("gallery--cols-3", html)
        self.assertEqual(html.count('class="gallery-item"'), 2)
        self.assertIn("Вход", html)
        self.assertIn("1 / 2", html)
        self.assertIn(str(self.two.public_id), html)

    def test_gallery_with_unknown_picture_keeps_a_frame(self):
        html = render("::gallery\nnope | Нет такой\n::\n")
        self.assertEqual(html.count('class="gallery-item"'), 1)
        self.assertIn("image-missing", html)

    def test_gallery_caption_is_escaped(self):
        html = render('::gallery\npic-1 | <script>x</script>\n::\n')
        self.assertNotIn("<script>x", html)

    def test_empty_gallery_renders_nothing(self):
        self.assertNotIn("widget--gallery", render("::gallery\n\n::\n"))

    def test_files_group_reuses_the_file_widget(self):
        html = render('::files title="Приложения"\nrep-1 | Отчёт\n::\n')
        self.assertIn("widget--files", html)
        self.assertIn("widget--file", html)
        self.assertIn("Приложения", html)
        self.assertIn("Отчёт", html)

    def test_map_embeds_live_and_still_addresses(self):
        html = render("::map lat=48.8 lon=2.3 zoom=5 date=2041-03-12 caption=Порт")
        self.assertIn("widget--map", html)
        self.assertIn("embed=1", html)
        self.assertIn("date=2041-03-12", html)
        self.assertIn("static=1#5/48.8/2.3", html)
        self.assertIn("Порт", html)

    def test_map_ignores_a_bad_date_and_clamps_the_view(self):
        html = render("::map lat=999 date=tomorrow")
        self.assertNotIn("date=", html)
        self.assertIn("/85/", html)

    def test_lint_checks_the_assets_of_groups(self):
        self.assertEqual(codes("::gallery\npic-1 | a\nnope | b\n::\n"), [(3, "asset-missing")])
        self.assertEqual(codes("::gallery\nrep-1 | a\n::\n"), [(2, "asset-type")])
        self.assertEqual(codes("::files\nrep-1 | a\n::\n"), [])
        self.assertEqual(codes("::map lat=1 lon=2\n"), [])
