// Пометки сцены карты: тип, цвета палитры и геометрия для рисования в редакторе.
import type { Feature as GeoFeature, FeatureCollection } from "geojson";

export type Point = [number, number];

export type Feature = {
  type: string;
  coords?: Point | Point[];
  token?: string;
  label?: string;
  text?: string;
  color?: string;
  icon?: string;
  width?: number;
  dash?: boolean;
  smooth?: boolean;
  fill?: boolean;
  fill_color?: string;
  fill_style?: string;
  radius_km?: number;
  size?: number;
  offset?: [number, number];
  border?: string;
  url?: string;
  from?: string;
  to?: string;
  key?: string;
};

/** Цвета палитры сцены на тёмной карте (как у страницы карты). */
export const COLOR_HEX: Record<string, string> = {
  red: "#ff5a5f", blue: "#5aa9ff", green: "#3fe0a0", orange: "#ffa13d", purple: "#b58cff", yellow: "#ffd84d", teal: "#3fd0ff", grey: "#9aa5a5",
};
export const COLOR_NAME: Record<string, string> = {
  red: "красный", blue: "синий", green: "зелёный", orange: "оранжевый", purple: "фиолетовый", yellow: "жёлтый", teal: "бирюзовый", grey: "серый",
};
export const hex = (name?: string, fallback = "#ffd84d"): string => COLOR_HEX[name ?? ""] ?? fallback;

export const TYPE_LABEL: Record<string, string> = {
  marker: "Метка", line: "Линия", arrow: "Стрелка", polygon: "Многоугольник", circle: "Круг", text: "Текст", callout: "Выноска", region: "Выделение",
};

export const isPoint = (f: Feature): boolean => ["marker", "circle", "text", "callout"].includes(f.type);
export const isPath = (f: Feature): boolean => ["line", "arrow", "polygon"].includes(f.type);
export const pointOf = (f: Feature): Point => f.coords as Point;
export const pathOf = (f: Feature): Point[] => (f.coords as Point[]) ?? [];

/** Подпись пометки в списке. */
export function title(f: Feature): string {
  const main = f.type === "text" || f.type === "callout" ? f.text : f.type === "region" ? f.token : f.label;
  return main?.trim() || TYPE_LABEL[f.type] || f.type;
}

/** Окружность радиусом km вокруг точки (многоугольник из steps вершин). */
export function circlePolygon(center: Point, km: number, steps = 72): Point[] {
  const [lng, lat] = center;
  const dLat = km / 111.32;
  const dLng = km / (111.32 * Math.max(Math.cos((lat * Math.PI) / 180), 0.05));
  const ring: Point[] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * Math.PI * 2;
    ring.push([lng + dLng * Math.cos(a), Math.max(-89.9, Math.min(89.9, lat + dLat * Math.sin(a)))]);
  }
  return ring;
}

/** Угол стрелки на экране (градусы по часовой, 0 — вверх) от точки a к b. */
export function bearing(a: Point, b: Point): number {
  const dx = (b[0] - a[0]) * Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
  const dy = b[1] - a[1];
  return (Math.atan2(dx, dy) * 180) / Math.PI;
}

/** Линии и площади пометок для слоя карты (точечные рисуются HTML-метками). */
export function toGeoJSON(features: Feature[]): FeatureCollection {
  const out: GeoFeature[] = [];
  features.forEach((f, i) => {
    const color = hex(f.color, f.type === "polygon" || f.type === "circle" ? hex("yellow") : hex("red"));
    const base = { i, color: f.type === "polygon" || f.type === "circle" ? hex(f.fill_color ?? f.color) : color, line: color, fill: f.fill !== false && (f.type === "polygon" || f.type === "circle"), dash: !!f.dash, width: f.width ?? 3 };
    if (f.type === "line" || f.type === "arrow") {
      if (pathOf(f).length >= 2) out.push({ type: "Feature", properties: base, geometry: { type: "LineString", coordinates: pathOf(f) } });
    } else if (f.type === "polygon") {
      const ring = pathOf(f);
      if (ring.length >= 3) out.push({ type: "Feature", properties: base, geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] } });
    } else if (f.type === "circle" && f.coords && f.radius_km) {
      out.push({ type: "Feature", properties: base, geometry: { type: "Polygon", coordinates: [circlePolygon(pointOf(f), f.radius_km)] } });
    }
  });
  return { type: "FeatureCollection", features: out };
}

/** «Привет мир» → «privet-mir»: слаг по названию. */
export function slugify(text: string): string {
  const map: Record<string, string> = { а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya" };
  return text.toLowerCase().split("").map((ch) => map[ch] ?? ch).join("").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}
