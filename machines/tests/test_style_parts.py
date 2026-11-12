import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase

from machines.world import styles

PARTS_DIR = Path(settings.BASE_DIR) / "static" / "ui" / "parts"


class StylePartFilesTests(SimpleTestCase):
    def test_part_files_use_only_their_own_attribute(self):
        """Файл части включается только своим атрибутом: панель не зависит от стиля стола и т. д."""
        for part in styles.PARTS:
            for path in (PARTS_DIR / part).glob("*.css"):
                text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
                kinds = set(re.findall(r"\[data-(theme|win-[a-z]+|notice|panel|dock)=", text))
                self.assertEqual(kinds, {part}, path)

    def test_every_part_file_belongs_to_a_known_part_and_style(self):
        for path in PARTS_DIR.glob("*/*.css"):
            self.assertIn(path.parent.name, styles.PARTS, path)
            self.assertIn(path.stem, styles.STYLES, path)

    def test_windows_css_knows_every_variant_and_nothing_else(self):
        """Каждый вариант окна из WINDOW чем-то нарисован (кроме основы из desktop.css), и в CSS нет неизвестных."""
        text = re.sub(r"/\*.*?\*/", "", (PARTS_DIR / "windows.css").read_text(), flags=re.S)
        used = set(re.findall(r'\[data-win-([a-z]+)="([a-z]+)"\]', text))
        known = {(key, value) for key, (_, options) in styles.WINDOW.items() for value in options}
        self.assertEqual(used - known, set())
        base = {("title", "tab"), ("frame", "line"), ("side", "left"), ("buttons", "icons"), ("set", "all")}
        self.assertEqual(known - used - base, set())
        self.assertNotIn("data-theme", text)

    def test_every_style_has_a_full_window_preset(self):
        for slug in styles.STYLES:
            preset = styles.window_of(slug)
            self.assertEqual(set(preset), set(styles.WINDOW), slug)
            for key, value in preset.items():
                self.assertIn(value, styles.WINDOW[key][1], (slug, key))

    def test_author_choice_goes_over_the_preset(self):
        self.assertEqual(styles.window_of("classic", {"window": {"title": "tab", "bogus": "x", "side": "up"}})["title"], "tab")
        self.assertEqual(styles.window_of("classic", {"window": {"side": "up"}})["side"], "right")
        self.assertEqual(styles.clean_parts({"window": {"title": "nope"}}), {})
        self.assertEqual(styles.parts_problems({"window": {"title": "nope", "size": "l"}}), ["Заголовок: нет варианта «nope».", "У окон нет параметра size."])


class StylePartTagsTests(TestCase):
    def render(self, text, **query):
        request = RequestFactory().get("/", query)
        request.user, request.session = AnonymousUser(), {}
        return Template("{% load os_style %}" + text).render(Context({"request": request}))

    def setUp(self):
        from machines.models import Machine, SystemType

        SystemType.objects.filter(code="AETHER").update(style="classic", style_parts={"window": {"buttons": "circles"}})
        Machine.objects.create(name="Main", hostname="aether-main")

    def test_html_gets_part_attributes(self):
        self.assertEqual(self.render("{% os_parts %}"),
                         ' data-win-title="plaque" data-win-frame="hard" data-win-side="right" data-win-buttons="circles" data-win-set="all"'
                         ' data-notice="classic" data-panel="classic" data-dock="classic" data-panel-edge="top" data-panel-form="bar"')

    def test_links_windows_before_parts(self):
        links = self.render("{% os_theme %}")
        order = [links.index(name) for name in ("ui/themes/classic.css", "ui/parts/windows.css", "ui/parts/notice/classic.css", "ui/parts/panel/classic.css")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("ui/parts/dock/classic.css", links)           # у Classic своего дока нет

    def test_preview_parts_only_for_staff(self):
        html = self.render("{% os_parts %}", preview_parts=json.dumps({"window": {"title": "full"}}))
        self.assertIn('data-win-title="plaque"', html)                 # аноним не подменяет
