"""Время мира в Студии: живое «сейчас», сдвиги, план, предупреждение о сдвиге назад, пояса машин."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from machines.models import Machine
from team.testing import full_role

API = "/studio/api"


class TimeApiTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("boss", password="pw", is_staff=True, role=full_role()))

    def call(self, method, path, body=None):
        kwargs = {"data": json.dumps(body), "content_type": "application/json"} if body is not None else {}
        response = getattr(self.client, method)(f"{API}{path}", **kwargs)
        return response.status_code, (response.json() if response.content else None)

    def test_shift_plan_warn_and_cancel(self):
        Machine.objects.create(name="M", hostname="msk", time_zone="Europe/Moscow")
        status, data = self.call("post", "/world/time", {"game_at": "2031-01-15T09:00:00Z", "rate": 1, "note": "старт"})
        self.assertEqual(status, 200)
        self.assertTrue(data["game_now"].startswith("2031-01-15T09:00"))
        self.assertIn({"zone": "Europe/Moscow", "machines": ["msk"]}, data["zones"])
        self.assertEqual(self.call("post", "/world/time", {"real_at": "2020-01-01T00:00:00Z", "game_at": "2031-01-01T00:00:00Z"})[0], 400)
        warned = self.call("post", "/world/time/check", {"game_at": "2031-01-10T00:00:00Z"})[1]
        self.assertTrue(warned["items"][0].startswith("Сдвиг назад на 5 д"))
        self.assertEqual(self.call("post", "/world/time/check", {"game_at": "2031-02-01T00:00:00Z"})[1]["items"], [])
        plan = self.call("post", "/world/time", {"real_at": "2099-01-01T00:00:00Z", "game_at": "2031-03-01T00:00:00Z", "rate": 0.5})[1]
        planned = next(a for a in plan["anchors"] if not a["past"])
        self.assertEqual(planned["rate"], 0.5)
        started = next(a for a in plan["anchors"] if a["note"] == "старт")
        self.assertEqual(self.call("delete", f"/world/time/{started['id']}")[0], 400)          # наступившее не удаляется
        self.assertEqual(len(self.call("delete", f"/world/time/{planned['id']}")[1]["anchors"]), 1)

    def test_machine_time_zone_is_checked(self):
        machine = Machine.objects.create(name="M", hostname="m")
        data = self.call("get", f"/machines/{machine.pk}")[1]
        body = {key: data[key] for key in ("hostname", "name", "system", "status", "address", "serial", "host_key", "note", "booted_at")}
        self.assertEqual(self.call("put", f"/machines/{machine.pk}", {**body, "time_zone": "Mars/Olympus"})[0], 400)
        saved = self.call("put", f"/machines/{machine.pk}", {**body, "time_zone": "Asia/Tokyo"})[1]
        self.assertEqual(saved["time_zone"], "Asia/Tokyo")
        self.assertIn("JST", saved["local_now"])
