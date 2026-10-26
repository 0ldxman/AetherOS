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

    def test_files_group_is_one_frame_with_rows(self):
        html = render('::files title="Приложения"\nrep-1 | Отчёт\n::\n')
        self.assertIn("widget--files", html)
        self.assertEqual(html.count('class="files-row"'), 1)
        self.assertIn("files-head", html)
        self.assertIn("Приложения", html)
        self.assertIn("Отчёт", html)

    def test_map_embeds_live_and_still_addresses(self):
        html = render("::map lat=48.8 lon=2.3 zoom=5 date=2041-03-12 caption=Порт\n::\n")
        self.assertIn("widget--map", html)
        self.assertIn("embed=1", html)
        self.assertIn("date=2041-03-12", html)
        self.assertIn("static=1#5/48.8/2.3", html)
        self.assertIn("Порт", html)
        self.assertIn("map-stamp", html)
        self.assertIn("map-north", html)
        self.assertIn("map-scale", html)

    def test_map_ignores_a_bad_date_and_clamps_the_view(self):
        html = render("::map lat=999 lon=1 date=tomorrow\n::\n")
        self.assertNotIn("date=", html)
        self.assertIn("/85/", html)

    def test_map_markers_go_to_the_url_and_the_legend(self):
        html = render("::map lat=48 lon=2\nПорт | 48.8 2.3\nСклад | 48.9, 2.4\nмусор\n::\n")
        self.assertIn("m=48.8,2.3,%D0%9F%D0%BE%D1%80%D1%82", html)
        self.assertEqual(html.count("map-legend-marker"), 2)
        self.assertIn("<b>2</b>Склад", html)

    def test_map_regions_come_from_database_codes(self):
        from map.models import Province

        Province.objects.create(code="RUS-32", source_code="RUS-2400", name="Алтай")
        html = render('::map regions="RUS-32 XXX-1"\n::\n')
        self.assertIn("regions=RUS-2400", html)
        self.assertNotIn("XXX-1", html)
        self.assertIn("map-legend-region", html)
        self.assertIn("Алтай", html)
        # вид подобран по рамке провинции
        self.assertIn("static=1#", html)
        self.assertNotIn("#2/20/10", html)

    def test_lint_flags_unknown_regions(self):
        from map.models import Province

        Province.objects.create(code="RUS-32", source_code="RUS-2400", name="Алтай")
        self.assertEqual(codes('::map regions="RUS-32 NOPE-1"\n::\n'), [(1, "region-missing")])

    def test_lint_checks_the_assets_of_groups(self):
        self.assertEqual(codes("::gallery\npic-1 | a\nnope | b\n::\n"), [(3, "asset-missing")])
        self.assertEqual(codes("::gallery\nrep-1 | a\n::\n"), [(2, "asset-type")])
        self.assertEqual(codes("::files\nrep-1 | a\n::\n"), [])
        self.assertEqual(codes("::map lat=1 lon=2\n::\n"), [])
