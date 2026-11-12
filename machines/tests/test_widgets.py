"""Элементы стола по ОС: что есть в оболочке стиля, переключатели ОС, CSS для выключенного, предупреждение, Студия."""
import json

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from machines.models import SystemType
from machines.world import widgets
from team.testing import full_role


class WidgetTests(TestCase):
    def test_support_resolve_and_css(self):
        self.assertIn("workspaces", widgets.supported("workbench"))
        self.assertNotIn("tasks", widgets.supported("aether"))
        self.assertEqual(widgets.supported("glitched"), widgets.supported("aether"))          # своей оболочки нет: как у aether
        state = widgets.resolve("aether", {"ping": False, "tasks": False, "bogus": False, "icons": "no"})
        self.assertEqual((state["ping"], state["clock"], "tasks" in state), (False, True, False))
        css = widgets.hidden_css("aether", {"ping": False, "icons": False})
        self.assertIn(".ping{display:none!important}", css)
        self.assertIn("#icons{display:none!important}", css)
        self.assertEqual(widgets.hidden_css("aether", {}), "")
        self.assertTrue(widgets.warnings("aether", {"icons": False}))                        # у aether нет меню запуска
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
        self.assertIn("gnome", info["dock"]["styles"])
        self.assertNotIn("aether", info["dock"]["styles"])
        body = {"style": "gnome", "tokens": {}, "widgets": {"ping": False, "dock": True, "nonsense": True}}
        saved = self.client.put("/studio/api/systems/KIOSK/style", data=json.dumps(body), content_type="application/json").json()
        self.assertEqual(saved["widgets"], {"ping": False, "dock": True})
