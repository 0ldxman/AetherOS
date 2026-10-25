"""Консольные сцены: описание анимации вывода в консоль.

Сцена это список шагов (словарей), который Python собирает, а браузер
проигрывает (static/ui/console.js). Так один и тот же язык служит и экрану
входа, и загрузке машины, и ответам команд терминала.

    s = Scene()
    s.say("AETHER LINK 3.2", style="dim")             # строка
    s.row("node", "aether-main", id="host")           # «метка    значение»
    s.task("resolving", "10.40.7.12", style="dim")    # «resolving ........ 10.40.7.12»
    s.say("Trust node? [y/n] ", end=False).type("y", human=True)
    s.wait(500).clear()

Весь словарь сцены:

    вывод      say      строка из частей: "текст", ("текст", стиль) или ("текст", стиль, id)
               row      «метка    значение  (пояснение)», метка дополняется до width
               blank    пустая строка
               type     напечатать побуквенно: human (неровный ритм), typo, chunk (пачками)
    процесс    task     задача с результатом: «метка ..... OK» (look="dots"),
                        «[ .. ] метка» -> «[  up  ] метка» (look="unit", службы Aether),
                        «X.XXXXXX метка» -> «0.801544 метка OK» (при at=, строки ядра)
               bar      полоса «[#####-----]  50%»
               count    число растёт до значения: «Memory Testing:  64000K OK»
               countdown  «Auto-boot in 3s...» -> 2s -> 1s
               log      строка ядра: «время  подсистема  текст»; пауза равна разнице времён
               burst    несколько строк почти сразу, как приходят пачкой
    время      wait     пауза: число мс или (от, до), каждый раз случайная
               read     дать прочитать экран: пауза тем дольше, чем больше на нём текста
    эффекты    clear    очистить экран
               cut      смена режима: чёрный кадр и чистый экран (между этапами загрузки)
               flash    вспышка экрана
               glitch   текст с id «портится» и становится другим
    ветвление  one_of   случайная из вложенных сцен
               choice   выбор из Option; вариант может появиться позже (appear) и
                        перепечатываться, пока игрок молчит (retype)

Время (ms) везде можно задать числом или парой (от, до): тогда при каждом показе
выбирается своё значение, и две загрузки подряд не совпадают.

Тексты могут содержать {имя}: браузер подставит значения при проигрывании.
Ничего секретного в сцену класть нельзя: она целиком видна в исходнике страницы.
"""
import json
from dataclasses import dataclass

STYLES = ("success", "warning", "error", "dim")
LOOKS = ("dots", "unit", "kernel")
MASK_CHAR = "█"
MAX_MS = 120_000

# результат задачи -> цвет, которым он выводится
RESULT_STYLES = {"OK": "success", "WARN": "warning", "FAIL": "error"}
# как результат выглядит в строке службы Aether: [  up  ] [ warn ] [ fail ]
UNIT_MARKS = {"OK": "  up  ", "WARN": " warn ", "FAIL": " fail "}


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
    """Задержка: число или пара (от, до)."""
    if isinstance(value, (list, tuple)):
        if len(value) != 2 or value[0] > value[1]:
            raise SceneError(f"Диапазон задержки должен быть (от, до), получено {value!r}")
        return [_ms(value[0], "задержка"), _ms(value[1], "задержка")]
    return _ms(value, "задержка")


def _is_part(value):
    """("текст", стиль) это одна часть строки, а не список строк."""
    return isinstance(value, tuple) and 1 < len(value) <= 3 and isinstance(value[0], str) and (
        value[1] is None or value[1] in STYLES
    )


def _steps(scene):
    if isinstance(scene, Scene):
        return scene.steps
    return list(scene)


def _stamp(at):
    """Время от старта ядра: «  0.004211»; None: время ещё неизвестно."""
    value = "X.XXXXXX" if at is None else f"{at:.6f}"
    return f"{value:>10}"


