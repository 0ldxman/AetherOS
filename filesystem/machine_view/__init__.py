"""

Как собирается вид (docs/storage-spec.md, раздел 3):
  1. Монтирования машины с точкой, от мелкой к глубокой, при равной глубине по порядку.
  2. Каждый том кладёт свои размещения под точку. Новая точка закрывает всё, что лежало под ней (затенение); та же точка
     складывается стопкой (объединение): одноимённая запись верхнего слоя перекрывает нижнюю, надгробие скрывает нижний файл.
  3. Сразу после слоя к нему применяется слой игрока над его экземпляром: удаления, правки, свои файлы.

Запись (put, remove, move, copy...) идёт в слой игрока: новый файл в верхний слой, покрывающий путь, правка существующего в
слой, откуда пришла запись. База не меняется.
"""
from filesystem.machine_view.entries import DATA_LIMIT, DIR, FILE, ITEM_PREFETCH, BadName, Entry, Layer, Occupied, ReadOnly, inner_paths
from filesystem.machine_view.view import MachineView, view_for

__all__ = ["DATA_LIMIT", "BadName", "DIR", "Entry", "FILE", "ITEM_PREFETCH", "Layer", "MachineView", "Occupied", "ReadOnly", "inner_paths", "view_for"]
