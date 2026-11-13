"""Элементы самого стола (machines/world/widgets.py) и главная панель (machines/world/panel.py)."""
import json

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from machines.models import SystemType
from machines.world import panel, styles, widgets
from team.testing import full_role


class DeskWidgetsTests(TestCase):
    def test_resolve_and_css(self):
        state = widgets.resolve("gnome", {"icons": False, "nonsense": True})
        self.assertEqual((state["icons"], state["toasts"]), (False, True))
        self.assertNotIn("dock", state)                                    # док теперь параметрами (styles.DOCK)
        self.assertIn("#icons{display:none!important}", widgets.hidden_css("gnome", {"icons": False}))

    def test_the_desktop_hides_what_the_os_turned_off(self):
        system = SystemType.objects.create(code="KIOSK", name="Kiosk", style="aether", widgets={"date": False, "ticker": False})
        request = RequestFactory().get("/")
        request.user = get_user_model()()
        request._os_style = ("aether", {}, system.code, {})
        request._os_widgets, request._os_parts = system.widgets, {}
        html = Template("{% load os_style %}{% os_widgets_css %}|{% os_widget 'ticker' %}|{% os_widget 'toasts' %}").render(Context({"request": request}))
        self.assertIn("#date{display:none!important}", html)
        self.assertTrue(html.endswith("|0|1"))

    def test_warning_when_apps_cannot_be_opened(self):
        layout = {"start": ["machine"], "center": ["clock"], "end": ["ping"]}
        self.assertTrue(widgets.warnings("aether", {"icons": False}, {"panel": layout}))
        self.assertFalse(widgets.warnings("aether", {"icons": False}, {"panel": {**layout, "end": ["apps"]}}))
        self.assertFalse(widgets.warnings("aether", {"icons": False}, {"panel": layout, "panel2": {"show": "on"}}))     # быстрый запуск на дополнительной
        self.assertFalse(widgets.warnings("gnome", {"icons": False}))           # у GNOME дополнительная панель по умолчанию
        self.assertFalse(widgets.warnings("phosphor", {"icons": False}))

    def test_studio_saves_widgets(self):
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))
        SystemType.objects.create(code="KIOSK", name="Kiosk", style="gnome")
        body = {"style": "gnome", "tokens": {}, "widgets": {"icons": False, "dock": True, "ping": False}, "widget_places": {"dock": "left"}}
        saved = self.client.put("/studio/api/systems/KIOSK/style", data=json.dumps(body), content_type="application/json").json()
        self.assertEqual((saved["widgets"], saved["widget_places"]), ({"icons": False}, {}))


