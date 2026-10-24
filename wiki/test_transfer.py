"""Экспорт и импорт записей: формат, правила обновления, ошибки, админка.

Запуск: python manage.py test wiki.test_transfer
"""

import io
import zipfile
from types import SimpleNamespace

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from wiki import transfer
from wiki.models import Document, DocumentRevision, ImportBatch, Namespace


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8") if isinstance(text, str) else text)
    return buffer.getvalue()


def read_zip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {n: archive.read(n).decode("utf-8") for n in archive.namelist()}


def run(files, user=None, commit=True):
    archive = transfer.read_archive(make_zip(files), "x.zip")
    return transfer.run(archive, user, commit)


def actions(rows):
    return sorted((r.path, r.action) for r in rows)


class NamesAndValuesTests(TestCase):
    def test_names_roundtrip_through_encoding(self):
        for name in ["Винтовка", "a/b", 'q"x', "50%", ".скрытая", "a\\b*?<>|", "ок"]:
            encoded = transfer.encode_name(name)
            self.assertNotRegex(encoded, r'[/\\:*?"<>|]')
            self.assertFalse(encoded.startswith("."))
            self.assertEqual(transfer.decode_name(encoded), name)

    def test_values_roundtrip(self):
        for value in ["key_a", "a b", "123", {"any": ["a", "b"]}, {"not": "x"}, "кириллица"]:
            self.assertEqual(transfer.parse_value(transfer.emit_value(value)), value)

    def test_simple_slug_is_written_bare(self):
        self.assertEqual(transfer.emit_value("key_a"), "key_a")
        self.assertEqual(transfer.emit_value({"all": ["a", "b"]}), '{"all": ["a", "b"]}')

    def test_broken_json_value_is_an_error(self):
        with self.assertRaises(ValueError):
            transfer.parse_value('{"all": [')

    def test_front_matter_split(self):
        lines, body = transfer.split_front_matter("---\ntype: doc\n---\nтекст\n")
        self.assertEqual((lines, body), (["type: doc\n"], "текст\n"))
        self.assertEqual(transfer.split_front_matter("просто текст"), (None, "просто текст"))
        with self.assertRaises(ValueError):
            transfer.split_front_matter("---\ntype: doc\nтекст")


class RoundTripTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("writer")
        tech = Namespace.objects.create(name="Тех", slug="tech", access="key_a")
        guns = Namespace.objects.create(name="Оружие", parent=tech, visibility={"any": ["k1", "k2"]})
        Namespace.objects.create(name="Пустой")
        Document.objects.create(
            namespace=guns, title="Винтовка", body="строка 1\r\nстрока 2", infobox="инфо",
            direct_link="rifle", access={"all": ["k1", "k2"]}, type="scan",
        )
        Document.objects.create(namespace=guns, title="a/b", body="slash")
        Document.objects.create(title="Корень", body="в корне", visibility="k3")

    def export(self):
        return transfer.build_archive(Document.objects.all(), Namespace.objects.all())

    def snapshot(self):
        docs = {
            (d.path(), d.type): (d.body, d.infobox, d.direct_link, d.access, d.visibility)
            for d in Document.objects.select_related("namespace")
        }
        sections = {
            n.path(): (n.slug, n.access, n.visibility) for n in Namespace.objects.all()
        }
        return docs, sections

    def test_layout(self):
        files = read_zip(self.export())
        self.assertIn("Тех/_section.yml", files)
        self.assertIn("Тех/Оружие/Винтовка.md", files)
        self.assertIn("Тех/Оружие/Винтовка.infobox.md", files)
        self.assertIn("Тех/Оружие/a%2Fb.md", files)
        self.assertIn("Пустой/_section.yml", files)
        self.assertIn("Корень.md", files)
        self.assertNotIn("Тех/Оружие/a%2Fb.infobox.md", files)
        self.assertTrue(files["Тех/Оружие/Винтовка.md"].startswith("---\ntype: scan\ndirect_link: rifle\n"))

    def test_export_into_empty_database_restores_everything(self):
        before = self.snapshot()
        data = self.export()
        Document.objects.all().delete()
        for ns in sorted(Namespace.objects.all(), key=lambda n: -len(n.chain())):
            ns.delete()  # родителя с вложенными удалить нельзя (PROTECT)

        rows = transfer.run(transfer.read_archive(data, "x.zip"), self.user, True)

        self.assertEqual([r for r in rows if r.action == "error"], [])
        self.assertEqual(self.snapshot(), before)

    def test_importing_own_export_changes_nothing(self):
        revisions = DocumentRevision.objects.count()
        rows = transfer.run(transfer.read_archive(self.export(), "x.zip"), self.user, True)
        self.assertEqual({r.action for r in rows}, {"same"})
        self.assertEqual(DocumentRevision.objects.count(), revisions)

    def test_dry_run_writes_nothing(self):
        data = self.export()
        Document.objects.filter(title="Корень").delete()
        before = Document.objects.count()
        rows = transfer.run(transfer.read_archive(data, "x.zip"), self.user, False)
        self.assertIn(("Корень", "create"), actions(rows))
        self.assertEqual(Document.objects.count(), before)


class RulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("writer")
        ns = Namespace.objects.create(name="Раздел")
        cls.doc = Document.objects.create(
            namespace=ns, title="Док", body="старое", infobox="старый инфобокс",
            access="key_a", direct_link="dd",
        )
        cls.other = Document.objects.create(namespace=ns, title="Другой", body="не в архиве")

    def reload(self):
        self.doc.refresh_from_db()
        return self.doc

    def test_changed_body_updates_and_leaves_a_revision(self):
        before = self.doc.revisions.count()
        rows = run({"Раздел/Док.md": "---\ntype: doc\ndirect_link: dd\naccess: key_a\n---\nновое"}, self.user)
        self.assertEqual(actions(rows), [("Раздел:Док", "update")])
        self.assertEqual(rows[0].changes, ["body"])
        self.assertEqual(self.reload().body, "новое")
        self.assertEqual(self.reload().updated_by, self.user)
        self.assertEqual(self.doc.revisions.count(), before + 1)

    def test_nothing_is_deleted(self):
        run({"Раздел/Док.md": "---\n---\nновое"}, self.user)
        self.assertTrue(Document.objects.filter(pk=self.other.pk).exists())

    def test_file_without_front_matter_changes_only_the_body(self):
        run({"Раздел/Док.md": "только текст"}, self.user)
        doc = self.reload()
        self.assertEqual((doc.body, doc.access, doc.direct_link), ("только текст", "key_a", "dd"))

    def test_front_matter_without_a_key_clears_it(self):
        run({"Раздел/Док.md": "---\ntype: doc\n---\nстарое"}, self.user)
        doc = self.reload()
        self.assertEqual((doc.access, doc.direct_link), ({}, ""))
        self.assertEqual(doc.infobox, "старый инфобокс")  # инфобокс без файла не трогается

    def test_infobox_file_replaces_only_the_infobox(self):
        rows = run({"Раздел/Док.infobox.md": "новый инфобокс"}, self.user)
        self.assertEqual(actions(rows), [("Раздел:Док", "update")])
        doc = self.reload()
        self.assertEqual((doc.body, doc.infobox), ("старое", "новый инфобокс"))

    def test_infobox_without_a_document_is_an_error(self):
        rows = run({"Раздел/Новый.infobox.md": "нет записи"}, self.user)
        self.assertEqual(actions(rows), [("Раздел:Новый", "error")])
        self.assertFalse(Document.objects.filter(title="Новый").exists())

    def test_line_endings_are_not_a_change(self):
        Document.objects.filter(pk=self.doc.pk).update(body="a\r\nb")
        rows = run({"Раздел/Док.md": "a\nb"}, self.user)
        self.assertEqual(actions(rows), [("Раздел:Док", "same")])

    def test_new_sections_and_documents_are_created_with_author(self):
        rows = run(
            {"Новый/Вложенный/Д.md": "---\ntype: rec\n---\nтекст", "Новый/_section.yml": "slug: nw\naccess: key_z\n"},
            self.user,
        )
        self.assertEqual(
            actions(rows),
            [("Новый", "create"), ("Новый:Вложенный", "create"), ("Новый:Вложенный:Д", "create")],
        )
        ns = Namespace.objects.get(name="Новый")
        self.assertEqual((ns.slug, ns.access), ("nw", "key_z"))
        doc = Document.objects.get(title="Д")
        self.assertEqual((doc.type, doc.created_by, doc.namespace.parent), ("rec", self.user, ns))

    def test_existing_section_meta_is_updated_only_when_the_file_is_present(self):
        run({"Раздел/Док.md": "старое"}, self.user)
        self.assertEqual(Namespace.objects.get(name="Раздел").access, {})
        run({"Раздел/_section.yml": "access: key_q\n"}, self.user)
        self.assertEqual(Namespace.objects.get(name="Раздел").access, "key_q")

    def test_lint_warnings_are_reported(self):
        rows = run({"Раздел/Новая.md": "::box\nнет конца\n"}, self.user)
        self.assertTrue(any("не закрыт" in w for w in rows[0].warnings))


class ErrorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("writer")
        Namespace.objects.create(name="Занято")

    def one(self, files):
        rows = run(files, self.user)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_unclosed_front_matter(self):
        self.assertEqual(self.one({"Д.md": "---\ntype: doc\nтекст"}).action, "error")

    def test_unknown_type(self):
        row = self.one({"Д.md": "---\ntype: wat\n---\nx"})
        self.assertEqual(row.action, "error")
        self.assertIn("wat", row.errors[0])

    def test_broken_json_in_front_matter(self):
        self.assertEqual(self.one({"Д.md": '---\naccess: {"all": [\n---\nx'}).action, "error")

    def test_bad_condition_is_rejected_by_model_validation(self):
        self.assertEqual(self.one({"Д.md": '---\naccess: {"xor": ["a"]}\n---\nx'}).action, "error")

    def test_title_clashing_with_a_section(self):
        self.assertEqual(self.one({"Занято.md": "x"}).action, "error")

    def test_colon_in_title(self):
        self.assertEqual(self.one({"А%3AБ.md": "x"}).action, "error")

    def test_bad_document_does_not_stop_the_others(self):
        rows = run({"Плохой.md": "---\ntype: wat\n---\n", "Хороший.md": "ок"}, self.user)
        self.assertEqual(actions(rows), [("Плохой", "error"), ("Хороший", "create")])
        self.assertTrue(Document.objects.filter(title="Хороший").exists())

    def test_document_in_a_section_that_cannot_be_created_is_skipped(self):
        rows = run({"Новый/_section.yml": "access: {bad\n", "Новый/Д.md": "x"}, self.user)
        self.assertEqual({r.action for r in rows}, {"error"})
        self.assertFalse(Document.objects.exists())

    def test_taken_slug(self):
        Namespace.objects.create(name="Старый", slug="same")
        rows = run({"Новый/_section.yml": "slug: same\n"}, self.user)
        self.assertEqual(actions(rows), [("Новый", "error")])


