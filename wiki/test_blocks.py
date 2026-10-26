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
        self.assertIn("m=48.8,2.3,,,,%D0%9F%D0%BE%D1%80%D1%82", html)
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

    def test_map_mode_and_province_names_are_options(self):
        html = render("::map lat=50 lon=19 zoom=5 mode=physical labels=off\n::\n")
        self.assertIn("mode=physical", html)
        self.assertIn("labels=0", html)
        self.assertNotIn("labels=0", render("::map lat=50 lon=19 zoom=5\n::\n"))

    def test_highlight_accepts_provinces_countries_and_exclusions(self):
        from datetime import date

        from map.models import Country, Ownership, Province

        a = Province.objects.create(code="POL-1", source_code="POL-3146", name="Силезия")
        b = Province.objects.create(code="POL-2", source_code="POL-3170", name="Малая Польша")
        c = Province.objects.create(code="DEU-1", source_code="DEU-1", name="Бавария")
        pol = Country.objects.create(code="POL-2013", name="Польша", valid_from=date(2013, 1, 1))
        deu = Country.objects.create(code="DEU-2013", name="Германия", valid_from=date(2013, 1, 1))
        for province, country in ((a, pol), (b, pol), (c, deu)):
            Ownership.objects.create(province=province, country=country, date_from=date(2013, 1, 1), de_jure=True)

        html = render("::map highlight=POL,-POL-2\n::\n")
        self.assertIn("regions=POL-3146&", html + "&")
        self.assertNotIn("POL-3170", html)
        self.assertNotIn("DEU-1", html)
        self.assertIn("Польша", html)
        # страна по названию, провинция по коду
        html = render("::map highlight=Германия,POL-2\n::\n")
        self.assertIn("DEU-1", html)
        self.assertIn("POL-3170", html)

    def test_country_follows_the_owner_on_the_date(self):
        from datetime import date

        from map.models import Country, Ownership, Province

        p = Province.objects.create(code="POL-1", source_code="POL-3146", name="Силезия")
        pol = Country.objects.create(code="POL-2013", name="Польша", valid_from=date(2013, 1, 1))
        deu = Country.objects.create(code="DEU-2030", name="Германия", valid_from=date(2030, 1, 1))
        Ownership.objects.create(province=p, country=pol, date_from=date(2013, 1, 1), de_jure=True)
        Ownership.objects.create(province=p, country=deu, date_from=date(2030, 1, 1), de_jure=True)
        self.assertIn("POL-3146", render("::map highlight=POL date=2020-01-01\n::\n"))
        self.assertNotIn("POL-3146", render("::map highlight=POL date=2035-01-01\n::\n"))
        self.assertIn("POL-3146", render("::map highlight=Германия date=2035-01-01\n::\n"))

    def test_marker_and_highlight_colors(self):
        from datetime import date

        from map.models import Country, Ownership, Province

        p = Province.objects.create(code="POL-1", source_code="POL-3146", name="Силезия")
        pol = Country.objects.create(code="POL-2013", name="Польша", valid_from=date(2013, 1, 1))
        Ownership.objects.create(province=p, country=pol, date_from=date(2013, 1, 1), de_jure=True)

        html = render("::map highlight=POL:blue lat=50 lon=19 zoom=5\nКраков | 50 19 синий\nДом | 51 20\n::\n")
        self.assertIn("regions=POL-3146:blue", html)
        self.assertIn("m=50.0,19.0,blue,", html)
        self.assertIn("m=51.0,20.0,,", html)
        self.assertIn('class="map-legend-marker" data-color="blue"', html)
        self.assertIn('class="map-legend-region" data-color="blue"', html)

    def test_a_province_in_two_tokens_takes_the_last_color_once(self):
        from datetime import date

        from map.models import Country, Ownership, Province

        a = Province.objects.create(code="POL-1", source_code="POL-3146", name="Силезия")
        b = Province.objects.create(code="POL-2", source_code="POL-3170", name="Малая Польша")
        pol = Country.objects.create(code="POL-2013", name="Польша", valid_from=date(2013, 1, 1))
        for province in (a, b):
            Ownership.objects.create(province=province, country=pol, date_from=date(2013, 1, 1), de_jure=True)
        html = render("::map highlight=POL:blue,POL-2:red\n::\n")
        self.assertEqual(html.count("POL-3170"), 2)        # живой и статичный адрес, по разу
        self.assertIn("POL-3170:red", html)
        self.assertNotIn("POL-3170:blue", html)
        self.assertIn("POL-3146:blue", html)

    def test_unknown_color_is_ignored_by_render_and_flagged_by_lint(self):
        html = render("::map lat=1 lon=2\nТочка | 1 2 розовый\n::\n")
        self.assertIn("m=1.0,2.0,,", html)
        self.assertEqual(codes("::map lat=1 lon=2\nТочка | 1 2 розовый\n::\n"), [(2, "map-color")])
        self.assertEqual(codes("::map highlight=POL:розовый\n::\n")[0][1], "map-color")

    def test_marker_palette_matches_between_map_and_legend(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        js = (root / "map/static/map.js").read_text(encoding="utf-8")
        css = (root / "wiki/static/wiki/blocks.css").read_text(encoding="utf-8")
        for theme, selector in (
            ("scan", '.widget--map[data-theme="scan"], .widget--map:not([data-theme]) {'),
            ("maps", '.widget--map[data-theme="maps"] {'),
            ("dark", '.widget--map[data-theme="dark"] {'),
        ):
            palette = js[js.index("const MARK_COLORS"):js.index("const markPalette")]
            block = re.search(theme + r": \{(.*?)\},", palette, re.S).group(1)
            wanted = dict(re.findall(r"(\w+): '(#[0-9a-f]{6})'", block))
            start = css.index(selector, css.index("цвета выделения и меток"))
            shown = dict(re.findall(r"--mc-(\w+): (#[0-9a-f]{6});", css[start:css.index("}", start)]))
            self.assertEqual(wanted, shown, theme)

    def _poland_czechia(self):
        from datetime import date

        from map.models import Country, Ownership, Province

        data = (("POL", "Польша", ("POL-1", "POL-3146"), ("POL-2", "POL-3170")),
                ("CZE", "Чехия", ("CZE-1", "CZE-1001"), ("CZE-3", "CZE-1003")),
                ("DEU", "Германия", ("DEU-1", "DEU-1")))
        for prefix, name, *provinces in data:
            country = Country.objects.create(code=prefix + "-2013", name=name, valid_from=date(2013, 1, 1))
            for code, source in provinces:
                province = Province.objects.create(code=code, source_code=source, name=code)
                Ownership.objects.create(province=province, country=country, date_from=date(2013, 1, 1), de_jure=True)

    def test_body_lines_set_highlights_colors_and_exclusions(self):
        self._poland_czechia()
        html = render("::map date=2041-03-12\nPOL blue\nCZE green\nexcept CZE-3\nКраков | 50 19 red\n::\n")
        self.assertIn("POL-3146:blue", html)
        self.assertIn("CZE-1001:green", html)
        self.assertNotIn("CZE-1003", html)
        self.assertIn("m=50.0,19.0,red,", html)

    def test_minus_is_the_short_form_of_except_and_commas_group_items(self):
        self._poland_czechia()
        html = render("::map\nPOL blue, CZE green\n-CZE-3\n::\n")
        self.assertIn("POL-3170:blue", html)
        self.assertIn("CZE-1001:green", html)
        self.assertNotIn("CZE-1003", html)

    def test_highlights_without_colors_get_different_colors(self):
        self._poland_czechia()
        html = render("::map\nPOL\nCZE\nDEU\n::\n")
        colors = {c for c in ("red", "blue", "green", "orange", "purple") if f":{c}" in html}
        self.assertEqual(len(colors), 3)
        # одно выделение остаётся цвета темы
        self.assertNotIn("POL-3146:", render("::map\nPOL\n::\n"))

    def test_explicit_colors_are_not_reused_by_auto_colors(self):
        self._poland_czechia()
        html = render("::map\nPOL red\nCZE\nDEU\n::\n")
        self.assertIn("POL-3146:red", html)
        self.assertNotIn("CZE-1001:red", html)
        self.assertNotIn("DEU-1:red", html)

    def test_old_header_syntax_still_works(self):
        self._poland_czechia()
        html = render('::map highlight="POL:blue CZE:green -CZE-3"\n::\n')
        self.assertIn("POL-3146:blue", html)
        self.assertNotIn("CZE-1003", html)

    def test_lint_checks_body_lines(self):
        self._poland_czechia()
        self.assertEqual(codes("::map\nPOL blue\nexcept CZE-3\nКраков | 1 2 red\n::\n"), [])
        self.assertEqual(codes("::map\nPOL blue\nNOPE\n::\n"), [(3, "region-missing")])
        self.assertEqual(codes("::map\nexcept NOPE-1\n::\n"), [(2, "region-missing")])
        self.assertEqual(codes("::map\nТочка | 1 2 розовый\n::\n"), [(2, "map-color")])

    def _scene(self, **fields):
        from map.models import MapScene

        data = dict(slug="raid", title="Рейд", lat=50, lon=19, zoom=5, features=[
            {"type": "marker", "coords": [19.9, 50.0], "label": "Краков", "url": "Technologies/Report"},
            {"type": "arrow", "coords": [[19, 50], [21, 52]], "color": "red"},
            {"type": "marker", "coords": [10, 10], "label": "Тайник", "key": "secret"},
        ])
        data.update(fields)
        return MapScene.objects.create(**data)

    def test_scene_widget_uses_the_scene_camera_and_embeds_visible_features(self):
        import json
        from html import unescape

        from datetime import date

        self._scene(bounds=[10, 40, 30, 60], min_zoom=3, max_zoom=9, flat=True, base_date=date(2029, 2, 12))
        html = render("::map scene=raid\n::\n")
        self.assertIn("date=2029-02-12", html)
        self.assertIn("bounds=10,40,30,60", html)
        self.assertIn("minzoom=3", html)
        self.assertIn("maxzoom=9", html)
        self.assertIn("flat=1", html)
        self.assertIn("#5/50/19", html)
        self.assertIn("Рейд", html)                       # подпись по умолчанию из названия сцены
        features = json.loads(unescape(html.split('data-scene="')[1].split('"')[0]))
        self.assertEqual([f["type"] for f in features], ["marker", "arrow"])      # секретная метка не попала
        self.assertTrue(features[0]["url"].endswith("Technologies/Report"))
        self.assertNotIn("Тайник", html)

    def test_scene_features_follow_the_date_of_the_map(self):
        self._scene(features=[
            {"type": "marker", "coords": [1, 1], "label": "Раньше", "to": "2030-01-01"},
            {"type": "marker", "coords": [2, 2], "label": "Позже", "from": "2040-01-01"},
        ])
        self.assertIn("Раньше", render("::map scene=raid date=2029-02-12\n::\n"))
        self.assertNotIn("Позже", render("::map scene=raid date=2029-02-12\n::\n"))
        self.assertIn("Позже", render("::map scene=raid date=2041-02-12\n::\n"))
        self.assertNotIn("Раньше", render("::map scene=raid date=2041-02-12\n::\n"))

    def test_scene_secret_feature_appears_with_the_key(self):
        self._scene()
        html = render("::map scene=raid\n::\n", keys={"secret"})
        self.assertIn("Тайник", html)

    def test_restricted_or_missing_scene_shows_a_placeholder(self):
        self._scene(key_condition="secret")
        self.assertIn("MAP RESTRICTED", render("::map scene=raid\n::\n"))
        self.assertNotIn("data-scene", render("::map scene=raid\n::\n"))
        self.assertIn("data-scene", render("::map scene=raid\n::\n", keys={"secret"}))
        self.assertIn("MAP NOT FOUND", render("::map scene=nope\n::\n"))

    def test_header_overrides_the_scene_and_lines_add_on_top(self):
        self._scene(flat=False)
        html = render("::map scene=raid lat=1 lon=2 zoom=7 flat=on caption=Своё\nМетка | 3 4 red\n::\n")
        self.assertIn("#7/1/2", html)
        self.assertIn("flat=1", html)
        self.assertIn("Своё", html)
        self.assertIn("m=3.0,4.0,red,", html)

    def test_inline_links_are_normalized_and_unsafe_ones_dropped(self):
        html = render("::map lat=1 lon=2\nА | 1 2 -> Technologies/Report\nБ | 3 4 -> javascript:alert(1)\n::\n")
        self.assertIn("Technologies%2FReport", html)
        self.assertEqual(html.count("javascript"), 0)

    def test_marker_icons_in_lines_in_any_order_with_colors(self):
        html = render("::map lat=1 lon=2\nА | 1 2 star red\nБ | 3 4 синий ромб\nВ | 5 6 triangle\nГ | 7 8 розовый\n::\n")
        self.assertIn("m=1.0,2.0,red,star,", html)
        self.assertIn("m=3.0,4.0,blue,diamond,", html)
        self.assertIn("m=5.0,6.0,,triangle,", html)
        self.assertIn("m=7.0,8.0,,,", html)                     # неизвестное слово не теряет метку
        self.assertEqual(codes("::map lat=1 lon=2\nА | 1 2 star red\n::\n"), [])
        self.assertEqual(codes("::map lat=1 lon=2\nГ | 7 8 розовый\n::\n"), [(2, "map-color")])

    def test_scene_marker_icon_is_validated(self):
        from django.core.exceptions import ValidationError

        from map.scenes import clean_features

        self.assertEqual(clean_features([{"type": "marker", "coords": [1, 2], "icon": "star"}])[0]["icon"], "star")
        with self.assertRaises(ValidationError):
            clean_features([{"type": "marker", "coords": [1, 2], "icon": "bomb"}])

    def test_lint_flags_unknown_scene(self):
        self._scene()
        self.assertEqual(codes("::map scene=raid\n::\n"), [])
        self.assertEqual(codes("::map scene=nope\n::\n"), [(1, "scene-missing")])

    def test_callouts_in_lines(self):
        import json
        from urllib.parse import unquote

        html = render("::map\nnote Склад \\n у реки | 50.1 19.9 +80 -40 blue -> Technologies/Report\nвыноска Пост | 51 20\n::\n")
        import re

        first, second = [json.loads(unquote(v)) for v in re.findall(r'&amp;c=([^&"#]+)', html)[:2]]
        self.assertEqual(first["text"], "Склад\nу реки")
        self.assertEqual((first["offset"], first["color"]), ([80, -40], "blue"))
        self.assertTrue(first["url"].endswith("Technologies/Report"))
        self.assertEqual((second["offset"], second["color"], second["text"]), ([70, -50], "", "Пост"))
        self.assertIn("#", html)                                   # вид подобран по выноскам
        self.assertEqual(codes("::map\nnote А | 1 2 blue\n::\n"), [])
        self.assertEqual(codes("::map\nnote А | 1 2 розовый\n::\n"), [(2, "map-color")])

    def test_lint_flags_unknown_regions(self):
        from map.models import Province

        Province.objects.create(code="RUS-32", source_code="RUS-2400", name="Алтай")
        self.assertEqual(codes('::map regions="RUS-32 NOPE-1"\n::\n'), [(1, "region-missing")])

    def test_lint_checks_the_assets_of_groups(self):
        self.assertEqual(codes("::gallery\npic-1 | a\nnope | b\n::\n"), [(3, "asset-missing")])
        self.assertEqual(codes("::gallery\nrep-1 | a\n::\n"), [(2, "asset-type")])
        self.assertEqual(codes("::files\nrep-1 | a\n::\n"), [])
        self.assertEqual(codes("::map lat=1 lon=2\n::\n"), [])
