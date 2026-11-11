<script lang="ts">
  // Редактор одной сцены: карта с инструментами рисования, список пометок со свойствами, настройки камеры и история снимков.
  // Точечные пометки (метка, текст, выноска) и ручки вершин рисуются HTML-метками, линии, площади и круги слоем карты.
  import maplibregl from "maplibre-gl";
  import type { Feature as GeoFeature } from "geojson";
  import { onDestroy, onMount, untrack, type Snippet } from "svelte";
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import Hint from "../../lib/Hint.svelte";
  import Icon from "../../lib/Icon.svelte";
  import { LOOKS, VIEWS, type MapView as MapViewKind } from "../../lib/mapLooks";
  import MapView from "../../lib/MapView.svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { ask } from "../../lib/confirm.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import DraftState from "../../lib/DraftState.svelte";
  import { SharedForm } from "../../lib/shared.svelte";
  import { bearing, hex, isPath, isPoint, pathOf, pointOf, title, toGeoJSON, TYPE_LABEL, type Feature, type Point } from "../../lib/sceneGeo";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, showDate } from "./shared";
  import FeatureForm from "./FeatureForm.svelte";

  type Form = Schemas["MapSceneIn"];
  type Tool = "select" | "marker" | "line" | "arrow" | "polygon" | "circle" | "text" | "callout" | "region";

  let { id, switcher, onsaved, oncopy, onremove }: { id: number; switcher: Snippet; onsaved: () => void; oncopy: (id: number) => void; onremove: () => void } = $props();

  const TOOLS: { key: Tool; label: string; hint: string; icon: string; hotkey: string }[] = [
    { key: "select", label: "Выбор", icon: "cursor", hotkey: "v", hint: "Выбирать пометки кликом и двигать их и их вершины мышью." },
    { key: "marker", label: "Метка", icon: "pin", hotkey: "m", hint: "Клик по карте ставит метку со значком." },
    { key: "line", label: "Линия", icon: "line", hotkey: "l", hint: "Кликами ставьте вершины, Enter или «Готово» завершает." },
    { key: "arrow", label: "Стрелка", icon: "arrow", hotkey: "a", hint: "Как линия, на конце наконечник." },
    { key: "polygon", label: "Область", icon: "polygon", hotkey: "p", hint: "Кликами ставьте вершины (от трёх), Enter завершает." },
    { key: "circle", label: "Круг", icon: "circle", hotkey: "o", hint: "Клик ставит центр, радиус задаётся справа в километрах." },
    { key: "text", label: "Текст", icon: "text", hotkey: "t", hint: "Клик ставит надпись прямо на карте." },
    { key: "callout", label: "Выноска", icon: "callout", hotkey: "c", hint: "Плашка с текстом, от неё линия к месту клика." },
    { key: "region", label: "Выделение", icon: "region", hotkey: "r", hint: "Клик по провинции выделяет её цветом. Страну целиком можно задать справа кодом." },
  ];

  // стиль карты нужен только для просмотра здесь, в сцене он не хранится
  const LOOK_KEY = "studio.sceneLook";
  let look = $state((() => { try { const v = localStorage.getItem(LOOK_KEY) ?? ""; return v in LOOKS ? v : "dark"; } catch { return "dark"; } })());
  $effect(() => { const v = look; try { localStorage.setItem(LOOK_KEY, v); } catch { /* память браузера закрыта */ } });
  let mapView: { zoomBy(delta: number): void } | undefined = $state();

  // даты, когда менялись границы: по ним шагает дата мира сцены
  let dates = $state<string[]>([]);
  onMount(async () => { dates = (await api.GET("/studio/api/map/territory/dates")).data ?? []; });

  let options = $state<Schemas["MapSceneOptions"] | null>(null);
  let scene = $state<Schemas["MapSceneOut"] | null>(null);
  let form = $state<Form | null>(null);
  let saved = $state("");
  let base = $state<Form | null>(null);                    // сохранённое: им наполняется общий черновик
  let errors = $state<Record<string, string[]>>({});
  let tool = $state<Tool>("select");
  let selected = $state<number | null>(null);
  let draft = $state<Point[]>([]);
  let side = $state<"marks" | "scene" | "history">("marks");
  let revisions = $state<Schemas["MapRevisionRow"][]>([]);
  let view = $state({ lng: 10, lat: 30, zoom: 2 });
  let owners = $state<Record<string, Schemas["MapOwnerOnDate"]>>({});
  let regionCodes = $state<Record<string, string[]>>({});
  let unknownTokens = $state<string[]>([]);
  let map: maplibregl.Map | undefined;
  let markers: maplibregl.Marker[] = [];
  let busy = $state(false);

  const features = $derived((form?.features ?? []) as Feature[]);
  const dirty = $derived(form !== null && JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);      // в совместном режиме черновик на сервере
  const current = $derived(selected !== null ? features[selected] ?? null : null);

  const shownDate = $derived(form?.base_date || dates.at(-1) || "");
  const dateIndex = $derived(Math.max(0, dates.findLastIndex((d) => d <= shownDate)));
  function step(direction: -1 | 1) {
    const to = direction < 0 ? [...dates].reverse().find((d) => d < shownDate) : dates.find((d) => d > shownDate);
    if (to && form) form.base_date = to;
  }
  const viewerUrl = $derived.by(() => {
    const root = window.STUDIO.api.replace(/studio\/api\/?$/, "");
    const query = new URLSearchParams({ scene: form?.slug ?? "", theme: look });
    return `${new URL("apps/map/", new URL(root, location.href)).pathname}?${query}`;
  });

  async function load() {
    const [a, b] = await Promise.all([api.GET("/studio/api/map/scenes/options"), api.GET("/studio/api/map/scenes/{scene_id}", { params: { path: { scene_id: id } } })]);
    options = a.data ?? null;
    if (!b.data) return;
    scene = b.data;
    const { id: _id, updated_at: _u, created_at: _c, ...fields } = b.data;
    form = fields;
    saved = JSON.stringify(form);
    base = JSON.parse(saved);
    selected = null;
    draft = [];
  }
  onMount(load);
  // общий черновик сцены карты (пометки целиком общим значением: побеждает последнее изменение)
  const share = new SharedForm({
    room: () => `map/scenes/${id}`,
    texts: ["title"],
    draft: () => form ?? ({} as Form),
    base: () => base,
    onRemoteSave: async () => {
      const { data } = await api.GET("/studio/api/map/scenes/{scene_id}", { params: { path: { scene_id: id } } });
      if (!data) return;
      scene = data;
      const { id: _id, updated_at: _u, created_at: _c, ...fields } = data;
      saved = JSON.stringify(fields);
      base = JSON.parse(saved);
    },
  });

  async function save() {
    if (!form || !scene) return;
    errors = {};
    busy = true;
    const { data, error } = await api.PUT("/studio/api/map/scenes/{scene_id}", { params: { path: { scene_id: scene.id } }, body: form });
    busy = false;
    if (error || !data) {
      errors = fieldErrors(error);
      const text = Object.values(errors).flat().join(" ");
      return toast(text || problem(error, "Не сохранилось."), "error");
    }
    share.markSaved();
    toast("Сцена сохранена.");
    const keep = selected;
    await load();
    selected = keep !== null && keep < (form?.features.length ?? 0) ? keep : null;
    onsaved();
    if (side === "history") loadRevisions();
  }

  async function loadRevisions() {
    revisions = (await api.GET("/studio/api/map/scenes/{scene_id}/revisions", { params: { path: { scene_id: id } } })).data ?? [];
  }
  $effect(() => { if (side === "history") loadRevisions(); });

  async function restore(row: Schemas["MapRevisionRow"]) {
    if (!(await ask("Восстановить снимок?", `Сцена станет такой, какой была ${showDate(row.saved_at.slice(0, 10))}. Текущее состояние останется в истории.`, "Восстановить"))) return;
    const { error } = await api.POST("/studio/api/map/scenes/{scene_id}/revisions/{revision_id}/restore", { params: { path: { scene_id: id, revision_id: row.id } } });
    if (error) return toast(problem(error), "error");
    toast("Снимок восстановлен.");
    await load();
    loadRevisions();
    onsaved();
  }

  // ---------- содержимое карты ----------
  async function loadOwners() {
    const date = form?.base_date || dates.at(-1);          // пусто: последние границы
    const query = date ? { date } : {};
    owners = (await api.GET("/studio/api/map/territory/owners", { params: { query } })).data ?? {};
  }
  let ownersFor = "";
  $effect(() => {
    const date = form?.base_date || dates.at(-1) || "";
    if (form && date !== ownersFor) { ownersFor = date; loadOwners(); }
  });

  const tokens = $derived([...new Set(features.filter((f) => f.type === "region" && f.token?.trim()).map((f) => f.token!.trim()))]);
  let resolveTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const list = tokens;
    const date = form?.base_date ?? null;
    clearTimeout(resolveTimer);
    resolveTimer = setTimeout(async () => {
      if (!list.length) { regionCodes = {}; unknownTokens = []; return; }
      const { data } = await api.POST("/studio/api/map/scenes/resolve", { body: { tokens: list, date } });
      const found: Record<string, string[]> = {};
      for (const g of data?.groups ?? []) found[g.token] = [...(found[g.token] ?? []), ...g.codes];
      regionCodes = found;
      unknownTokens = data?.unknown ?? [];
    }, 300);
  });

  // фон: владения на дату сцены, приглушённые; поверх них выделения цветом пометки
  const colors = $derived.by(() => {
    const table: Record<string, string> = {};
    for (const [code, own] of Object.entries(owners)) table[code] = own.color + "bb";
    for (const f of features) {
      if (f.type !== "region" || !f.token) continue;
      for (const code of regionCodes[f.token.trim()] ?? []) table[code] = hex(f.color);
    }
    return table;
  });
  const markedCodes = $derived(current?.type === "region" && current.token ? regionCodes[current.token.trim()] ?? [] : []);

  function onready(m: maplibregl.Map) {
    map = m;
    m.addSource("feat", { type: "geojson", data: toGeoJSON([]) });
    m.addSource("draft", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    m.addLayer({ id: "feat-sel", type: "line", source: "feat", filter: ["==", ["get", "i"], -1], paint: { "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.5 } });
    m.addLayer({ id: "feat-fill", type: "fill", source: "feat", filter: ["==", ["get", "fill"], true], paint: { "fill-color": ["get", "color"], "fill-opacity": 0.3 } });
    m.addLayer({ id: "feat-line", type: "line", source: "feat", filter: ["!=", ["get", "dash"], true], paint: { "line-color": ["get", "line"], "line-width": ["get", "width"] } });
    m.addLayer({ id: "feat-dash", type: "line", source: "feat", filter: ["==", ["get", "dash"], true], paint: { "line-color": ["get", "line"], "line-width": ["get", "width"], "line-dasharray": [2, 2] } });
    m.addLayer({ id: "draft-line", type: "line", source: "draft", paint: { "line-color": "#ffd23f", "line-width": 2, "line-dasharray": [2, 2] } });
    m.addLayer({ id: "draft-pts", type: "circle", source: "draft", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 5, "circle-color": "#ffd23f", "circle-stroke-color": "#000", "circle-stroke-width": 1 } });
    m.on("click", (e) => {
      if (tool !== "select") return;
      const hit = m.queryRenderedFeatures([[e.point.x - 4, e.point.y - 4], [e.point.x + 4, e.point.y + 4]], { layers: ["feat-fill", "feat-line", "feat-dash"] })[0];
      selected = hit ? Number(hit.properties?.i) : null;
      if (selected !== null) side = "marks";
    });
    m.on("mousemove", (e) => { if (tool === "line" || tool === "arrow" || tool === "polygon") cursor = [e.lngLat.lng, e.lngLat.lat]; });
    redraw();
    if (form) fly();
  }

  let cursor: Point | null = null;

  function redraw() {
    if (!map || !map.getSource("feat")) return;
    (map.getSource("feat") as maplibregl.GeoJSONSource).setData(toGeoJSON(features));
    map.setFilter("feat-sel", ["==", ["get", "i"], selected ?? -1]);
    const shape: GeoFeature[] = draft.map((p) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: p } }));
    if (draft.length >= 2) shape.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: tool === "polygon" ? [...draft, draft[0]] : draft } });
    (map.getSource("draft") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: shape });
  }

  function clearMarkers() { for (const m of markers) m.remove(); markers = []; }

  function element(css: string, text = ""): HTMLElement {
    const el = document.createElement("div");
    el.className = css;
    if (text) el.textContent = text;
    return el;
  }

  function iconSvg(f: Feature): string {
    const color = hex(f.color);
    const icon = options?.icons.find((i) => i.name === (f.icon ?? "pin"));
    if (!icon || icon.name === "pin") return `<svg viewBox="0 0 24 24" width="26" height="26"><path d="M12 22s-7-7-7-12a7 7 0 0 1 14 0c0 5-7 12-7 12Zm0-9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" fill="${color}" stroke="#000" stroke-width="1"/></svg>`;
    return `<svg viewBox="0 0 24 24" width="26" height="26"><path d="${icon.d}" fill="${icon.closed || icon.solid ? color : "none"}" fill-opacity="${icon.solid ? 1 : 0.3}" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  function move(index: number, at: maplibregl.LngLat, vertex?: number) {
    const f = features[index];
    const spot: Point = [+at.lng.toFixed(5), +at.lat.toFixed(5)];
    if (vertex === undefined) f.coords = spot;
    else (f.coords as Point[])[vertex] = spot;
  }

  function drawMarkers() {
    if (!map) return;
    clearMarkers();
    const put = (el: HTMLElement, at: Point, drag?: (lngLat: maplibregl.LngLat) => void, offset: [number, number] = [0, 0]) => {
      const marker = new maplibregl.Marker({ element: el, draggable: !!drag, offset }).setLngLat(at).addTo(map!);
      if (drag) marker.on("dragend", () => drag(marker.getLngLat()));
      markers.push(marker);
      return marker;
    };
    features.forEach((f, i) => {
      const on = i === selected;
      const select = (event: Event) => { if (tool === "select") { event.stopPropagation(); selected = i; side = "marks"; } };
      if (f.type === "marker") {
        const el = element("m-marker" + (on ? " sel" : ""));
        el.innerHTML = iconSvg(f);
        if (f.label) el.append(element("m-label", f.label));
        el.onclick = select;
        put(el, pointOf(f), (at) => move(i, at), [0, -10]);
      } else if (f.type === "text") {
        const el = element("m-text" + (on ? " sel" : ""), f.text || "Текст");
        el.style.color = hex(f.color, "#fff");
        el.style.fontSize = `${f.size ?? 14}px`;
        el.onclick = select;
        put(el, pointOf(f), (at) => move(i, at));
      } else if (f.type === "callout") {
        const el = element("m-dot" + (on ? " sel" : ""));
        el.style.background = hex(f.color, "#fff");
        const [dx, dy] = f.offset ?? [70, -50];
        el.innerHTML = `<svg class="m-leader" width="1" height="1" style="overflow:visible"><line x1="0" y1="0" x2="${dx}" y2="${dy}" stroke="${hex(f.color, "#fff")}" stroke-width="1.5"/></svg>`;
        const box = element("m-callout", f.text || "Выноска");
        box.style.cssText = `left:${dx}px;top:${dy}px;border-color:${hex(f.color, "#fff")}`;
        el.append(box);
        el.onclick = select;
        put(el, pointOf(f), (at) => move(i, at));
      } else if (f.type === "circle") {
        const el = element("m-dot" + (on ? " sel" : ""));
        el.style.background = hex(f.color);
        el.onclick = select;
        put(el, pointOf(f), (at) => move(i, at));
      } else if (f.type === "arrow" && pathOf(f).length >= 2) {
        const path = pathOf(f);
        const el = element("m-head");
        el.style.borderBottomColor = hex(f.color);
        el.style.transform = `rotate(${bearing(path.at(-2)!, path.at(-1)!)}deg)`;
        el.style.pointerEvents = "none";
        put(el, path.at(-1)!);
      }
      // ручки вершин выбранной линии и области: тянуть, Alt+клик убирает, плюс между вершинами добавляет
      if (on && isPath(f) && !f.smooth) {
        const path = pathOf(f);
        const need = f.type === "polygon" ? 3 : 2;
        path.forEach((p, v) => {
          const h = element("m-vertex");
          h.onclick = (event) => {
            if (!event.altKey) return;
            event.stopPropagation();
            if (path.length > need) path.splice(v, 1); else toast(`Нужно хотя бы ${need} точки.`, "error");
          };
          put(h, p, (at) => move(i, at, v));
          const next = f.type === "polygon" ? path[(v + 1) % path.length] : path[v + 1];
          if (next) {
            const mid = element("m-mid");
            mid.title = "Добавить вершину";
            mid.onclick = (event) => { event.stopPropagation(); path.splice(v + 1, 0, [(p[0] + next[0]) / 2, (p[1] + next[1]) / 2]); };
            put(mid, [(p[0] + next[0]) / 2, (p[1] + next[1]) / 2]);
          }
        });
      }
    });
  }

  // карта следует за данными: любое изменение пометок или выбора перерисовывает слой и метки
  $effect(() => {
    JSON.stringify(features);
    selected; draft; tool; options;
    untrack(() => { redraw(); drawMarkers(); });
  });
  onDestroy(clearMarkers);

  function fly() {
    if (!map || !form) return;
    map.jumpTo({ center: [form.lon, form.lat], zoom: form.zoom });
  }

  // ---------- рисование ----------
  function add(f: Feature) {
    form!.features.push(f as never);
    selected = form!.features.length - 1;
    side = "marks";
  }

  async function onpick(code: string | null, at: { lng: number; lat: number; shift: boolean; alt: boolean }) {
    if (!form || tool === "select") return;
    const point: Point = [+at.lng.toFixed(5), +at.lat.toFixed(5)];
    if (tool === "marker") { add({ type: "marker", coords: point, color: "red" }); tool = "select"; }
    else if (tool === "text") { add({ type: "text", coords: point, text: "Текст", color: "yellow" }); tool = "select"; }
    else if (tool === "callout") { add({ type: "callout", coords: point, text: "Выноска", offset: [70, -50], color: "yellow" }); tool = "select"; }
    else if (tool === "circle") { add({ type: "circle", coords: point, radius_km: 100, color: "red", fill: true }); tool = "select"; }
    else if (tool === "line" || tool === "arrow" || tool === "polygon") draft = [...draft, point];
    else if (tool === "region") {
      if (!code) return;
      const { data } = await api.GET("/studio/api/map/provinces/by-code/{source_code}", { params: { path: { source_code: code } } });
      if (!data) return toast("Для этой провинции нет записи в базе.", "error");
      if (features.some((f) => f.type === "region" && f.token === data.code)) return toast(`${data.code} уже выделена.`, "error");
      add({ type: "region", token: data.code, color: "red", fill: true });
    }
  }

  function finish() {
    const need = tool === "polygon" ? 3 : 2;
    if (draft.length < need) return toast(`Нужно хотя бы ${need} точки.`, "error");
    add(tool === "polygon" ? { type: "polygon", coords: draft, color: "red", fill: true } : { type: tool, coords: draft, color: "red", width: 3 });
    draft = [];
    tool = "select";
  }
  function cancel() { draft = []; if (tool !== "select") tool = "select"; else selected = null; }

  function key(event: KeyboardEvent) {
    const target = event.target as HTMLElement;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable) return;
    if (!event.ctrlKey && !event.metaKey && !event.altKey) {
      const found = TOOLS.find((item) => item.hotkey === event.key.toLowerCase());
      if (found) { tool = found.key; draft = []; return; }
    }
    if (event.key === "Enter" && draft.length) { event.preventDefault(); finish(); }
    else if (event.key === "Escape") cancel();
    else if (event.key === "Backspace" && draft.length) { event.preventDefault(); draft = draft.slice(0, -1); }
    else if (event.key === "Delete" && selected !== null) remove(selected);
    else if ((event.ctrlKey || event.metaKey) && event.key === "s") { event.preventDefault(); if (dirty) save(); }
  }
  function remove(index: number) {
    form!.features.splice(index, 1);
    selected = null;
  }
  function duplicate(index: number) {
    const copy = JSON.parse(JSON.stringify(form!.features[index])) as Feature;
    if (copy.coords && isPoint(copy)) copy.coords = [pointOf(copy)[0] + 0.5, pointOf(copy)[1] - 0.5];
    else if (copy.coords && isPath(copy)) copy.coords = pathOf(copy).map(([x, y]) => [x + 0.5, y - 0.5] as Point);
    add(copy);
  }
  function swap(index: number, by: -1 | 1) {
    const list = form!.features;
    const to = index + by;
    if (to < 0 || to >= list.length) return;
    [list[index], list[to]] = [list[to], list[index]];
    selected = to;
  }

  function takeView() {
    if (!form || !map) return;
    form.lon = +view.lng.toFixed(3);
    form.lat = +view.lat.toFixed(3);
    form.zoom = +view.zoom.toFixed(2);
  }
  function takeBounds() {
    if (!form || !map) return;
    const b = map.getBounds();
    form.bounds = [+b.getWest().toFixed(2), +b.getSouth().toFixed(2), +b.getEast().toFixed(2), +b.getNorth().toFixed(2)];
  }

  const drawing = $derived(tool === "line" || tool === "arrow" || tool === "polygon");
  const regionUnknown = $derived(current?.type === "region" && !!current.token && unknownTokens.includes(current.token.trim()));