@dataclass(frozen=True)
class Option:
    """Вариант в выборе.

    key       клавиша быстрого выбора; на экране «[ D ]». also: ещё клавиши.
    label     текст варианта: строка или список (случайная при каждом показе).
    appear    None: вариант есть сразу. Число мс или (от, до): появится сам, позже.
              Его текст сначала печатается на месте простой строкой, потом
              «оформляется под кнопку» (settle мс спустя, typo: с опечаткой).
    retype    тексты (не меньше двух) для перепечатки: пока игрок не ответил, через
              retype_after мс (число или (от, до)) текст стирается и набирается другой.
    """

    id: str
    key: str
    label: object
    tag: str = ""
    also: tuple = ()
    style: str | None = None
    appear: object = None
    typo: bool = True
    settle: int = 500
    retype: tuple = ()
    retype_after: object = (20000, 30000)

    def to_dict(self):
        data = {
            "id": self.id,
            "key": f"[ {self.key.upper()} ]",
            "label": self.label if isinstance(self.label, str) else list(self.label),
            "tag": self.tag,
            "keys": [k.lower() for k in (self.key, *self.also)],
            "style": _style(self.style),
        }
        if self.appear is not None:
            data["late"] = {
                "after_ms": _delay(self.appear),
                "typo": bool(self.typo),
                "settle_ms": _ms(self.settle, "settle"),
            }
        if self.retype:
            if self.appear is None:
                raise SceneError("retype работает только у варианта с appear")
            if len(self.retype) < 2:
                raise SceneError("retype: нужно хотя бы две строки")
            data["rewrites"] = {"after_ms": _delay(self.retype_after), "labels": list(self.retype)}
        return data


