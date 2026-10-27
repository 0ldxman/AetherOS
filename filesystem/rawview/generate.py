"""Сборка байтов файла: источник, формат, слои."""
from dataclasses import dataclass

from django.conf import settings

from filesystem.rawview import encodings, formats, keys, signatures
from filesystem.rawview.noise import noise, stable
from filesystem.rawview.source import READ_LIMIT, resolve_payload
from filesystem.states.compiler import StateError, compile_text
from filesystem.states.stack import build_stack, load_progress

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


def layers_of(machine_file, session_state=""):
    """Эффективный стек файла для этой сессии, верхний слой первым."""
    text = machine_file.state or ""
    try:
        canonical = compile_text(text) if text.strip() else []
        return build_stack(canonical, load_progress(session_state or "", text))
    except (StateError, ValueError):
        return []              # описание файла с ошибкой (старые данные): байты показываются как у файла без слоёв


def generated_size(machine_file):
    """Размер файла, на который ничто не указывает: указанный автором или выдуманный, всегда один и тот же."""
    if machine_file.file_type == "DIRECTORY":
        return 4096
    if machine_file.size is not None:
        return machine_file.size
    return stable(f"{machine_file.machine.hostname}:{machine_file.path}", GENERATED_MIN, GENERATED_MAX)


def _asset_bytes(payload):
    asset, reader = payload.meta["asset"], payload.meta.get("reader")
    try:
        if reader is not None:
            return reader(asset)
        from assets.services import read_asset_bytes

        return read_asset_bytes(asset, READ_LIMIT)
    except Exception:
        return None


def _content(machine_file, payload, fmt, seed):
    """Байты файла без слоёв: настоящие данные в контейнере формата или шум."""
    if payload.kind == "asset":
        real = _asset_bytes(payload)
        if real is None:
            size = payload.size if payload.size is not None else generated_size(machine_file)
            real = noise(seed + ":asset", size)
        if fmt and formats.known(fmt):
            if formats.has_image(fmt):
                return formats.build(fmt, b"", payload.meta, image=real, seed=seed)
            return formats.build(fmt, real, payload.meta, seed=seed)
        return real

    if payload.kind in ("wiki", "map", "mail"):
        wanted = fmt or payload.fmt or ("msg" if payload.kind == "mail" else "rec")
        return formats.build(wanted, payload.body, payload.meta, seed=seed, views=payload.views)

    if payload.kind in ("key", "slice", "signature"):
        return payload.body

    if payload.kind == "archive":
        return payload.build()

    if payload.kind == "app":
        text = f"path: {payload.meta['path']}\n".encode()
        head = formats.magic("app")
        return head + text + noise(seed + ":app", max(0, 256 - len(head) - len(text)))

    body = noise(seed, generated_size(machine_file))
    return formats.build(fmt, body, {}, seed=seed) if fmt and formats.known(fmt) else body


def _core(machine_file, payload, fmt, seed):
    """Содержимое файла вместе с блоками его ключей (FileKey): они лежат под слоями и открываются вместе с ними."""
    data = _content(machine_file, payload, fmt, seed)
    data = keys.embed(data, keys.slugs_of(machine_file), seed, real=payload.kind in ("asset", "archive"), locked=payload.locked)
    if payload.locked and payload.kind in ("wiki", "map", "mail"):
        # доступа нет: место, где лежит тело, закрывается шумом той же длины, остальное (заголовки формата) как есть
        for variant in formats.variants(payload.body, payload.views):
            data = data.replace(variant, noise(seed + ":body", len(variant)))
    signed = [(row.key.slug, row.date, row.valid) for row in machine_file.signatures.select_related("key").order_by("key__slug")]
    return signatures.embed(data, signed, seed, locked=payload.locked)


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


def build_raw(machine_file, session_state="", keys=frozenset(), reader=None, viewer=None):
    """Байты файла для игрока с этими ключами и этим прогрессом по слоям."""
    seed = f"{machine_file.machine.hostname}:{machine_file.path}"
    payload = resolve_payload(machine_file, keys, reader, viewer)
    stack = layers_of(machine_file, session_state)

    # слой disguised главнее: он говорит, в какую упаковку завёрнуто содержимое
    disguised = next((layer for layer in stack if layer.state.name == "disguised"), None)
    fmt = str(disguised.params["format"]).strip().lower() if disguised else payload.fmt

    payload.meta.setdefault("host", machine_file.machine.hostname)
    data = _core(machine_file, payload, fmt, seed)

    bad = ()
    for layer in reversed(stack):         # от нижнего слоя к верхнему
        name, params = layer.state.name, layer.params
        bad = ()
        if name == "binary":
            data = encodings.encode(str(params.get("encoding", "")).strip().lower(), data)
        elif name == "base64":
            data = encodings.wrap_base64(data)
        elif name == "encrypted":
            data = noise(seed + ":enc", len(data))
        elif name in ("damaged", "corrupted"):
            bad = tuple(_bad_blocks(len(data), seed))
            data = _damage(data, seed)
        elif name == "shifted":
            skip = int(params.get("skip", 0))
            data = noise(seed + ":skip", skip * BLOCK) + data + noise(seed + ":tail", BLOCK)

    return RawFile(data, format=fmt, bad=bad)
