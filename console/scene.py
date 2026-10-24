"""Консольные сцены: описание анимации вывода в консоль.

Сцена это список шагов (словарей), который Python собирает, а браузер
проигрывает (static/ui/console.js). Так один и тот же язык служит и экрану
входа, и ответам команд терминала, и переходам между машинами.

    scene = (
        Scene()
        .line("connecting ...")
        .dots("resolving", "10.40.7.12", "dim", ms=700)
        .text("Trust node? [y/n] ")
        .type("y", human=True)          # «набирает» человек: неровный ритм
        .newline()
    )
    scene.to_json()

Шаги:
    text      дописать текст в текущую строку (style, id)
    newline   закончить строку (count пустых строк подряд)
    type      напечатать побуквенно (speed, human, typo)
    dots      «метка ........ СТАТУС», точки набираются по одной
    pause     пауза (ms, jitter)
    clear     очистить экран
    flash     вспышка экрана
    glitch    текст с id «портится» и становится другим
    one_of    случайная из нескольких вложенных сцен
    choice    выбор из вариантов; события (events) разыгрываются, пока
              игрок не ответил, и могут добавлять варианты

Тексты могут содержать {имя}: браузер подставит значения при проигрывании.
Ничего секретного в сцену класть нельзя: она целиком видна в исходнике страницы.
"""
import json
from dataclasses import dataclass, field

STYLES = ("success", "warning", "error", "dim")
MASK_CHAR = "█"
MAX_MS = 120_000


class SceneError(ValueError):
    """Сцена собрана неверно (неизвестный стиль, отрицательная пауза и т.п.)."""


def _style(style):
    if style is not None and style not in STYLES:
        raise SceneError(f"Неизвестный стиль {style!r}; допустимы {STYLES}")
    return style


def _ms(value, name="ms"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_MS:
        raise SceneError(f"{name} должно быть числом от 0 до {MAX_MS}, получено {value!r}")
    return int(value)


def _delay(value):
    """Задержка: число или пара [от, до]."""
    if isinstance(value, (list, tuple)):
        if len(value) != 2 or value[0] > value[1]:
            raise SceneError(f"Диапазон задержки должен быть [от, до], получено {value!r}")
        return [_ms(value[0], "after_ms"), _ms(value[1], "after_ms")]
    return _ms(value, "after_ms")


def _steps(scene):
    if isinstance(scene, Scene):
        return scene.steps
    return list(scene)


@dataclass(frozen=True)
class Option:
    """Вариант в выборе. key это подпись («[ D ]»), keys это клавиши быстрого выбора."""

    id: str
    key: str
    label: object          # строка или список строк (случайная при каждом показе)
    tag: str = ""
    keys: tuple = ()
    style: str | None = None

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "label": self.label if isinstance(self.label, str) else list(self.label),
            "tag": self.tag,
            "keys": [k.lower() for k in self.keys],
            "style": _style(self.style),
        }


@dataclass(frozen=True)
class Event:
    """Что случается, пока игрок выбирает: после after_ms играет сцена и добавляются варианты."""

    after_ms: object       # число или [от, до]
    scene: object          # Scene или список шагов
    options: tuple = field(default_factory=tuple)

    def to_dict(self):
        return {
            "after_ms": _delay(self.after_ms),
            "steps": _steps(self.scene),
            "options": [o.to_dict() for o in self.options],
        }


class Scene:
    def __init__(self):
        self.steps = []

    # ---------- вывод ----------

    def text(self, value, style=None, *, id=None):
        step = {"op": "text", "value": str(value)}
        if style is not None:
            step["style"] = _style(style)
        if id:
            step["id"] = id
        self.steps.append(step)
        return self

    def newline(self, count=1):
        for _ in range(count):
            self.steps.append({"op": "newline"})
        return self

    def line(self, *parts, style=None):
        """Строка целиком. Части: строка или (текст, стиль)."""
        for part in parts or ("",):
            if isinstance(part, tuple):
                self.text(part[0], part[1])
            else:
                self.text(part, style)
        return self.newline()

    def kv(self, label, value, style=None, *, width=10, note=None, id=None):
        """«метка     значение  (пояснение)»: метка дополняется до width."""
        self.text(label.ljust(width))
        self.text(value, style, id=id)
        if note:
            self.text("  " + note, "dim")
        return self.newline()

    def type(self, value, *, speed=22, style=None, human=False, typo=False):
        step = {
            "op": "type",
            "value": str(value),
            "speed": _ms(speed, "speed"),
            "human": bool(human),
            "typo": bool(typo),
        }
        if style is not None:
            step["style"] = _style(style)
        self.steps.append(step)
        return self

    def dots(self, label, status, style="success", *, ms=500, count=14, newline=True):
        """«метка ........ СТАТУС» и конец строки (newline=False оставляет её открытой)."""
        self.steps.append(
            {
                "op": "dots",
                "label": str(label),
                "status": str(status),
                "style": _style(style),
                "ms": _ms(ms),
                "count": _ms(count, "count"),
            }
        )
        return self.newline() if newline else self

    def route(self, hops, *, label="carrier", width=10, ms=450, jitter=250):
        """Маршрут: [(название, имя, задержка мс или None для «нет ответа»), ...]."""
        for index, (name, host, latency) in enumerate(hops):
            self.pause(ms, jitter)
            self.text((label if index == 0 else "").ljust(width))
            self.text(f"{name:<10}{host:<14}")
            if latency is None:
                self.text("no answer", "warning")
            else:
                self.text(f"{latency:>3} ms", "dim")
            self.newline()
        return self

    # ---------- время и эффекты ----------

    def pause(self, ms, jitter=0):
        self.steps.append({"op": "pause", "ms": _ms(ms), "jitter": _ms(jitter, "jitter")})
        return self

    def clear(self):
        self.steps.append({"op": "clear"})
        return self

    def flash(self):
        self.steps.append({"op": "flash"})
        return self

    def glitch(self, id, to):
        """Текст, ранее выведенный с этим id, портится и становится to."""
        self.steps.append({"op": "glitch", "id": id, "to": str(to)})
        return self

    # ---------- ветвление ----------

    def one_of(self, *scenes):
        if not scenes:
            raise SceneError("one_of без вариантов")
        self.steps.append({"op": "one_of", "scenes": [_steps(s) for s in scenes]})
        return self

    def choice(self, id, options, *, prompt="Select", events=()):
        if not options:
            raise SceneError("choice без вариантов")
        self.steps.append(
            {
                "op": "choice",
                "id": id,
                "prompt": prompt,
                "options": [o.to_dict() for o in options],
                "events": [e.to_dict() for e in events],
            }
        )
        return self

    def extend(self, other):
        self.steps.extend(_steps(other))
        return self

    # ---------- помощники ----------

    @staticmethod
    def mask(length):
        """Замазанное поле: тот же символ, что у спойлеров в вики."""
        return MASK_CHAR * length

    def to_dict(self):
        return self.steps

    def to_json(self):
        return json.dumps(self.steps, ensure_ascii=False)