</script>

<svelte:window onkeydown={key} />

{#if form && scene && options}
  <div class="terr">
    <div class="mapbox">
      <MapView bind:this={mapView} {colors} selected={markedCodes} flat={form.flat} center={[form.lon, form.lat]} zoom={form.zoom} look={look} view={form.mode as MapViewKind}
               {onpick} {onready} oncamera={(v) => (view = v)} />
    </div>

    <div class="overlay">
      <section class="panel top" aria-label="Сцена, дата и вид карты">
        <div class="row head">
          {@render switcher()}
          <input class="title" bind:value={form.title} class:bad={errors.title} aria-label="Название сцены" />
          <code class="muted slug">{form.slug}</code>
          <span class="grow"></span>
          <DraftState {share} {dirty} saved="" />
          <button class="btn primary" disabled={!dirty || busy} onclick={save} title="Сохранить сцену (Ctrl+S)">{busy ? "Сохраняю…" : "Сохранить"}</button>
        </div>
        <div class="row">
          <div class="when">
            <button class="icon" onclick={() => step(-1)} disabled={!dates.some((d) => d < shownDate)} aria-label="Предыдущее изменение границ" title="Предыдущее изменение границ"><Icon name="chevron" size={16} /></button>
            <input class="field date" type="date" bind:value={form.base_date} aria-label="Дата мира" />
            <button class="icon next" onclick={() => step(1)} disabled={!dates.some((d) => d > shownDate)} aria-label="Следующее изменение границ" title="Следующее изменение границ"><Icon name="chevron" size={16} /></button>
            <button class="ghost" class:on={!form.base_date} aria-pressed={!form.base_date} onclick={() => (form!.base_date = null)} title="Показывать самые свежие границы, без привязки к дате">Последние границы</button>
          </div>
          <div class="line">
            <input type="range" min="0" max={Math.max(0, dates.length - 1)} step="1" value={dateIndex} disabled={dates.length < 2} oninput={(e) => (form!.base_date = dates[+e.currentTarget.value] ?? null)}
                   aria-label="Изменения границ по порядку" />
            <span class="muted small count">{#if form.base_date && dates.length}{dateIndex + 1} из {dates.length}{/if}</span>
          </div>
          <Hint text="Какие владения показывать под пометками. Пусто: самые свежие. Игрок видит сцену на эту дату, пока в ссылке не указана другая." />
        </div>
        <div class="row looks">
          <div class="seg" role="radiogroup" aria-label="Стиль карты">
            <span class="seglabel" title="Стиль карты"><Icon name="layers" size={14} /></span>
            {#each Object.entries(LOOKS) as [key, item] (key)}
              <button role="radio" aria-checked={look === key} class:on={look === key} title="{item.hint}. Только для просмотра здесь: в сцене стиль не хранится, игрок видит свой." onclick={() => (look = key)}>{item.label}</button>
            {/each}
          </div>
          <div class="seg" role="radiogroup" aria-label="Режим карты">
            {#each VIEWS as item (item.key)}
              <button role="radio" aria-checked={form.mode === item.key} class:on={form.mode === item.key} title={item.hint} onclick={() => (form!.mode = item.key)}>{item.label}</button>
            {/each}
          </div>
          <div class="seg" role="radiogroup" aria-label="Проекция">
            <button role="radio" aria-checked={!form.flat} class:on={!form.flat} onclick={() => (form!.flat = false)}>Глобус</button>
            <button role="radio" aria-checked={form.flat} class:on={form.flat} onclick={() => (form!.flat = true)}>Плоская</button>
          </div>
          <a class="ghost view" href={viewerUrl} target="_blank" rel="noopener" title={dirty ? "Откроется сохранённая версия: сохраните правки" : "Открыть сцену в приложении игры"}><Icon name="play" size={14} />Посмотреть</a>
        </div>
      </section>

      <div class="tools panel" role="radiogroup" aria-label="Инструмент">
        {#each TOOLS as t (t.key)}
          <button class="tool" class:on={tool === t.key} role="radio" aria-checked={tool === t.key} title="{t.label} ({t.hotkey.toUpperCase()}): {t.hint}" onclick={() => { tool = t.key; draft = []; }}>
            <Icon name={t.icon} size={18} /><kbd>{t.hotkey.toUpperCase()}</kbd>
          </button>
        {/each}
      </div>

      <aside class="side">
        <section class="panel dock" aria-label="Пометки, сцена, история">
          <div class="tabs" role="tablist">
            <button role="tab" aria-selected={side === "marks"} class:on={side === "marks"} onclick={() => (side = "marks")}>Пометки<span class="n">{features.length}</span></button>
            <button role="tab" aria-selected={side === "scene"} class:on={side === "scene"} onclick={() => (side = "scene")}>Сцена</button>
            <button role="tab" aria-selected={side === "history"} class:on={side === "history"} onclick={() => (side = "history")}>История</button>
          </div>

          {#if side === "marks"}
            {#if !features.length}<p class="muted small pad">Пометок нет. Выберите инструмент слева и кликните по карте.</p>{/if}
            <ul class="marks">
              {#each features as f, i (i)}
                <li class:on={i === selected}>
                  <button class="mark" onclick={() => { selected = i; tool = "select"; }}>
                    <i style="background:{hex(f.color)}"></i><span class="kind">{TYPE_LABEL[f.type]}</span><span class="name">{title(f)}</span>
                  </button>
                  {#if i === selected}
                    <button class="icon sm" onclick={() => swap(i, -1)} disabled={i === 0} aria-label="Выше" title="Выше"><Icon name="chevron" size={14} /></button>
                    <button class="icon sm next" onclick={() => swap(i, 1)} disabled={i === features.length - 1} aria-label="Ниже" title="Ниже"><Icon name="chevron" size={14} /></button>
                  {/if}
                </li>
              {/each}
            </ul>
            {#if errors.features}<p class="err">{errors.features.join(" ")}</p>{/if}
          {:else if side === "scene"}
            <div class="form">
              <label><span class="label">Слаг<Hint text="По нему сцену подключают в вики и ссылках: ::map scene=слаг. Латиница, цифры и дефис." /></span>
                <input class="field mono" class:bad={errors.slug} bind:value={form.slug} />{#if errors.slug}<span class="err">{errors.slug.join(" ")}</span>{/if}</label>

              <h4>Камера</h4>
              <div class="three">
                <label><span class="label">Долгота</span><input class="field" type="number" step="0.01" bind:value={form.lon} /></label>
                <label><span class="label">Широта</span><input class="field" type="number" step="0.01" bind:value={form.lat} /></label>
                <label><span class="label">Зум</span><input class="field" type="number" step="0.1" bind:value={form.zoom} /></label>
              </div>
              <div class="row"><button class="btn" onclick={takeView}>Взять из карты</button><button class="btn ghost" onclick={fly}>Показать</button></div>
              {#each ["lon", "lat", "zoom"] as name (name)}{#if errors[name]}<span class="err">{errors[name].join(" ")}</span>{/if}{/each}

              <h4>Пределы<Hint text="За эти пределы игрок не уведёт камеру." /></h4>
              <div class="two">
                <label><span class="label">Мин. зум</span><input class="field" type="number" step="0.1" bind:value={form.min_zoom} /></label>
                <label><span class="label">Макс. зум</span><input class="field" type="number" step="0.1" bind:value={form.max_zoom} /></label>
              </div>
              <p class="small mono">{form.bounds ? `границы: ${form.bounds.join(", ")}` : "границы не заданы"}</p>
              <div class="row"><button class="btn" onclick={takeBounds}>Границы по виду карты</button>{#if form.bounds}<button class="btn ghost" onclick={() => (form!.bounds = null)}>Снять</button>{/if}</div>
              {#if errors.bounds || errors.max_zoom}<span class="err">{[...(errors.bounds ?? []), ...(errors.max_zoom ?? [])].join(" ")}</span>{/if}

              <h4>Кто видит сцену<Hint text="Условие по ключам: пока оно не выполнено, сцена игроку недоступна. Пусто: всем." /></h4>
              <AccessBuilder bind:value={form.keys} bad={!!errors.keys} />
              {#if errors.keys}<span class="err">{errors.keys.join(" ")}</span>{/if}

              <h4>Действия</h4>
              <div class="row">
                <button class="btn" onclick={() => oncopy(scene!.id)}><Icon name="copy" size={14} />Сделать копию</button>
                <button class="btn ghost danger" onclick={onremove}><Icon name="trash" size={14} />Удалить сцену</button>
              </div>
            </div>
          {:else}
            <p class="muted small">Каждое сохранение оставляет снимок (последние 50). Восстановление само записывается новым снимком.</p>
            <ul class="revs">
              {#each revisions as r, n (r.id)}
                <li>
                  <div><b>{showDate(r.saved_at.slice(0, 10))}</b> <span class="muted">{r.saved_at.slice(11, 16)}</span>{#if r.saved_by} <span class="muted">· {r.saved_by}</span>{/if}
                    <div class="muted small">{r.title}, пометок: {r.features}{n === 0 ? " · последний" : ""}</div></div>
                  {#if n > 0}<button class="btn" onclick={() => restore(r)}>Восстановить</button>{/if}
                </li>
              {:else}
                <li class="muted small">Снимков нет.</li>
              {/each}
            </ul>
          {/if}
        </section>

        {#if current && selected !== null && side === "marks"}
          <section class="panel card">
            <h3>Свойства<span class="spacer"></span>
              <button class="x" onclick={() => (selected = null)} aria-label="Снять выбор" title="Снять выбор (Esc)"><Icon name="close" size={14} /></button></h3>
            <div class="scroll">
              <FeatureForm bind:f={() => features[selected!], (v) => (form!.features[selected!] = v)} {options} unknown={regionUnknown} onduplicate={() => duplicate(selected!)} onremove={() => remove(selected!)} />
            </div>
          </section>
        {/if}
      </aside>

      <div class="foot">
        <div class="tag" aria-live="polite">
          {#if drawing && draft.length}
            <span>точек: <b>{draft.length}</b></span>
            <button class="btn" onclick={() => (draft = draft.slice(0, -1))}>Убрать точку</button>
            <button class="btn primary" onclick={finish}>Готово</button>
          {:else}
            <span class="muted">{TOOLS.find((t) => t.key === tool)?.hint}</span>
          {/if}
        </div>
        <div class="zoom panel">
          <button class="icon" onclick={() => mapView?.zoomBy(1)} aria-label="Приблизить" title="Приблизить"><Icon name="plus" size={16} /></button>
          <button class="icon" onclick={() => mapView?.zoomBy(-1)} aria-label="Отдалить" title="Отдалить"><Icon name="minus" size={16} /></button>
          <button class="icon" onclick={fly} aria-label="Вернуть вид сцены" title="Вернуть сохранённый кадр сцены"><Icon name="home" size={16} /></button>
          <button class="icon" onclick={takeView} aria-label="Зафиксировать кадр" title="Зафиксировать кадр: текущий вид карты станет камерой сцены"><Icon name="camera" size={16} /></button>
        </div>
      </div>
    </div>
  </div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

<style>
  .terr { position: relative; height: 100%; min-height: 0; overflow: hidden; }
  .mapbox { position: absolute; inset: 0; }
  .overlay { position: absolute; inset: 0; display: grid; grid-template-columns: auto minmax(0, 1fr) 340px; grid-template-rows: auto minmax(0, 1fr) auto; gap: 10px; padding: 12px; pointer-events: none; }
  .overlay > * { pointer-events: auto; }
  .panel { padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius); background: color-mix(in srgb, var(--panel) 95%, transparent); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3); }
  .top { grid-column: 1 / 3; grid-row: 1; display: flex; flex-direction: column; gap: 8px; justify-self: start; width: min(100%, 820px); }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
  .head { flex-wrap: nowrap; gap: 8px; }
  .head :global(.draft) { flex: none; font-size: 12.5px; }
  .grow { flex: 1; }
  .slug { flex: none; }
  .title { flex: 0 1 280px; min-width: 120px; background: transparent; border: 1px solid transparent; font-size: 16px; font-weight: 650; padding: 2px 6px; border-radius: var(--radius-s); color: var(--text); }
  .title:hover, .title:focus { border-color: var(--line); outline: none; }
  .when { display: flex; align-items: center; gap: 4px; }
  .date { width: 150px; height: 30px; padding: 2px 8px; }
  .icon { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); color: var(--text); cursor: pointer; }
  .icon:hover:not(:disabled) { border-color: var(--line); background: var(--raise); }
  .icon:disabled { opacity: 0.4; cursor: default; }
  .icon.sm { width: 24px; height: 24px; flex: none; }
  .icon :global(svg) { transform: rotate(90deg); }
  .icon.next :global(svg) { transform: rotate(-90deg); }
  .zoom .icon :global(svg) { transform: none; }
  .icon.sm :global(svg) { transform: rotate(180deg); }
  .icon.sm.next :global(svg) { transform: none; }
  .ghost { height: 30px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .ghost:hover:not(:disabled) { color: var(--text); border-color: var(--line); }
  .ghost:disabled { opacity: 0.4; cursor: default; }
  .ghost.on { background: var(--accent-soft); border-color: var(--accent); color: var(--text); }
  .view { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; text-decoration: none; line-height: 28px; }
  .view:hover { text-decoration: none; }
  .line { display: flex; align-items: center; gap: 8px; min-width: 200px; flex: 1; }
  .count { min-width: 44px; white-space: nowrap; }
  .line input[type="range"] { flex: 1; min-width: 120px; accent-color: var(--accent); }
  .looks { padding-top: 8px; border-top: 1px solid var(--line-soft); }
  .seg { display: inline-flex; align-items: center; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 4px 10px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .seglabel { display: inline-flex; align-items: center; gap: 5px; padding: 0 4px 0 10px; color: var(--faint); font-size: 12px; }

  .tools { grid-column: 1; grid-row: 2; align-self: start; display: flex; flex-direction: column; gap: 4px; padding: 6px; }
  .tool { position: relative; display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--muted); cursor: pointer; }
  .tool:hover { background: var(--panel-2); color: var(--text); }
  .tool.on { background: var(--accent-soft); border-color: var(--accent); color: var(--text); }
  .tool kbd { position: absolute; right: 3px; bottom: 1px; font: 600 9px var(--mono); color: var(--faint); }
  .tool:focus-visible, .seg button:focus-visible, .icon:focus-visible, .ghost:focus-visible, .mark:focus-visible, .tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

  .side { grid-column: 3; grid-row: 1 / 4; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
  .dock { flex: 1 1 0; min-height: 200px; display: flex; flex-direction: column; gap: 8px; overflow: auto; }
  .tabs { flex: none; display: flex; gap: 2px; border-bottom: 1px solid var(--line-soft); margin: -4px -4px 0; padding: 0 4px; }
  .tabs button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .n { padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .marks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; overflow: auto; flex: 1 1 0; min-height: 60px; }
  .marks li { display: flex; align-items: center; gap: 4px; border-radius: var(--radius-s); padding-right: 4px; }
  .marks li.on { background: var(--accent-soft); }
  .mark { flex: 1; display: flex; align-items: center; gap: 8px; padding: 5px 8px; border: 0; background: transparent; color: var(--text); font: inherit; text-align: left; cursor: pointer; min-width: 0; }
  .mark:hover { background: var(--panel-2); }
  .mark i { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .kind { color: var(--muted); font-size: 12px; flex: none; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pad { padding: 8px; }
  .form { display: flex; flex-direction: column; gap: 10px; }
  h4 { margin: 8px 0 0; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
  .revs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .revs li { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }

  .card { flex: none; max-height: 52%; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
  .card h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 14px; font-weight: 650; flex: none; }
  .scroll { overflow: auto; min-height: 0; }
  .spacer { flex: 1; }
  .x { display: grid; place-items: center; width: 22px; height: 22px; padding: 0; border: 0; border-radius: 6px; background: none; color: var(--muted); cursor: pointer; }
  .x:hover { background: var(--panel-2); color: var(--text); }

  .foot { grid-column: 1 / 3; grid-row: 3; display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; pointer-events: none; }
  .foot > * { pointer-events: auto; }
  .tag { display: flex; gap: 10px; align-items: center; padding: 6px 10px; border-radius: var(--radius-s); background: rgba(14, 15, 18, 0.86); border: 1px solid var(--line); max-width: 70%; font-size: 12.5px; }
  .zoom { display: flex; flex-direction: column; gap: 4px; padding: 4px; }
  .small { font-size: 12px; margin: 0; }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
  .bad { border-color: var(--danger); }
  .mono { font-family: var(--mono); font-size: 12px; }
  code { font-size: 11.5px; }

  :global(.m-marker) { display: flex; flex-direction: column; align-items: center; cursor: pointer; }
  :global(.m-marker.sel svg) { filter: drop-shadow(0 0 4px #fff); }
  :global(.m-label), :global(.m-text) { font: 600 12px var(--font); text-shadow: 0 0 3px #000, 0 0 3px #000; white-space: nowrap; cursor: pointer; color: #fff; }
  :global(.m-text.sel) { outline: 1px dashed #fff; outline-offset: 2px; }
  :global(.m-dot) { width: 12px; height: 12px; border-radius: 50%; border: 2px solid #000; cursor: pointer; position: relative; }
  :global(.m-dot.sel) { box-shadow: 0 0 0 3px #fff; }
  :global(.m-leader) { position: absolute; left: 6px; top: 6px; pointer-events: none; }
  :global(.m-callout) { position: absolute; transform: translate(0, -50%); max-width: 200px; padding: 4px 8px; background: rgba(10, 23, 34, 0.94); color: #fff; border: 1.5px solid; border-radius: 4px; font: 12px var(--font); white-space: pre-wrap; }
  :global(.m-vertex) { width: 12px; height: 12px; border-radius: 50%; background: #fff; border: 2px solid var(--accent); cursor: move; }
  :global(.m-mid) { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); opacity: 0.7; cursor: copy; }
  :global(.m-head) { width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent; border-bottom: 16px solid; }
  @media (max-width: 1000px) { .overlay { grid-template-columns: auto minmax(0, 1fr) 290px; } }
</style>
