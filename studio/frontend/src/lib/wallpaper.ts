// Картинка и узор рабочего стола ОС: значения по умолчанию и плитка узора для миниатюр (сервер рисует так же, machines/world/wallpaper.py).
export type Wallpaper = {
  file_id: string; file_name: string; mode: string; opacity: number;
  pattern: string; pattern_color: string; pattern_size: number; pattern_opacity: number;
};

export const WALLPAPER_DEFAULT: Wallpaper = { file_id: "", file_name: "", mode: "center", opacity: 100, pattern: "none", pattern_color: "#ffffff", pattern_size: 24, pattern_opacity: 15 };
export const WALL_MODES: { key: string; label: string; hint: string }[] = [
  { key: "center", label: "По центру", hint: "Реальный размер по центру экрана, большая картинка уменьшается, чтобы влезть. Подходит для логотипа." },
  { key: "cover", label: "Растянуть", hint: "Картинка заполняет весь экран, лишнее по краям обрезается." },
];
export const WALL_PATTERNS: { key: string; label: string }[] = [
  { key: "none", label: "Нет" }, { key: "grid", label: "Сетка" }, { key: "dots", label: "Точки" }, { key: "plus", label: "Плюсики" },
];

/** Плитка узора как адрес data:image/svg+xml. */
export function tileUrl(pattern: string, color: string, size: number): string {
  const mid = size / 2;
  const shape = pattern === "grid" ? `<path d="M0 .5H${size}M.5 0V${size}" stroke="${color}" stroke-width="1" fill="none"/>`
    : pattern === "dots" ? `<circle cx="${mid}" cy="${mid}" r="1.4" fill="${color}"/>`
    : `<path d="M${mid - 4} ${mid}H${mid + 4}M${mid} ${mid - 4}V${mid + 4}" stroke="${color}" stroke-width="1" fill="none"/>`;
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">${shape}</svg>`)}`;
}
