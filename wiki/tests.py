import contextlib
import io
import runpy
from pathlib import Path

from django.test import SimpleTestCase

from wiki.access import document_state, namespace_state
from wiki.markup import MASK_CHAR, render, visible_text
from wiki.models import Document, Namespace


def ns(name, parent=None, visibility=None, access=None):
    """Неймспейс в памяти: chain() ходит по parent, база не нужна."""
    return Namespace(
        name=name,
        parent=parent,
        visibility=visibility or "",
        access=access or "",
    )


def doc(namespace, visibility=None, access=None):
    return Document(
        namespace=namespace,
        title="d",
        visibility=visibility or "",
        access=access or "",
    )


class AccessTests(SimpleTestCase):
    def test_open_by_default(self):
        state = namespace_state(ns("a"), frozenset())
        self.assertTrue(state.visible and state.open)

    def test_condition_is_inherited_down_the_chain(self):
        root = ns("root", access="key")
        child = ns("child", parent=root)
        leaf = doc(child)

        self.assertFalse(namespace_state(child, frozenset()).open)
        self.assertFalse(document_state(leaf, frozenset()).open)
        self.assertTrue(document_state(leaf, {"key"}).open)

    def test_hidden_parent_hides_document(self):
        root = ns("root", visibility="key")
        leaf = doc(ns("child", parent=root))

        self.assertFalse(document_state(leaf, frozenset()).visible)
        self.assertTrue(document_state(leaf, {"key"}).visible)

    def test_document_conditions_apply_on_top_of_namespace(self):
        leaf = doc(ns("a"), visibility="v", access="k")

        state = document_state(leaf, frozenset())
        self.assertFalse(state.visible or state.open)
        state = document_state(leaf, {"v", "k"})
        self.assertTrue(state.visible and state.open)

    def test_direct_link_bypasses_only_visibility(self):
        leaf = doc(ns("a"), visibility="v", access="k")

        state = document_state(leaf, frozenset(), via_direct_link=True)
        self.assertTrue(state.visible)
        self.assertFalse(state.open)


def spoiler(expr, body="Секретный текст"):
    return f"до\n\n::spoiler {expr}\n{body}\n::\n\nпосле"


class MarkupSecurityTests(SimpleTestCase):
    def test_raw_html_is_escaped(self):
        html = render("<script>alert(1)</script>")
        self.assertNotIn("<script>", html)

    def test_javascript_links_are_not_links(self):
        self.assertNotIn("<a ", render("[x](javascript:alert(1))"))

    def test_closed_spoiler_hides_text_and_key(self):
        html = render(spoiler("key_a"), keys=set())
        self.assertNotIn("Секрет", html)
        self.assertNotIn("key_a", html)
        self.assertIn(MASK_CHAR, html)

    def test_closed_spoiler_hides_link_target_and_image(self):
        html = render(
            spoiler("k", "[t](https://secret.example/x) ![i](https://secret.example/i.png)"),
            keys=set(),
        )
        self.assertNotIn("secret.example", html)
        self.assertNotIn("<img", html)

    def test_open_spoiler_shows_text(self):
        html = render(spoiler("key_a"), keys={"key_a"})
        self.assertIn("Секретный текст", html)
        self.assertNotIn("key_a", html)

    def test_expression_is_evaluated(self):
        body = spoiler("a and not b")
        self.assertIn("Секретный", render(body, keys={"a"}))
        self.assertNotIn("Секретный", render(body, keys={"a", "b"}))

    def test_visible_text_skips_closed_spoilers(self):
        text = spoiler("k", "пароль") + "\n\nпубличное"
        closed = visible_text(text, frozenset())
        self.assertNotIn("пароль", closed)
        self.assertIn("публичное", closed)
        self.assertIn("пароль", visible_text(text, {"k"}))


class LegacyMarkupChecksTests(SimpleTestCase):
    """Прогоняет старый скрипт wiki/check_markup.py: его проверок больше сотни."""

    def test_no_failures(self):
        out = io.StringIO()
        script = Path(__file__).with_name("check_markup.py")
        with contextlib.redirect_stdout(out):
            runpy.run_path(str(script), run_name="check_markup")
        failed = [l for l in out.getvalue().splitlines() if l.startswith("FAIL")]
        self.assertEqual(failed, [])
