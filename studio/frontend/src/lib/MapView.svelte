<script lang="ts" module>
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";

  let protocolAdded = false;
  function addProtocol() {
    if (protocolAdded) return;
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    protocolAdded = true;
  }

  /** Адрес файла данных карты (абсолютный: так его читают и MapLibre, и pmtiles). */
  export function dataUrl(name: string): string {
    return new URL(window.STUDIO.mapData + name, location.href).href;
  }
</script>

<script lang="ts">
  // Карта для Студии: свой простой стиль (вода, острова, провинции), без внешних сервисов. Цвет провинции, наведение и выделение
  // это feature-state (promoteId adm1_code): меняется одна провинция, тайлы не перечитываются. Раньше они шли через setFilter и
  // paint-выражение со всеми кодами, и MapLibre после каждого движения мыши заново разбирал тяжёлые тайлы: подсветка отставала на секунды.
  // Клик, наведение и рамка отдаются родителю. Остальное (маркеры, линии сцены) родитель рисует сам через onready(map).
  import "maplibre-gl/dist/maplibre-gl.css";
  import { onDestroy, onMount, untrack } from "svelte";
  import { LOOKS, type MapView } from "./mapLooks";

  let { colors = {}, selected = [], boxMode = false, flat = true, center = [10, 30], zoom = 2, interactive = true, look = "dark", view = "political",
        onpick, onhover, onbox, onready, oncamera }: {
    colors?: Record<string, string>;
    selected?: string[];
    boxMode?: boolean;                // тянуть рамку вместо сдвига карты
    flat?: boolean;
    center?: [number, number];
    zoom?: number;
    interactive?: boolean;
    look?: string;                    // стиль: dark, maps, scan (lib/mapLooks)
    view?: MapView;                   // политическая или физическая (без провинций)
    onpick?: (code: string | null, event: { shift: boolean; alt: boolean; lng: number; lat: number }) => void;
    onhover?: (code: string | null) => void;
    onbox?: (codes: string[], remove: boolean) => void;
    onready?: (map: maplibregl.Map) => void;
    oncamera?: (view: { lng: number; lat: number; zoom: number }) => void;
  } = $props();

  const SOURCE = "adm1";
  const LAYER = "aether_provinces";
  const home = untrack(() => ({ center: [...center] as [number, number], zoom }));
  const style = $derived(LOOKS[look] ?? LOOKS.dark);

  let box: HTMLDivElement;
  let frame = $state<{ x: number; y: number; w: number; h: number } | null>(null);
  let map: maplibregl.Map | undefined;
  let ready = $state(false);

  export function getMap(): maplibregl.Map | undefined { return map; }
  export function flyTo(lng: number, lat: number, to?: number) { map?.flyTo({ center: [lng, lat], zoom: to ?? Math.max(map.getZoom(), 4), duration: 600 }); }
  export function zoomBy(delta: number) { map?.easeTo({ zoom: map.getZoom() + delta, duration: 200 }); }
  export function reset() { map?.flyTo({ center: home.center, zoom: home.zoom, duration: 600 }); }

  const ref = (id: string) => ({ source: SOURCE, sourceLayer: LAYER, id });
  const flag = (key: string) => ["boolean", ["feature-state", key], false] as maplibregl.ExpressionSpecification;

  // ---------- что уже записано в feature-state ----------
  const painted = new Map<string, string>();
  let picked = new Set<string>();
  let hovered: string | null = null;

  function setHover(code: string | null) {
    if (code === hovered) return;
    const m = map!;
    if (hovered) m.setFeatureState(ref(hovered), { hover: false });
    if (code) m.setFeatureState(ref(code), { hover: true });
    hovered = code;
    onhover?.(code);
  }

  function applyColors(table: Record<string, string>) {
    const m = map!;
    for (const [code, color] of Object.entries(table)) {
      if (painted.get(code) === color) continue;
      m.setFeatureState(ref(code), { color });
      painted.set(code, color);
    }
    for (const code of [...painted.keys()]) {
      if (code in table) continue;
      m.removeFeatureState(ref(code), "color");
      painted.delete(code);
    }
  }

  function applySelection(codes: string[]) {
    const m = map!;
    const next = new Set(codes);
    for (const code of picked) if (!next.has(code)) m.setFeatureState(ref(code), { selected: false });
    for (const code of next) if (!picked.has(code)) m.setFeatureState(ref(code), { selected: true });
    picked = next;
  }

  function applyLook() {
    const m = map!;
    const s = style;
    m.setPaintProperty("water", "background-color", s.water);
    m.setPaintProperty("lands", "fill-color", s.land);
    // физическая карта: провинции это суша (острова одни не дают континентов), без цветов владельцев и границ
    m.setPaintProperty("adm1-fill", "fill-color", view === "physical" ? s.land : ["to-color", ["coalesce", ["feature-state", "color"], s.empty]]);
    m.setPaintProperty("adm1-fill", "fill-opacity", view === "physical" ? 1 : s.opacity);
    m.setPaintProperty("adm1-line", "line-color", s.line);
    m.setPaintProperty("adm1-line", "line-opacity", view === "physical" ? 0 : 1);
    m.setPaintProperty("adm1-sel", "fill-color", s.pick);
    m.setPaintProperty("adm1-sel-line", "line-color", s.pick);
    m.setPaintProperty("adm1-hover", "line-color", s.hover);
  }

  onMount(() => {
    addProtocol();
    map = new maplibregl.Map({
      container: box, center, zoom, minZoom: 0.5, maxZoom: 9, interactive, attributionControl: false, dragRotate: false,
      style: { version: 8, sources: {}, layers: [{ id: "water", type: "background", paint: { "background-color": style.water } }] },
    });
    map.touchZoomRotate.disableRotation();
    map.on("style.load", () => map!.setProjection({ type: flat ? "mercator" : "globe" }));
    map.on("load", () => {
      const m = map!;
      m.addSource("lands", { type: "geojson", data: dataUrl("aether_lands.geojson") });
      m.addLayer({ id: "lands", type: "fill", source: "lands", paint: { "fill-color": style.land } });
      m.addSource(SOURCE, { type: "vector", url: "pmtiles://" + dataUrl("aether_provinces.pmtiles"), promoteId: { [LAYER]: "adm1_code" } });
      const src = { source: SOURCE, "source-layer": LAYER } as const;
      m.addLayer({ id: "adm1-fill", type: "fill", ...src, paint: { "fill-color": ["to-color", ["coalesce", ["feature-state", "color"], style.empty]], "fill-opacity": style.opacity } });
      m.addLayer({ id: "adm1-line", type: "line", ...src, paint: { "line-color": style.line, "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.3, 6, 1] } });
      m.addLayer({ id: "adm1-sel", type: "fill", ...src, paint: { "fill-color": style.pick, "fill-opacity": ["case", flag("selected"), 0.32, 0] } });
      m.addLayer({ id: "adm1-sel-line", type: "line", ...src, paint: { "line-color": style.pick, "line-width": ["case", flag("selected"), 2, 0] } });
      m.addLayer({ id: "adm1-hover", type: "line", ...src, paint: { "line-color": style.hover, "line-width": ["case", flag("hover"), 2.5, 0] } });

      m.on("mousemove", "adm1-fill", (e) => {
        const feature = e.features?.[0];
        const code = feature ? String(feature.id ?? feature.properties?.adm1_code) : null;
        m.getCanvas().style.cursor = boxMode ? "crosshair" : "pointer";
        setHover(code);
      });
      m.on("mouseleave", "adm1-fill", () => {
        m.getCanvas().style.cursor = "";
        setHover(null);
      });
      m.on("click", (e) => {
        if (boxMode) return;
        const hit = m.queryRenderedFeatures(e.point, { layers: ["adm1-fill"] })[0];
        onpick?.(hit ? String(hit.id ?? hit.properties?.adm1_code) : null, { shift: e.originalEvent.shiftKey, alt: e.originalEvent.altKey, lng: e.lngLat.lng, lat: e.lngLat.lat });
      });
      m.on("moveend", () => { const c = m.getCenter(); oncamera?.({ lng: c.lng, lat: c.lat, zoom: m.getZoom() }); });
      ready = true;
      onready?.(m);
    });
  });

  onDestroy(() => map?.remove());

  $effect(() => {
    const table = colors;
    if (ready) applyColors(table);
  });
  $effect(() => {
    const codes = selected;
    if (ready) applySelection(codes);
  });
  $effect(() => {
    style; view;
    if (ready) applyLook();
  });
  $effect(() => {
    if (!ready) return;
    if (boxMode) map!.dragPan.disable(); else map!.dragPan.enable();
  });

  // выделение рамкой: тянем прямоугольник, по отпусканию собираем провинции под ним (Alt: убрать из выделения)
  let from: { x: number; y: number } | null = null;
  function down(event: PointerEvent) {
    if (!boxMode || event.button !== 0) return;
    const rect = box.getBoundingClientRect();
    from = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    frame = { x: from.x, y: from.y, w: 0, h: 0 };
    box.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent) {
    if (!from) return;
    const rect = box.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    frame = { x: Math.min(from.x, x), y: Math.min(from.y, y), w: Math.abs(x - from.x), h: Math.abs(y - from.y) };
  }
  function up(event: PointerEvent) {
    if (!from || !frame || !map) return;
    const { x, y, w, h } = frame;
    from = null;
    frame = null;
    if (w < 3 && h < 3) return;
    const found = map.queryRenderedFeatures([[x, y], [x + w, y + h]], { layers: ["adm1-fill"] });
    const codes = [...new Set(found.map((f) => String(f.id ?? f.properties?.adm1_code)).filter(Boolean))];
    onbox?.(codes, event.altKey);
  }
</script>

<div class="wrap" role="presentation" onpointerdown={down} onpointermove={move} onpointerup={up}>
  <div class="map" bind:this={box}></div>
  {#if frame}<div class="frame" style="left:{frame.x}px; top:{frame.y}px; width:{frame.w}px; height:{frame.h}px"></div>{/if}
</div>

<style>
  .wrap { position: relative; width: 100%; height: 100%; }
  .map { position: absolute; inset: 0; }
  .frame { position: absolute; border: 1px dashed var(--accent); background: var(--accent-soft); pointer-events: none; }
  :global(.maplibregl-ctrl-bottom-left), :global(.maplibregl-ctrl-bottom-right) { display: none; }
</style>
