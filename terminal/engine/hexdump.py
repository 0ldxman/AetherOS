"""Hexdump как у hexdump -C: смещение, 16 байт в двух группах, ASCII справа; повторяющиеся строки сворачиваются в «*»."""


def hexdump(data, start=0):
    lines, previous, folded = [], None, False
    for offset in range(0, len(data), 16):
        row = data[offset:offset + 16]
        if row == previous and offset + 16 < len(data):
            if not folded:
                lines.append("*")
                folded = True
            continue
        previous, folded = row, False
        cells = [f"{byte:02x}" for byte in row] + ["  "] * (16 - len(row))
        text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in row)
        lines.append(f"{start + offset:08x}  {' '.join(cells[:8])}  {' '.join(cells[8:])}  |{text}|")
    return lines
