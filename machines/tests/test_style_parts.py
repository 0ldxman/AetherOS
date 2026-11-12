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
        """Файл части включается только своим атрибутом: окна не зависят от стиля стола, панель от окон и т. д."""
        for part in styles.PARTS:
            for path in (PARTS_DIR / part).glob("*.css"):
                text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
                self.assertNotIn("data-theme", text, path)
                kinds = set(re.findall(r"\[data-(theme|window|notice|panel|dock)=", text))
                self.assertEqual(kinds, {part}, path)

    def test_every_part_file_belongs_to_a_known_part_and_style(self):
        for path in PARTS_DIR.glob("*/*.css"):
            self.assertIn(path.parent.name, styles.PARTS, path)
            self.assertIn(path.stem, styles.STYLES, path)

    def test_part_file_is_empty_for_missing_kind(self):
        self.assertEqual(styles.part_file("window", "aether"), "")
        self.assertEqual(styles.part_file("window", "classic"), "ui/parts/window/classic.css")


class StylePartTagsTests(TestCase):
    def render(self, text):
        request = RequestFactory().get("/")
        request.user, request.session = AnonymousUser(), {}
        return Template("{% load os_style %}" + text).render(Context({"request": request}))

    def test_html_gets_part_attributes_and_links(self):
        from machines.models import Machine, SystemType

        SystemType.objects.filter(code="AETHER").update(style="classic")
        Machine.objects.create(name="Main", hostname="aether-main")
        self.assertEqual(self.render("{% os_parts %}"), ' data-window="classic" data-notice="classic" data-panel="classic" data-dock="classic"')
        links = self.render("{% os_theme %}")
        self.assertIn("ui/themes/classic.css", links)
        self.assertIn("ui/parts/window/classic.css", links)
        self.assertIn("ui/parts/panel/classic.css", links)
        self.assertNotIn("ui/parts/dock/classic.css", links)           # у Classic своего дока нет
