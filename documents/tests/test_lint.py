"""Проверка текста записи: структура блоков, ключи, ассеты, ссылки.

Запуск: python manage.py test documents.tests.test_lint
"""

from django.test import TestCase

from assets.models import Asset
from filesystem.testing import key_item
from documents.markup import lint
from wiki.testing import make_document, make_namespace


def codes(text):
    return [(i.line, i.code) for i in lint(text)]


class StructureTests(TestCase):
    def test_clean_text_has_no_issues(self):
        text = "Обычный текст\n\n::box border\nвнутри\n::\n\n::stamp СЕКРЕТНО tone=red\n"
        self.assertEqual(codes(text), [])

    def test_unclosed_spoiler_reported_on_its_opening_line(self):
        self.assertEqual(codes("a\n::spoiler key_a\nскрыто\n"), [(2, "unclosed-block"), (2, "unknown-key")])

    def test_nested_blocks_each_need_a_close(self):
        self.assertEqual(codes("::section 01\n::box\nтекст\n::\n"), [(1, "unclosed-block")])

    def test_stray_close(self):
        self.assertEqual(codes("текст\n::\n"), [(2, "stray-close")])

    def test_single_line_widget_does_not_open_a_block(self):
        self.assertEqual(codes("::stamp ОК\nдальше\n"), [])

    def test_raw_widget_needs_close(self):
        self.assertEqual(codes("::log\nстрока\n"), [(1, "unclosed-block")])

    def test_unknown_widget(self):
        self.assertEqual(codes("::nonsense x=1\n"), [(1, "unknown-widget")])

    def test_code_fence_is_ignored_and_unclosed_fence_reported(self):
        self.assertEqual(codes("```\n::spoiler\n[x]{bad key}\n```\n"), [])
        self.assertEqual(codes("текст\n```\n::box\n"), [(2, "unclosed-fence")])

    def test_inline_code_is_ignored(self):
        self.assertEqual(codes("пример `[x]{bad key}` в тексте"), [])


class KeyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        key_item("key_a")

    def test_known_key_passes_unknown_warns(self):
        text = "::spoiler key_a\nok\n::\n\n::spoiler key_a and ghost\nx\n::\n"
        self.assertEqual(codes(text), [(5, "unknown-key")])

    def test_inline_spoiler_and_grid_cell_conditions(self):
        self.assertEqual(codes("тут [секрет]{ghost} есть"), [(1, "unknown-key")])

    def test_bad_condition_is_an_error(self):
        self.assertEqual(codes("[x]{key_a and}"), [(1, "bad-condition")])
        self.assertEqual(codes("::spoiler\nx\n::\n"), [(1, "bad-condition")])


class AssetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Asset.objects.create(
            name="Theme", slug="theme-01", file_id="f1", viewer_type=Asset.ViewerType.AUDIO,
        )

    def test_known_asset_passes(self):
        self.assertEqual(codes("::audio theme-01 title=\"Тема\"\n"), [])

    def test_missing_asset(self):
        self.assertEqual(codes("::audio nope\n"), [(1, "asset-missing")])

    def test_src_is_required(self):
        self.assertEqual(codes("::audio title=\"Тема\"\n"), [(1, "asset-missing")])

    def test_block_form_reads_src_line(self):
        self.assertEqual(codes("::audio\nsrc: theme-01\n::\n"), [])
        self.assertEqual(codes("::audio\nsrc: nope\n::\n"), [(1, "asset-missing")])

    def test_wrong_widget_for_asset_kind(self):
        self.assertEqual(codes("::video theme-01\n"), [(1, "asset-type")])

    def test_generic_asset_widget_accepts_any_kind(self):
        self.assertEqual(codes("::asset theme-01\n"), [])


class LinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ns = make_namespace("Тех")
        make_document(ns, "Оружие", direct_link="gun")

    def test_existing_targets_pass(self):
        text = "[a](/apps/wiki/Тех/Оружие) [b](/apps/wiki/Тех) [c](/apps/wiki/go/gun/)"
        self.assertEqual(codes(text), [])

    def test_missing_document_warns(self):
        self.assertEqual(codes("[a](/apps/wiki/Тех/Нет)"), [(1, "broken-link")])
        self.assertEqual(codes("[a](/apps/wiki/go/ghost/)"), [(1, "broken-link")])

    def test_percent_encoded_path_is_decoded(self):
        from urllib.parse import quote
        self.assertEqual(codes(f"[a](/apps/wiki/{quote('Тех')}/{quote('Оружие')})"), [])

    def test_external_links_are_not_checked(self):
        self.assertEqual(codes("[a](https://example.com/x) [b](#top)"), [])
