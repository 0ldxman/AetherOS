// Что это за файл: значок и подпись для файлового менеджера. Одна логика для таблицы и дерева.
import type { Schemas } from "./api";

export type Kind = "folder" | "file" | "doc" | "image" | "archive" | "key" | "object";

const IMAGES = new Set(["jpg", "jpeg", "png", "gif", "bmp", "ico", "webp", "svg"]);
const ARCHIVES = new Set(["zip", "7z", "gz", "bz2", "rar", "tar", "xz", "tgz", "pak"]);

/** Расширение имени: «.txt» или пусто (скрытые файлы вроде «.env» расширения не имеют). */
export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot).toLowerCase() : "";
}

export type Described = { kind: Kind; label: string; own: boolean };

/** Значок и подпись узла диска. Файл без объекта и объект различаются: подпись начинается со слов «Файл» и «Объект». */
export function describe(node: Schemas["Node"], formats: Schemas["Format"][], count = 0): Described {
  if (node.kind === "folder") return { kind: "folder", own: false, label: count ? `Папка · ${count} ${plural(count)}` : "Папка · пусто" };
  const found = formats.find((item) => item.name === node.format);
  const ext = extensionOf(node.name);
  const shown = found ? found.title || found.name : ext ? ext : "";
  const name = node.format || ext.slice(1);
  let kind: Kind = node.item ? "object" : "file";
  if (found?.markup) kind = "doc";
  else if (node.format === "key") kind = "key";
  else if (IMAGES.has(name)) kind = "image";
  else if (ARCHIVES.has(name)) kind = "archive";
  const own = !node.item;
  const what = own ? "Файл" : "Объект";
  return { kind, own, label: shown ? `${what} · ${shown}` : what };
}

function plural(count: number): string {
  const tail = count % 100;
  const last = count % 10;
  return tail >= 11 && tail <= 14 ? "элементов" : last === 1 ? "элемент" : last >= 2 && last <= 4 ? "элемента" : "элементов";
}

/** Что сказать о типе файла по имени, пока его печатают (диалог «Новый файл»). */
export function typeHint(name: string, formats: Schemas["Format"][]): string {
  const ext = extensionOf(name.trim());
  if (!name.trim()) return "Расширение любое: оно станет типом файла.";
  if (!ext) return "Без расширения: обычный текстовый файл.";
  const found = formats.find((item) => item.extension.toLowerCase() === ext);
  return found
    ? `Тип: ${found.title || found.name} (${ext}).`
    : `Тип: ${ext}. Такого формата нет в каталоге, файл останется текстом с этим расширением.`;
}
