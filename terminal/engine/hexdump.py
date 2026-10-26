"""Hexdump в духе hexdump -C, но по 8 байт в строке: окно терминала узкое. Смещение, байты, ASCII справа;
повторяющиеся строки сворачиваются в «*»."""

WIDTH = 8


def hexdump(data, start=0):
    lines, previous, folded = [], None, False
    for offset in range(0, len(data), WIDTH):
        row = data[offset:offset + WIDTH]
        if row == previous and offset + WIDTH < len(data):
            if not folded:
                lines.append("*")
                folded = True
            continue
        previous, folded = row, False
        cells = [f"{byte:02x}" for byte in row] + ["  "] * (WIDTH - len(row))
        text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in row)
        lines.append(f"{start + offset:08x}  {' '.join(cells)}  |{text}|")
    return lines
