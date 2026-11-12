"""Элементы стола по ОС: что есть в оболочке стиля, переключатели ОС, CSS для выключенного, предупреждение, Студия."""
import json

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from machines.models import SystemType
from machines.world import widgets
from team.testing import full_role


class WidgetTests(TestCase):
    def test_slots_render_added_elements(self):
        from django.template.loader import render_to_string

        found = widgets.slot_context("aether", {"tasks": True, "dock": True, "launcher": True}, {}, "end")
        self.assertEqual(found["els"], ["tasks"])
        desk = widgets.slot_context("aether", {"dock": True, "launcher": True}, {}, "desk")
        self.assertEqual((desk["dock"], desk["launcher_panel"], desk["notices_panel"]), ("bottom", True, False))
        html = render_to_string("desktop/elements/slot.html", {**found, "login": "ivan", "machine_name": "m"})
        self.assertIn('data-shell="tasks"', html)
        self.assertEqual(widgets.slot_context("classic", {"launcher": True}, {}, "desk")["launcher_panel"], False)   # своя панель есть

    def test_support_resolve_and_css(self):
        self.assertTrue(widgets.is_native("workspaces", "workbench"))
        self.assertFalse(widgets.is_native("tasks", "aether"))
        self.assertEqual(widgets.shell_of("glitched"), "aether")                              # своей оболочки нет: как у aether
        state = widgets.resolve("aether", {"ping": False, "dock": True, "bogus": False, "icons": "no"})
        self.assertEqual((state["ping"], state["clock"], state["tasks"], state["dock"]), (False, True, False, True))
        self.assertEqual(widgets.added("aether", {"dock": True, "workspaces": True}, {"dock": "left"}), {"dock": "left", "workspaces": "end"})
        self.assertTrue(widgets.resolve("classic", {"launcher": False})["launcher"])          # в нём выход: не выключается
        css = widgets.hidden_css("aether", {"ping": False, "icons": False})
        self.assertIn(".ping{display:none!important}", css)
        self.assertIn("#icons{display:none!important}", css)
        self.assertEqual(widgets.hidden_css("aether", {}), "")
        self.assertTrue(widgets.warnings("aether", {"icons": False}))                        # у aether нет меню запуска
        self.assertEqual(widgets.warnings("aether", {"icons": False, "launcher": True}), [])
        self.assertEqual(widgets.warnings("gnome", {"icons": False}), [])

    def test_the_desktop_hides_what_the_os_turned_off(self):
        from machines.templatetags import os_style

        system = SystemType.objects.create(code="KIOSK", name="Kiosk", style="aether", widgets={"ping": False, "ticker": False})
        request = RequestFactory().get("/")
        request.user = get_user_model()()
        request._os_style = ("aether", {}, system.code, {})
        request._os_widgets = system.widgets
        html = Template("{% load os_style %}{% os_widgets_css %}|{% os_widget 'ticker' %}|{% os_widget 'toasts' %}").render(Context({"request": request}))
        self.assertIn(".ping{display:none!important}", html)
        self.assertTrue(html.endswith("|0|1"))
        self.assertEqual(os_style.widget_state(request)["ping"], False)

    def test_studio_saves_widgets(self):
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))
        SystemType.objects.create(code="KIOSK", name="Kiosk", style="gnome")
        data = self.client.get("/studio/api/systems/KIOSK").json()
        info = {w["key"]: w for w in data["widget_info"]}
        self.assertIn("gnome", info["dock"]["native"])
        self.assertNotIn("aether", info["dock"]["native"])
        self.assertEqual([p["value"] for p in info["dock"]["places"]], ["bottom", "left", "right"])
        body = {"style": "gnome", "tokens": {}, "widgets": {"ping": False, "dock": True, "nonsense": True}, "widget_places": {"dock": "left", "ping": "end"}}
        saved = self.client.put("/studio/api/systems/KIOSK/style", data=json.dumps(body), content_type="application/json").json()
        self.assertEqual((saved["widgets"], saved["widget_places"]), ({"ping": False, "dock": True}, {"dock": "left"}))
