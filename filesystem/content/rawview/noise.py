import hashlib


def noise(seed, length, offset=0):
    """Псевдослучайные байты: для одного seed всегда одни и те же, читать можно с любого места."""
    if length <= 0:
        return b""
    first, last = offset // 32, (offset + length - 1) // 32
    data = b"".join(hashlib.sha256(f"{seed}:{i}".encode()).digest() for i in range(first, last + 1))
    start = offset - first * 32
    return data[start:start + length]


def stable(seed, low, high):
    """Число от low до high, у одного seed всегда одно и то же."""
    value = int.from_bytes(hashlib.sha256(str(seed).encode()).digest()[:4], "big")
    return low + value % (high - low + 1)