class ArchiveReadingTests(TestCase):
    def test_not_an_archive(self):
        with self.assertRaises(transfer.ArchiveError):
            transfer.read_archive(b"hello", "notes.txt")
        with self.assertRaises(transfer.ArchiveError):
            transfer.read_archive(b"", "a.md")

    def test_single_markdown_file(self):
        archive = transfer.read_archive("---\ntype: scan\n---\nтекст".encode(), "Мой%2Fфайл.md")
        (key, source), = archive.docs.items()
        self.assertEqual(key, ((), "Мой/файл"))
        self.assertEqual((source.body, source.meta), ("текст", {"type": "scan"}))

    def test_bom_is_dropped(self):
        archive = transfer.read_archive(b"\xef\xbb\xbf---\ntype: doc\n---\nx", "a.md")
        self.assertEqual(archive.docs[((), "a")].meta, {"type": "doc"})

    def test_hidden_and_service_files_are_ignored_quietly(self):
        archive = transfer.read_archive(
            make_zip({"__MACOSX/._a.md": "x", ".git/config": "x", ".DS_Store": "x", "ok.md": "x"}), "z.zip"
        )
        self.assertEqual(list(archive.docs), [((), "ok")])
        self.assertEqual(archive.notes, [])

    def test_parent_directory_paths_are_refused(self):
        archive = transfer.read_archive(make_zip({"../evil.md": "x", "ok.md": "x"}), "z.zip")
        self.assertEqual(list(archive.docs), [((), "ok")])
        self.assertTrue(any("недопустимый путь" in n for n in archive.notes))

    def test_unsupported_files_are_reported(self):
        archive = transfer.read_archive(make_zip({"a.png": "x", "ok.md": "x"}), "z.zip")
        self.assertTrue(any("a.png" in n for n in archive.notes))

    def test_too_many_files(self):
        data = make_zip({f"f{i}.md": "x" for i in range(transfer.MAX_FILES + 1)})
        with self.assertRaises(transfer.ArchiveError):
            transfer.read_archive(data, "z.zip")

    def test_unpacked_size_limit(self):
        original = transfer.MAX_UNPACKED_BYTES
        transfer.MAX_UNPACKED_BYTES = 100
        self.addCleanup(setattr, transfer, "MAX_UNPACKED_BYTES", original)
        with self.assertRaises(transfer.ArchiveError):
            transfer.read_archive(make_zip({"a.md": "x" * 500}), "z.zip")

    def test_utf8_names_without_the_utf8_flag(self):
        mojibake = "Раздел/Док.md".encode("utf-8").decode("cp437")
        info = SimpleNamespace(filename=mojibake, flag_bits=0)
        self.assertEqual(transfer._zip_name(info), "Раздел/Док.md")

    def test_duplicate_entries_keep_the_first(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("a.md", "первый")
            archive.writestr("a.md", "второй")
        parsed = transfer.read_archive(buffer.getvalue(), "z.zip")
        self.assertEqual(parsed.docs[((), "a")].body, "первый")
        self.assertTrue(parsed.notes)


@override_settings(FORCE_SCRIPT_NAME=None)
class AdminTransferTests(TestCase):
    def setUp(self):
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        User = get_user_model()
        self.admin = User.objects.create_superuser("root", password="pw")
        self.client.force_login(self.admin)
        self.tech = Namespace.objects.create(name="Тех")
        self.guns = Namespace.objects.create(name="Оружие", parent=self.tech)
        self.rifle = Document.objects.create(namespace=self.guns, title="Винтовка", body="текст")
        self.root_doc = Document.objects.create(title="Корень", body="корень")

    def url(self, name, *args):
        return reverse(f"admin:wiki_document_{name}", args=args)

    def upload(self, files, name="a.zip"):
        data = make_zip(files) if isinstance(files, dict) else files
        return self.client.post(self.url("import"), {"archive": SimpleUploadedFile(name, data)})

    def test_export_all(self):
        response = self.client.get(self.url("export"))
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment", response["Content-Disposition"])
        names = set(read_zip(response.content))
        self.assertEqual(names, {"Тех/_section.yml", "Тех/Оружие/_section.yml", "Тех/Оружие/Винтовка.md", "Корень.md"})

    def test_export_one_section_keeps_its_ancestors(self):
        names = set(read_zip(self.client.get(self.url("export"), {"ns": self.guns.pk}).content))
        self.assertEqual(names, {"Тех/_section.yml", "Тех/Оружие/_section.yml", "Тех/Оружие/Винтовка.md"})

    def test_export_root_only(self):
        names = set(read_zip(self.client.get(self.url("export"), {"ns": "root"}).content))
        self.assertEqual(names, {"Корень.md"})

    def test_export_selected_action(self):
        response = self.client.post(
            reverse("admin:wiki_document_changelist"),
            {"action": "export_selected", ACTION_CHECKBOX_NAME: [self.root_doc.pk]},
        )
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertEqual(set(read_zip(response.content)), {"Корень.md"})

    def test_list_has_import_and_export_buttons(self):
        response = self.client.get(reverse("admin:wiki_document_changelist"))
        self.assertContains(response, self.url("import"))
        self.assertContains(response, self.url("export"))

    def test_import_page(self):
        self.assertEqual(self.client.get(self.url("import")).status_code, 200)

    def test_upload_shows_the_plan_and_writes_nothing(self):
        response = self.upload({"Тех/Оружие/Винтовка.md": "---\n---\nправка", "Тех/Новая.md": "новая"})
        self.assertContains(response, "Что произойдёт")
        self.assertEqual(response.context["counts"]["create"], 1)
        self.assertEqual(response.context["counts"]["update"], 1)
        self.rifle.refresh_from_db()
        self.assertEqual(self.rifle.body, "текст")
        self.assertFalse(Document.objects.filter(title="Новая").exists())
        self.assertEqual(ImportBatch.objects.count(), 1)

    def test_apply_writes_and_removes_the_batch(self):
        batch = self.upload({"Тех/Новая.md": "новая"}).context["batch"]
        response = self.client.post(self.url("import_apply", batch.pk), follow=True)
        self.assertTrue(Document.objects.filter(title="Новая").exists())
        self.assertEqual(ImportBatch.objects.count(), 0)
        self.assertIn("создано 1", "".join(str(m) for m in response.context["messages"]))

    def test_apply_reports_documents_with_errors(self):
        batch = self.upload({"Плохой.md": "---\ntype: wat\n---\n"}).context["batch"]
        response = self.client.post(self.url("import_apply", batch.pk), follow=True)
        text = "".join(str(m) for m in response.context["messages"])
        self.assertIn("с ошибками 1", text)
        self.assertIn("Плохой", text)

    def test_nothing_to_import(self):
        response = self.upload({"Корень.md": "---\ntype: doc\n---\nкорень"})
        self.assertFalse(response.context["can_apply"])

    def test_bad_upload_shows_an_error(self):
        response = self.upload(b"not an archive", name="notes.txt")
        self.assertContains(response, "Нужен ZIP-архив")
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_batch_of_another_user_is_not_found(self):
        batch = self.upload({"Новая.md": "x"}).context["batch"]
        other = get_user_model().objects.create_superuser("other", password="pw")
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url("import_apply", batch.pk)).status_code, 404)

    def test_apply_needs_post(self):
        batch = self.upload({"Новая.md": "x"}).context["batch"]
        self.assertEqual(self.client.get(self.url("import_apply", batch.pk)).status_code, 405)

    def test_staff_without_permission_is_refused(self):
        viewer = get_user_model().objects.create_user("viewer", password="pw", is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url("import")).status_code, 403)
        self.assertEqual(self.client.get(self.url("export")).status_code, 403)

    def test_old_batches_are_cleaned_on_upload(self):
        self.upload({"Новая.md": "x"})
        from datetime import timedelta
        from django.utils import timezone
        ImportBatch.objects.update(created_at=timezone.now() - timedelta(days=2))
        self.upload({"Другая.md": "y"})
        self.assertEqual(ImportBatch.objects.count(), 1)
