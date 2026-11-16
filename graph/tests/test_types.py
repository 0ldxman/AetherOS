"""Типы сокетов: «одно или список» (many:) и несколько типов (a|b)."""
from django.test import SimpleTestCase

from graph import nodes
from graph.nodes import Field


class SocketTypeTests(SimpleTestCase):
    def test_one_or_list_takes_both(self):
        self.assertTrue(nodes.compatible("placement", "many:placement"))
        self.assertTrue(nodes.compatible("list:placement", "many:placement"))
        self.assertTrue(nodes.compatible("text", "many:placement"))              # вещь по имени
        self.assertTrue(nodes.compatible("many:placement", "list:placement"))
        self.assertTrue(nodes.compatible("many:placement", "placement"))
        self.assertTrue(nodes.compatible("many:placement", "list:any"))
        self.assertFalse(nodes.compatible("machine", "many:placement"))
        self.assertFalse(nodes.compatible("event", "many:placement"))

    def test_several_types(self):
        self.assertTrue(nodes.compatible("machine", "machine|server"))
        self.assertTrue(nodes.compatible("server", "many:machine|server"))
        self.assertTrue(nodes.compatible("list:server", "many:machine|server"))
        self.assertFalse(nodes.compatible("character", "machine|server"))
        self.assertFalse(nodes.compatible("list:machine", "machine|server"))      # список в одиночный вход нельзя
        self.assertTrue(nodes.compatible("list:machine", "text"))

    def test_labels_and_fields(self):
        self.assertEqual(nodes.type_label("many:placement"), "размещение или список (размещение)")
        self.assertEqual(nodes.type_label("machine|server"), "машину или сетевой ресурс")
        self.assertEqual(nodes.type_label("list:placement"), "список (размещение)")
        self.assertEqual(nodes.field_type(Field("p", "Размещение", "many:placement")), "many:placement")
        self.assertEqual(nodes.field_type(Field("o", "Объект", "many:object")), "many:item")
