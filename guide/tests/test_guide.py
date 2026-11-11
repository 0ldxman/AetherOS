"""Справка автора: страницы docs/guide, рендер с картинками и видео, поиск, отдача медиа, права.

Запуск: python manage.py test guide
"""
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from guide import pages

PAGE = """---
title: Граф сценария
section: Почта
order: 20
---
# Граф сценария

Вступление про шаги.

![Карта шагов](shot:graph)

## Песочница

Проба ответов без записи в мир. См. [начало](page:start).

![Прогон](clip:sandbox)
"""


class Base(TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        (root / "media").mkdir()
        (root / "mail-graph.md").write_text(PAGE)
        (root / "start.md").write_text("---\ntitle: Начало\nsection: Основы\norder: 10\n---\nЧто такое AetherOS.\n")
        (root / "bare.md").write_text("Без шапки.\n")
        for patch in (mock.patch.object(pages, "ROOT", root), mock.patch.object(pages, "MEDIA", root / "media")):
            patch.start()
            self.addCleanup(patch.stop)
        self.root = root


class PagesTests(Base):
    def test_order_sections_and_defaults(self):
        self.assertEqual([p.slug for p in pages.pages()], ["start", "mail-graph", "bare"])
        self.assertEqual([title for title, _ in pages.sections()], ["Основы", "Почта", "Прочее"])
        self.assertEqual(pages.get("bare").title, "bare")
        self.assertIsNone(pages.get("nope"))

    def test_missing_media_is_a_placeholder_and_listed(self):
        body, heads = pages.render(pages.get("mail-graph"), lambda name: f"/m/{name}")
        self.assertIn("снимок не сделан: graph", body)
        self.assertIn("видео не сделан: sandbox", body)
        self.assertNotIn("<img", body)
        self.assertEqual(pages.missing_media(), [("mail-graph", "graph.png"), ("mail-graph", "sandbox.webm")])
        self.assertEqual([h["title"] for h in heads], ["Песочница"])

    def test_present_media_becomes_img_and_video(self):
        (self.root / "media" / "graph.png").write_bytes(b"png")
        (self.root / "media" / "sandbox.webm").write_bytes(b"webm")
        body, _ = pages.render(pages.get("mail-graph"), lambda name: f"/m/{name}")
        self.assertIn('<img src="/m/graph.png" alt="Карта шагов"', body)
        self.assertIn('<video src="/m/sandbox.webm" autoplay loop muted', body)
        self.assertIn('href="#/guide/start"', body)
        self.assertEqual(pages.missing_media(), [])

    def test_media_path_refuses_foreign_names(self):
        (self.root / "media" / "ok.png").write_bytes(b"x")
        (self.root / "secret.png").write_bytes(b"x")
        self.assertIsNotNone(pages.media_path("ok.png"))
        for bad in ("../secret.png", "ok.gif", "a/b.png", "", None, "nope.png"):
            self.assertIsNone(pages.media_path(bad), bad)

    def test_search_weighs_title_and_skips_media_tokens(self):
        hits = pages.search("песочница")
        self.assertEqual([p.slug for p, _ in hits], ["mail-graph"])
        self.assertIn("Песочница", hits[0][1])
        self.assertEqual([p.slug for p, _ in pages.search("граф шаги")], ["mail-graph"])
        self.assertEqual(pages.search("sandbox"), [])
        self.assertEqual(pages.search("  "), [])
        self.assertEqual(pages.search("page:start"), [])           # ссылки считаются текстом ссылки, не адресом


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.author = get_user_model().objects.create_user("ed", password="pw", is_staff=True)
        self.client.force_login(self.author)

    def test_index_page_and_neighbours(self):
        index = self.client.get("/studio/api/guide").json()
        self.assertEqual([s["title"] for s in index], ["Основы", "Почта", "Прочее"])
        data = self.client.get("/studio/api/guide/mail-graph").json()
        self.assertEqual((data["prev"]["slug"], data["next"]["slug"], data["missing"]), ("start", "bare", 2))
        (self.root / "media" / "graph.png").write_bytes(b"x")
        self.assertIn("/studio/guide/media/graph.png", self.client.get("/studio/api/guide/mail-graph").json()["html"])
        self.assertEqual(self.client.get("/studio/api/guide/nope").status_code, 404)

    def test_search_endpoint(self):
        found = self.client.get("/studio/api/guide/search", {"q": "aetheros"}).json()
        self.assertEqual([h["slug"] for h in found], ["start"])

    def test_any_author_reads_even_without_a_role_section(self):
        self.assertEqual(self.client.get("/studio/api/guide").status_code, 200)

    def test_media_view(self):
        (self.root / "media" / "graph.png").write_bytes(b"PNGDATA")
        response = self.client.get("/studio/guide/media/graph.png")
        self.assertEqual((response.status_code, response["Content-Type"], b"".join(response.streaming_content)), (200, "image/png", b"PNGDATA"))
        self.assertEqual(self.client.get("/studio/guide/media/none.png").status_code, 404)
        self.client.logout()
        self.assertNotEqual(self.client.get("/studio/guide/media/graph.png").status_code, 200)
