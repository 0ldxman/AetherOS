"""Сборка байтов файла: источник, формат, слои."""
from dataclasses import dataclass

from django.conf import settings

from filesystem.content.rawview import encodings, formats, keys, signatures
from filesystem.content.rawview.noise import noise, stable
from filesystem.content.sources import READ_LIMIT, payload_for
from filesystem.layers.compiler import StateError, compile_text
from filesystem.layers.stack import build_stack, load_progress

BLOCK = 512
GENERATED_MIN, GENERATED_MAX = 180, 48_000


@dataclass
class RawFile:
    data: bytes
    format: str | None = None     # какой формат у файла «на самом деле» (по слою disguised или по записи вики)
    bad: tuple = ()               # блоки (по 512 байт) последнего слоя damaged, если он сверху: чтение их даёт ошибку

    @property
    def size(self):
        return len(self.data)


def layers_of(state, progress=""):
    """Эффективный стек файла для этой сессии, верхний слой первым. state: слои автора, progress: прогресс игрока."""
    text = state or ""
    try:
        canonical = compile_text(text) if text.strip() else []
        return build_stack(canonical, load_progress(progress or "", text))
    except (StateError, ValueError):
        return []              # описание файла с ошибкой (старые данные): байты показываются как у файла без слоёв


def seed_of(entry):
    """Зерно шума файла: у объекта его слаг (копии и переносы дают те же байты), у файла игрока машина и путь."""
    if entry.item is not None:
        return f"item:{entry.item.slug}"
    host = entry.machine.hostname if entry.machine is not None else ""
    return f"{host}:{entry.path}"


def generated_size(entry):
    """Размер файла, на который ничто не указывает: указанный автором или выдуманный, всегда один и тот же."""
    if entry.is_dir:
        return 4096
    if entry.item is not None and entry.item.size is not None:
        return entry.item.size
    return stable(seed_of(entry), GENERATED_MIN, GENERATED_MAX)


def _asset_bytes(payload):
    asset, reader = payload.meta["asset"], payload.meta.get("reader")
    try:
        if reader is not None:
            return reader(asset)
        from assets.services import read_asset_bytes

        return read_asset_bytes(asset, READ_LIMIT)
    except Exception:
        return None


def _content(entry, payload, fmt, seed):
    """Байты файла без слоёв: настоящие данные в контейнере формата или шум. Как их собирать, говорит layout источника."""
    if payload.layout == "asset":
        real = _asset_bytes(payload)
        if real is None:
            size = payload.size if payload.size is not None else generated_size(entry)
            real = noise(seed + ":asset", size)
        if fmt and formats.known(fmt):
            if formats.has_image(fmt):
                return formats.build(fmt, b"", payload.meta, image=real, seed=seed)
            return formats.build(fmt, real, payload.meta, seed=seed)
        return real

    if payload.layout == "format":
        wanted = fmt or payload.fmt or payload.default_fmt
        return formats.build(wanted, payload.body, payload.meta, seed=seed, views=payload.views)

    if payload.layout == "raw":
        return payload.body

    if payload.layout == "archive":
        return payload.build()

    if payload.layout == "app":
        text = f"path: {payload.meta['path']}\n".encode()
        head = formats.magic("app")
        return head + text + noise(seed + ":app", max(0, 256 - len(head) - len(text)))

    body = noise(seed, generated_size(entry))
    return formats.build(fmt, body, {}, seed=seed) if fmt and formats.known(fmt) else body


def _core(entry, payload, fmt, seed):
    """Содержимое файла вместе с блоками его ключей (ItemKey): они лежат под слоями и открываются вместе с ними."""
    data = _content(entry, payload, fmt, seed)
    if payload.locked and payload.layout == "raw":
        data = noise(seed + ":body", len(data))                   # закрытый текст без контейнера: шум той же длины
    data = keys.embed(data, keys.slugs_of(entry.item), seed, real=payload.real, locked=payload.locked)
    if payload.locked and payload.layout == "format":
        # доступа нет: место, где лежит тело, закрывается шумом той же длины, остальное (заголовки формата) как есть
        for variant in formats.variants(payload.body, payload.views):
            data = data.replace(variant, noise(seed + ":body", len(variant)))
    signed = signatures_of(entry.item)
    return signatures.embed(data, signed, seed, locked=payload.locked)


def _cipher(length, params, seed):
    """Зашифрованный файл: пакеты в духе OpenPGP (ключ получателя, пароль), дальше шум. Длина не меняется."""
    head = b""
    if params.get("key"):
        head += b"\x85\x01\x0c\x03" + keys.key_id(str(params["key"]).strip().lower()) + noise(seed + ":pk", 4)    # зашифровано ключом: его ID
    if params.get("password") not in (None, ""):
        head += b"\x8c\x0d\x04\x09\x03\x08" + noise(seed + ":salt", 8) + b"\x00\x0c"                    # зашифровано паролем (соль)
    return (head + noise(seed + ":enc", max(0, length - len(head))))[:length]


def _bad_blocks(length, seed):
    """Номера повреждённых блоков файла такой длины."""
    blocks = max(1, -(-length // BLOCK))
    return sorted({stable(f"{seed}:bad{i}", 0, blocks - 1) for i in range(min(blocks, stable(seed, 3, 9)))})


def _damage(data, seed):
    """Повреждённые блоки: несколько блоков заменены шумом, длина не меняется."""
    out = bytearray(data)
    for number in _bad_blocks(len(data), seed):
        start = number * BLOCK
        out[start:start + BLOCK] = noise(f"{seed}:blk{number}", len(out[start:start + BLOCK]))
    return bytes(out)


def signatures_of(item):
    """Подписи, встроенные автором в объект: [(слаг ключа, дата, верна ли)]."""
    if item is None:
        return []
    return sorted(((row.key.slug, row.date, row.valid) for row in item.signatures.all()), key=lambda found: found[0])


def build_raw(entry, view=None, keys=frozenset(), reader=None, viewer=None):
    """Байты файла для игрока с этими ключами и этим прогрессом по слоям. entry: файл вида машины, view нужен архиву."""
    seed = seed_of(entry)
    payload = payload_for(entry, view, keys, reader, viewer)
    stack = layers_of(entry.state, entry.progress)

    # слой disguised главнее: он говорит, в какую упаковку завёрнуто содержимое
    disguised = next((layer for layer in stack if layer.state.name == "disguised"), None)
    fmt = str(disguised.params["format"]).strip().lower() if disguised else payload.fmt

    payload.meta.setdefault("host", entry.machine.hostname if entry.machine is not None else "")
    data = _core(entry, payload, fmt, seed)

    bad = ()
    for layer in reversed(stack):         # от нижнего слоя к верхнему
        name, params = layer.state.name, layer.params
        bad = ()
        if name == "binary":
            data = encodings.encode(str(params.get("encoding", "")).strip().lower(), data)
        elif name == "encrypted":
            data = _cipher(len(data), params, seed)
        elif name in ("damaged", "corrupted"):
            bad = tuple(_bad_blocks(len(data), seed))
            data = _damage(data, seed)
        elif name == "shifted":
            skip = int(params.get("skip", 0))
            data = noise(seed + ":skip", skip * BLOCK) + data + noise(seed + ":tail", BLOCK)

    return RawFile(data, format=fmt, bad=bad)