class PartGroupsTests(TestCase):
    def test_presets_follow_the_look_of_the_style(self):
        self.assertEqual(panel.of2("gnome")["show"], "on")
        self.assertEqual(panel.of2("gnome")["end"], ["allapps"])
        self.assertEqual(panel.of2("aether")["show"], "off")
        self.assertEqual(styles.preset("apps", "gnome")["labels"], "none")
        self.assertEqual(styles.preset("notice", "glitched"), {"corner": "br", "errors": "window", "fill": "standard", "look": "aether"})
        self.assertEqual(styles.group_of("notice", "aether", {"notice": {"look": "gnome"}})["corner"], "tc")      # чужой вид со своим углом
        self.assertEqual(styles.group_of("clock", "aether", {"clock": {"hours": "12", "seconds": "x"}}), {"hours": "12", "seconds": "on"})

    def test_main_panel_on_a_side_uses_generic_elements(self):
        self.assertEqual(panel.attrs("aether", {"edge": "left"})["panel-edge"], "left")
        self.assertEqual(dict(panel.elements("aether", {"edge": "left"})["start"])["machine"], "desktop/elements/machine.html")
        self.assertEqual(panel.attrs2("aether", {"show": "on", "reserve": "on"})["pl2-reserve"], "on")

    def test_main_panel_can_be_switched_off(self):
        self.assertEqual(panel.elements("aether", {"show": "off"}), {"start": [], "center": [], "end": []})
        self.assertEqual(panel.of2("aether", {"show": "on", "start": ["clock"]}, {"show": "off"})["start"], ["clock"])     # её элементы свободны
        self.assertTrue(panel.problems("aether", {"show": "off"}))                                  # выхода нигде нет
        self.assertEqual(panel.problems("aether", {"show": "off"}, {"show": "on", "start": ["launcher"]}), [])

    def test_second_panel_never_repeats_the_main_one(self):
        self.assertEqual(panel.of2("workbench", {"show": "on"})["start"], [])          # быстрый запуск уже на передней панели Workbench
        self.assertEqual(panel.problems2("workbench", {"start": ["apps"]}), ["Быстрый запуск: уже стоит на главной панели."])
        self.assertEqual(panel.problems2("aether", {"edge": "middle"}), ["Нет такого края: middle."])
        main = {"start": ["clock"], "center": [], "end": ["ping"]}
        self.assertFalse(panel.exits("aether", main))
        self.assertTrue(panel.exits("aether", main, {"show": "on", "start": ["launcher"]}))        # выход на дополнительной тоже выход
        self.assertFalse(panel.exits("aether", main, {"show": "off", "start": ["launcher"]}))

    def test_attrs(self):
        attrs = styles.parts("aether", {"panel2": {"show": "on", "edge": "left"}, "apps": {"mark": "line"}, "notice": {"corner": "tl", "errors": "screen"}, "clock": {"seconds": "off"}})
        self.assertEqual((attrs["pl2-show"], attrs["pl2-edge"], attrs["apps-mark"], attrs["toast-corner"], attrs["toast-move"], attrs["error-form"], attrs["clock-seconds"]),
                         ("on", "left", "line", "tl", "1", "screen", "off"))
        self.assertNotIn("toast-move", styles.parts("gnome"))
        self.assertEqual(styles.parts("aether", {"notice": {"fill": "fill"}})["error-fill"], "fill")

    def test_desk_renders_the_second_panel(self):
        def render(parts):
            request = RequestFactory().get("/")
            request.user = get_user_model()()
            request._os_style = ("aether", {}, "AETHER", {})
            request._os_widgets, request._os_places, request._os_parts = {}, {}, parts
            return Template("{% load os_style %}{% os_slot 'desk' %}").render(Context({"request": request, "login": "ivan", "machine_name": "aether-main"}))
        html = render({"panel2": {"show": "on", "start": ["apps"], "end": ["allapps", "clock"]}})
        self.assertIn('<nav class="dk"', html)
        self.assertIn('class="el el--apps"', html)
        self.assertIn('class="el el--allapps" data-shell="launcher"', html)
        self.assertNotIn('id="clock"', html)                               # часы уже на главной панели Aether
        self.assertIn('id="launcher" class="el-pop', html)                # у Aether своего меню запуска нет: кнопке нужно меню
        self.assertEqual(render({}), "")
        self.assertEqual(render({"panel2": {"show": "on", "start": ["clock"]}}), "")      # всё уже на главной — пустую панель не рисуем

    def test_studio_saves_parts_and_second_panel(self):
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))
        SystemType.objects.create(code="KIOSK", name="Kiosk", style="gnome")
        put = lambda body: self.client.put("/studio/api/systems/KIOSK/style", data=json.dumps({"style": "gnome", "tokens": {}, **body}), content_type="application/json")
        saved = put({"parts": {"apps": {"size": "l"}, "clock": {"hours": "12"}}, "panel2": {"edge": "left"}}).json()
        self.assertEqual(saved["parts"], {"apps": {"size": "l"}, "notice": {}, "clock": {"hours": "12"}, "fx": {}, "icons": {}, "cursor": {}})
        self.assertEqual({k: v for k, v in saved["panel2"].items() if v is not None}, {"edge": "left"})
        self.assertEqual(saved["panel_info"]["presets2"]["gnome"]["end"], ["allapps"])
        response = put({"panel2": {"start": ["launcher"]}})
        self.assertEqual((response.status_code, response.json()["fields"]["panel2"]), (400, ["Меню запуска: уже стоит на главной панели."]))
        response = put({"parts": {"apps": {"size": "xl"}}})
        self.assertEqual((response.status_code, response.json()["fields"]["parts"]), (400, ["Размер значков: нет варианта «xl»."]))