class Scene:
    def __init__(self):
        self.steps = []
        self._clock = 0.0       # «время ядра» для log() и task(at=)

    # ---------- вывод ----------

    def _text(self, value, style=None, id=None):
        step = {"op": "text", "value": str(value)}
        if style is not None:
            step["style"] = _style(style)
        if id:
            step["id"] = id
        self.steps.append(step)

    def say(self, *parts, style=None, end=True, cursor=False):
        """Строка. Части: "текст", ("текст", стиль) или ("текст", стиль, id).

        style красит части без собственного стиля. end=False оставляет строку
        открытой: дальше можно дописать type() или ещё один say().
        cursor=True показывает курсор в конце: консоль ждёт ввода (вопрос, приглашение).
        Курсора нет там, где просто идёт вывод.
        """
        for part in parts:
            if isinstance(part, tuple):
                value, part_style, part_id = (*part, None, None)[:3]
                self._text(value, part_style or style, part_id)
            else:
                self._text(part, style)
        if cursor and self.steps and self.steps[-1]["op"] == "text":
            self.steps[-1]["cursor"] = True
        return self.blank() if end else self

    def blank(self, count=1):
        """Конец строки; если строка не открыта, то пустая строка."""
        for _ in range(count):
            self.steps.append({"op": "newline"})
        return self

    def row(self, label, value, style=None, *, width=10, note=None, id=None):
        """«метка     значение  (пояснение)»: метка дополняется до width."""
        parts = [label.ljust(width), (value, style, id)]
        if note:
            parts.append(("  " + note, "dim"))
        return self.say(*parts)

    def type(self, value, *, speed=22, style=None, human=False, typo=False, chunk=1, end=True):
        """Напечатать. human: неровный ритм и раздумья. typo: опечатка, которую стирают.
        chunk: по сколько символов (до) появляется за раз, для логов и дампов."""
        step = {
            "op": "type",
            "value": str(value),
            "speed": _ms(speed, "speed"),
            "human": bool(human),
            "typo": bool(typo),
            "chunk": _ms(chunk, "chunk"),
        }
        if style is not None:
            step["style"] = _style(style)
        self.steps.append(step)
        return self.blank() if end else self

    # ---------- процессы ----------

    def task(self, label, result="OK", note=None, *, look=None, ms=600, done=None, style=None, at=None):
        """Задача, у которой есть результат: OK, WARN, FAIL или любой свой текст.

        look="dots"     «label ........ OK», точки набираются по одной (по умолчанию)
        look="unit"     «[ .. ] label» со спиннером, потом строка заменяется на
                        «[  up  ] done» (done: текст после запуска, по умолчанию label)
        look="kernel"   «X.XXXXXX label» со спиннером, потом настоящее время at и
                        результат. Выбирается, если указан at (секунды «времени ядра»)

        ms: сколько длится, число или (от, до).
        """
        look = look or ("kernel" if at is not None else "dots")
        if look not in LOOKS:
            raise SceneError(f"Неизвестный вид задачи {look!r}; допустимы {LOOKS}")
        style = _style(style) or RESULT_STYLES.get(result)

        if look == "dots":
            self.steps.append(
                {"op": "dots", "label": str(label), "status": str(result), "style": style, "ms": _delay(ms), "count": 14}
            )
            if note:
                self._text("  " + note, "dim")
        elif look == "unit":
            bad = result in ("WARN", "FAIL")
            mark = UNIT_MARKS.get(result, str(result).center(6))
            parts = [[f"[{mark}] ", style], [str(done or label), style if bad else None]]
            if note:
                parts.append([note, "dim"])
            self.steps.append({"op": "spin", "pending": [[f"[  ..  ] {label}", "dim"]], "done": parts, "ms": _delay(ms)})
        else:
            if at is None:
                raise SceneError("look='kernel' требует at")
            ms = max(0, (at - self._clock) * 1000)
            self._clock = at
            parts = [[f"{_stamp(at)}  {label} ", None], [str(result), style]]
            if note:
                parts.append([" " + note, "dim"])
            self.steps.append(
                {"op": "spin", "pending": [[f"{_stamp(None)}  {label} ", None]], "done": parts, "ms": _ms(ms)}
            )
        return self.blank()

    def log(self, at, tag, message, style=None):
        """Строка ядра: «время  подсистема  текст». Пауза перед ней равна разнице времён."""
        self.wait(max(0, (at - self._clock) * 1000))
        self._clock = at
        return self.say(_stamp(at), "  ", (f"{tag:<7}", "dim"), f" {message}", style=style)

    def burst(self, *lines, gap=(8, 45)):
        """Несколько строк почти сразу, с короткими случайными паузами: так приходит пачка.
        Строка это текст или список частей (как у say)."""
        for line in lines:
            self.say(*(line if isinstance(line, (list, tuple)) and not _is_part(line) else (line,)))
            self.wait(gap)
        return self

    def bar(self, label, *, ms=1200, width=24):
        """Полоса прогресса «[#####-----]  50%», заполняется за ms."""
        self.steps.append({"op": "bar", "label": str(label), "ms": _delay(ms), "width": _ms(width, "width")})
        return self.blank()

    def count(self, label, to, *, unit="", ms=1400, width=17, result=None, note=None):
        """Число растёт от 0 до to, как проверка памяти: «Memory Testing:  64000K OK»."""
        self.steps.append(
            {"op": "count", "label": str(label).ljust(width), "to": int(to), "unit": str(unit), "ms": _delay(ms)}
        )
        if result:
            self._text(" " + result, RESULT_STYLES.get(result))
        if note:
            self._text("  " + note, "dim")
        return self.blank()

    def countdown(self, template, seconds):
        """Обратный отсчёт: template содержит {n}, например «Auto-boot in {n}s...»."""
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 600:
            raise SceneError(f"seconds должно быть целым от 1 до 600, получено {seconds!r}")
        self.steps.append({"op": "countdown", "template": str(template), "seconds": seconds})
        return self.blank()

    # ---------- время и эффекты ----------

    def wait(self, ms):
        """Пауза: число мс или (от, до)."""
        self.steps.append({"op": "wait", "ms": _delay(ms)})
        return self

    def read(self, per_char=4, min_ms=900, max_ms=4500):
        """Дать прочитать то, что на экране: пауза растёт с числом символов (per_char мс
        на символ), но не короче min_ms и не длиннее max_ms. Ставится перед cut()."""
        self.steps.append(
            {"op": "read", "per_char": _ms(per_char, "per_char"), "min_ms": _ms(min_ms, "min_ms"), "max_ms": _ms(max_ms, "max_ms")}
        )
        return self

    def clear(self):
        self.steps.append({"op": "clear"})
        return self

    def cut(self):
        """Смена режима вывода: короткий чёрный кадр и чистый экран."""
        self.steps.append({"op": "cut"})
        return self

    def flash(self):
        self.steps.append({"op": "flash"})
        return self

    def glitch(self, id, to, *, frames=14):
        """Текст, ранее выведенный с этим id, портится и становится to (только отличающиеся буквы)."""
        self.steps.append({"op": "glitch", "id": id, "to": str(to), "frames": _ms(frames, "frames")})
        return self

    # ---------- ветвление ----------

    def one_of(self, *scenes):
        if not scenes:
            raise SceneError("one_of без вариантов")
        self.steps.append({"op": "one_of", "scenes": [_steps(s) for s in scenes]})
        return self

    def choice(self, id, options, *, prompt="Select"):
        if not options:
            raise SceneError("choice без вариантов")
        self.steps.append(
            {"op": "choice", "id": id, "prompt": prompt, "options": [o.to_dict() for o in options]}
        )
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
