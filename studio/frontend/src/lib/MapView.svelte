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
  // Карта для Студии: свой простой стиль (вода, острова, провинции), без внешних сервисов. Провинции красятся по коду (adm1_code)
  // из colors; выделенные подсвечены; клик, наведение и выделение рамкой отдаются родителю. Остальное (маркеры, линии сцены)
  // родитель рисует сам через onready(map).
  import "maplibre-gl/dist/maplibre-gl.css";
  import { onDestroy, onMount } from "svelte";

  let { colors = {}, selected = [], boxMode = false, flat = true, center = [10, 30], zoom = 2, interactive = true,
        onpick, onhover, onbox, onready, oncamera }: {
    colors?: Record<string, string>;
    selected?: string[];
    boxMode?: boolean;                // тянуть рамку вместо сдвига карты
    flat?: boolean;
    center?: [number, number];
    zoom?: number;
    interactive?: boolean;
    onpick?: (code: string | null, event: { shift: boolean; alt: boolean; lng: number; lat: number }) => void;
    onhover?: (code: string | null) => void;
    onbox?: (codes: string[], remove: boolean) => void;
    onready?: (map: maplibregl.Map) => void;
    oncamera?: (view: { lng: number; lat: number; zoom: number }) => void;
  } = $props();

  const EMPTY = "#26313c";
  let box: HTMLDivElement;
  let frame = $state<{ x: number; y: number; w: number; h: number } | null>(null);
  let map: maplibregl.Map | undefined;
  let ready = $state(false);

  export function getMap(): maplibregl.Map | undefined { return map; }
  export function flyTo(lng: number, lat: number, to?: number) { map?.flyTo({ center: [lng, lat], zoom: to ?? Math.max(map.getZoom(), 4), duration: 600 }); }

  function colorExpression(table: Record<string, string>): maplibregl.ExpressionSpecification | string {
    const rows = Object.entries(table);
    if (!rows.length) return EMPTY;
    const expr: unknown[] = ["match", ["get", "adm1_code"]];
    for (const [code, color] of rows) expr.push(code, color);
    expr.push(EMPTY);
    return expr as maplibregl.ExpressionSpecification;
  }

  const only = (codes: string[]): maplibregl.FilterSpecification => ["in", ["get", "adm1_code"], ["literal", codes]];

  onMount(() => {
    addProtocol();
    map = new maplibregl.Map({
      container: box, center, zoom, minZoom: 0.5, maxZoom: 9, interactive, attributionControl: false, dragRotate: false,
      style: { version: 8, sources: {}, layers: [{ id: "water", type: "background", paint: { "background-color": "#0a1722" } }] },
    });
    map.touchZoomRotate.disableRotation();
    map.on("style.load", () => map!.setProjection({ type: flat ? "mercator" : "globe" }));
    map.on("load", () => {
      const m = map!;
      m.addSource("lands", { type: "geojson", data: dataUrl("aether_lands.geojson") });
      m.addLayer({ id: "lands", type: "fill", source: "lands", paint: { "fill-color": "#16222d" } });
      m.addSource("adm1", { type: "vector", url: "pmtiles://" + dataUrl("aether_provinces.pmtiles") });
      const src = { source: "adm1", "source-layer": "aether_provinces" } as const;
      m.addLayer({ id: "adm1-fill", type: "fill", ...src, paint: { "fill-color": colorExpression(colors), "fill-opacity": 0.88 } });
      m.addLayer({ id: "adm1-line", type: "line", ...src, paint: { "line-color": "rgba(220,235,255,.28)", "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.3, 6, 1] } });
      m.addLayer({ id: "adm1-sel", type: "fill", ...src, filter: only([]), paint: { "fill-color": "#ffffff", "fill-opacity": 0.32 } });
      m.addLayer({ id: "adm1-sel-line", type: "line", ...src, filter: only([]), paint: { "line-color": "#ffffff", "line-width": 2 } });
      m.addLayer({ id: "adm1-hover", type: "line", ...src, filter: only([]), paint: { "line-color": "#ffd23f", "line-width": 2.5 } });

      m.on("mousemove", "adm1-fill", (e) => {
        const code = e.features?.[0]?.properties?.adm1_code ?? null;
        m.setFilter("adm1-hover", only(code ? [code] : []));
        m.getCanvas().style.cursor = boxMode ? "crosshair" : "pointer";
        onhover?.(code);
      });
      m.on("mouseleave", "adm1-fill", () => {
        m.setFilter("adm1-hover", only([]));
        m.getCanvas().style.cursor = "";
        onhover?.(null);
      });
      m.on("click", (e) => {
        if (boxMode) return;
        const hit = m.queryRenderedFeatures(e.point, { layers: ["adm1-fill"] })[0];
        onpick?.(hit?.properties?.adm1_code ?? null, { shift: e.originalEvent.shiftKey, alt: e.originalEvent.altKey, lng: e.lngLat.lng, lat: e.lngLat.lat });
      });
      m.on("moveend", () => { const c = m.getCenter(); oncamera?.({ lng: c.lng, lat: c.lat, zoom: m.getZoom() }); });
      ready = true;
      onready?.(m);
    });
  });

  onDestroy(() => map?.remove());

  $effect(() => {
    const table = colors;
    if (ready) map!.setPaintProperty("adm1-fill", "fill-color", colorExpression(table));
  });
  $effect(() => {
    const codes = selected;
    if (!ready) return;
    map!.setFilter("adm1-sel", only(codes));
    map!.setFilter("adm1-sel-line", only(codes));
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
    const codes = [...new Set(found.map((f) => String(f.properties?.adm1_code)).filter(Boolean))];
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
