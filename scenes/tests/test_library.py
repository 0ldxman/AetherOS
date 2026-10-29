"""Библиотека сцен из файлов (scenes/library) играет то же, что встроенная загрузка на Python: шаг в шаг."""
from pathlib import Path

from django.test import TestCase

from machines.models import Machine
from machines.world.dates import world
from machines.world.identity import identity_of
from scenes.boots import _pcr_digest, aether_boot
from scenes.script import compile_script

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def load(slug):
    path = LIBRARY / f"{slug}.scene"
    return path.read_text() if path.exists() else None


def strip(steps):
    """Привести к тому, что видит игрок: подпись внутри count это текст перед ним; пробелы без цвета; соседний текст одного цвета слит;
    хвостовые пробелы подписей перед точками и полосой не видны."""
    flat = []
    for step in steps:
        step = dict(step)
        if step["op"] == "count" and step.get("label"):
            flat.append({"op": "text", "value": step["label"]})
            step["label"] = ""
        for key in ("label", "value"):
            if isinstance(step.get(key), str) and step["op"] != "text":
                step[key] = step[key].rstrip()
        if step["op"] == "text" and not step["value"].strip():
            step.pop("style", None)
        flat.append(step)
    folded = []
    for index, step in enumerate(flat):                                  # пробелы перед цветным текстом красятся вместе с ним
        ahead = flat[index + 1] if index + 1 < len(flat) else None
        if step["op"] == "text" and not step["value"].strip() and "style" not in step and ahead and ahead["op"] == "text" \
                and ahead.get("style") and not ahead.get("id"):
            ahead["value"] = step["value"] + ahead["value"]
        else:
            folded.append(step)
    merged = []
    for step in folded:
        last = merged[-1] if merged else None
        if step["op"] == "text" and last and last["op"] == "text" and last.get("style") == step.get("style") and not last.get("id") \
                and not step.get("id") and not last.get("cursor"):
            last["value"] += step["value"]
        else:
            merged.append(step)
    return merged


class BootLibraryTests(TestCase):
    def build(self, slug):
        Machine.objects.create(name="Main", hostname="aether-main")
        ident = identity_of("aether-main")
        now = world()
        params = {
            "host": ident.hostname, "hid": ident.hid, "serial": ident.serial, "address": ident.address, "host_key": ident.host_key,
            "os": "AETHER", "os_name": "Aether", "date": now.game_date, "time": f"{now.game_now:%H:%M} UTC", "pcr": _pcr_digest(ident),
        }
        scene, errors = compile_script(load(slug), params, now.game_now, load)
        self.assertEqual(errors, [])
        return ident, scene.to_dict()

    def assertSame(self, ours, theirs):
        ours, theirs = strip(ours), strip(theirs)
        for index, (a, b) in enumerate(zip(ours, theirs)):
            self.assertEqual(a, b, f"шаг {index}")
        self.assertEqual(len(ours), len(theirs))

    def test_the_full_boot_is_the_same_as_in_python(self):
        ident, steps = self.build("boot")
        self.assertSame(steps, aether_boot(ident).to_dict())

    def test_the_short_boot_is_the_same_as_in_python(self):
        ident, steps = self.build("boot-short")
        self.assertSame(steps, aether_boot(ident, short=True).to_dict())