class PanelTests(SimpleTestCase):
    def test_every_look_has_a_template_and_a_preset_with_an_exit(self):
        for look in panel.LOOKS:
            render_to_string(f"desktop/panels/{look}.html", {"panel": panel.elements(look)})
            self.assertTrue(panel.exits(look), look)
        self.assertEqual(panel.look_of("glitched"), "aether")

    def test_native_markup_only_in_its_place(self):
        """Прибитые к экрану часы Aether рисуются родными только по центру верхней панели во всю ширину."""
        self.assertEqual(dict(panel.elements("aether")["center"])["clock"], "desktop/panels/aether/clock.html")
        moved = panel.elements("aether", {"center": [], "end": ["ping", "clock"]})
        self.assertEqual(dict(moved["end"])["clock"], "desktop/elements/clock.html")
        self.assertEqual(dict(panel.elements("aether", {"edge": "bottom"})["center"])["clock"], "desktop/elements/clock.html")
        self.assertEqual(dict(panel.elements("aether", {"form": "island"})["center"])["clock"], "desktop/elements/clock.html")
        self.assertEqual(dict(panel.elements("classic", {"edge": "bottom"})["end"])["clock"], "desktop/panels/classic/clock.html")
        self.assertEqual(dict(panel.elements("aether", {"end": ["search"]})["end"])["search"], "desktop/elements/search.html")

    def test_clean_keeps_each_element_once(self):
        self.assertEqual(panel.clean({"look": "nope", "edge": "middle", "start": ["clock", "nope"], "end": ["clock", "ping"]}),
                         {"start": ["clock"], "end": ["ping"]})

    def test_problems(self):
        self.assertEqual(panel.problems("aether", {"start": ["clock"], "center": [], "end": ["ping"]}),
                         ["На панелях нет выхода из сеанса: оставьте меню запуска, «Сеанс» или «Кнопки сеанса»."])
        self.assertEqual(panel.problems("tui", {"start": [], "center": [], "end": []}), [])            # выход в полосе F-клавиш
        self.assertIn("Пинг: стоит на панели дважды.", panel.problems("aether", {"start": ["ping"], "end": ["ping"]}))
        self.assertIn("Нет такого края: middle.", panel.problems("aether", {"edge": "middle"}))

    def test_attrs_mark_a_foreign_edge_and_form(self):
        self.assertEqual(panel.attrs("modern"), {"panel": "modern", "panel-show": "on", "panel-edge": "bottom", "panel-form": "bar"})
        self.assertEqual(panel.attrs("modern", {"edge": "top", "form": "island"}),            # прежнее «остров» читается как док
                         {"panel": "modern", "panel-show": "on", "panel-edge": "top", "panel-form": "dock", "panel-flip": "top", "panel-reform": "dock"})
        self.assertEqual(panel.attrs("aether", {"form": "islands"})["panel-form"], "islands")
        self.assertEqual(panel.attrs("tui", {"edge": "bottom"})["panel-edge"], "top")                 # край у TUI не меняется

    def test_another_look_brings_its_layout(self):
        found = panel.of("aether", {"look": "workbench"})
        self.assertEqual((found["edge"], found["form"], found["start"][0]), ("bottom", "dock", "clock"))
        self.assertEqual(styles.parts("aether", {"panel": {"look": "classic"}})["panel"], "classic")
        self.assertEqual(styles.parts("aether", {"panel": {"look": "classic"}})["dock"], "classic")


class PanelRenderTests(TestCase):
    def render(self, parts, style="aether"):
        request = RequestFactory().get("/")
        request.user = get_user_model()()
        request._os_style = (style, {}, "AETHER", {})
        request._os_widgets, request._os_places, request._os_parts = {}, {}, parts
        return Template("{% load os_style %}{% os_panel %}").render(Context({"request": request, "login": "ivan", "machine_name": "aether-main"}))

    def test_slots_render_in_order_and_desk_adds_popovers(self):
        html = self.render({"panel": {"start": ["launcher", "tasks"], "center": ["clock"], "end": ["notices", "machine"]}})
        self.assertLess(html.index('class="el el--btn el--launcher"'), html.index('class="el el--tasks"'))
        self.assertIn('<span class="pl-center"><span class="pl-group pl-group--center"><div id="clock-plate">', html)             # часы Aether на своём месте — родные
        self.assertIn('id="session-menu-button"', html)
        self.assertIn('class="el-pop el-pop--top el-pop--left el-launcher"', html)        # у Aether своего меню запуска нет
        self.assertIn('class="el-pop el-pop--top el-pop--right el-notices"', html)
        self.assertIn('data-action="disconnect"', html)

    def test_presets_render_native_markup(self):
        html = self.render({}, style="modern")
        self.assertIn('class="start-button"', html)
        self.assertIn('id="clock-plate"', html)
        self.assertNotIn("el-pop", html)


class FxIconsCursorTests(TestCase):
    def test_presets_and_attrs(self):
        self.assertEqual(styles.preset("fx", "glitched")["glitch"], "on")          # сбои Glitched теперь эффект
        self.assertEqual(styles.preset("fx", "phosphor")["pixels"], "on")
        attrs = styles.parts("aether", {"fx": {"scanlines": "on"}, "icons": {"look": "ascii"}, "cursor": {"cursor": "block"}})
        self.assertEqual((attrs["fx-scanlines"], attrs["fx-glitch"], attrs["icons-look"], attrs["cursor"]), ("on", "off", "ascii", "block"))

    def test_icon_set_is_chosen_by_the_os(self):
        def icon(parts):
            request = RequestFactory().get("/")
            request.user = get_user_model()()
            request._os_style = ("aether", {}, "AETHER", {})
            request._os_parts = parts
            return Template("{% load os_style %}{% app_icon 'book' %}").render(Context({"request": request}))
        self.assertIn("icons/aether/", icon({}))
        self.assertIn("icons/classic/", icon({"icons": {"set": "classic"}}))
        self.assertEqual(icon({"icons": {"set": "text"}}), "")
