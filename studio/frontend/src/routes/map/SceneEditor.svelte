<script lang="ts">
  // Редактор одной сцены: карта с инструментами рисования, список пометок со свойствами, настройки камеры и история снимков.
  // Точечные пометки (метка, текст, выноска) и ручки вершин рисуются HTML-метками, линии, площади и круги слоем карты.
  import maplibregl from "maplibre-gl";
  import type { Feature as GeoFeature } from "geojson";
  import { onDestroy, onMount, untrack } from "svelte";
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import Hint from "../../lib/Hint.svelte";
  import MapView from "../../lib/MapView.svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { ask } from "../../lib/confirm.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { bearing, hex, isPath, isPoint, pathOf, pointOf, title, toGeoJSON, TYPE_LABEL, type Feature, type Point } from "../../lib/sceneGeo";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, showDate } from "./shared";
  import FeatureForm from "./FeatureForm.svelte";

  type Form = Schemas["MapSceneIn"];
  type Tool = "select" | "marker" | "line" | "arrow" | "polygon" | "circle" | "text" | "callout" | "region";

  let { id, onsaved, oncopy, onremove }: { id: number; onsaved: () => void; oncopy: (id: number) => void; onremove: () => void } = $props();

  const TOOLS: { key: Tool; label: string; hint: string }[] = [
    { key: "select", label: "Выбор", hint: "Выбирать пометки кликом и двигать их и их вершины мышью." },
    { key: "marker", label: "Метка", hint: "Клик по карте ставит метку со значком." },
    { key: "line", label: "Линия", hint: "Кликами ставьте вершины, Enter или «Готово» завершает." },
    { key: "arrow", label: "Стрелка", hint: "Как линия, на конце наконечник." },
    { key: "polygon", label: "Область", hint: "Кликами ставьте вершины (от трёх), Enter завершает." },
    { key: "circle", label: "Круг", hint: "Клик ставит центр, радиус задаётся справа в километрах." },
    { key: "text", label: "Текст", hint: "Клик ставит надпись прямо на карте." },
    { key: "callout", label: "Выноска", hint: "Плашка с текстом, от неё линия к месту клика." },
    { key: "region", label: "Выделение", hint: "Клик по провинции выделяет её цветом. Страну целиком можно задать справа кодом." },
  ];

  let options = $state<Schemas["MapSceneOptions"] | null>(null);
  let scene = $state<Schemas["MapSceneOut"] | null>(null);
  let form = $state<Form | null>(null);
  let saved = $state("");
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
  guardUnsaved(() => saved !== "" && dirty);
  const current = $derived(selected !== null ? features[selected] ?? null : null);

  async function load() {
    const [a, b] = await Promise.all([api.GET("/studio/api/map/scenes/options"), api.GET("/studio/api/map/scenes/{scene_id}", { params: { path: { scene_id: id } } })]);
    options = a.data ?? null;
    if (!b.data) return;
    scene = b.data;
    const { id: _id, updated_at: _u, created_at: _c, ...fields } = b.data;
    form = fields;
    saved = JSON.stringify(form);
    selected = null;
    draft = [];
  }
  onMount(load);

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
    const query = form?.base_date ? { date: form.base_date } : {};
    owners = (await api.GET("/studio/api/map/territory/owners", { params: { query } })).data ?? {};
  }
  let ownersFor = "";
  $effect(() => {
    const date = form?.base_date ?? "";
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
  <div class="editor">
    <div class="mapcol">
      <div class="toolbar">
        <div class="tools" role="radiogroup" aria-label="Инструмент">
          {#each TOOLS as t (t.key)}
            <button class="tool" class:on={tool === t.key} role="radio" aria-checked={tool === t.key} title={t.hint} onclick={() => { tool = t.key; draft = []; }}>{t.label}</button>
          {/each}
        </div>
        <span class="spacer"></span>
        {#if drawing && draft.length}
          <span class="muted small">точек: {draft.length}</span>
          <button class="btn" onclick={() => (draft = draft.slice(0, -1))}>Убрать точку</button>
          <button class="btn primary" onclick={finish}>Готово</button>
        {/if}
      </div>
      <div class="mapbox">
        <MapView {colors} selected={markedCodes} flat={form.flat} center={[form.lon, form.lat]} zoom={form.zoom} {onpick} {onready} oncamera={(v) => (view = v)} />
        <p class="tip">{TOOLS.find((t) => t.key === tool)?.hint}</p>
      </div>
    </div>

    <aside class="side">
      <header class="top">
        <div class="names">
          <input class="title" bind:value={form.title} class:bad={errors.title} aria-label="Название" />
          <code class="muted">{form.slug}</code>
        </div>
        <button class="btn primary" disabled={!dirty || busy} onclick={save}>Сохранить</button>
      </header>
      <div class="tabs" role="tablist">
        <button role="tab" aria-selected={side === "marks"} class:on={side === "marks"} onclick={() => (side = "marks")}>Пометки <span class="chip">{features.length}</span></button>
        <button role="tab" aria-selected={side === "scene"} class:on={side === "scene"} onclick={() => (side = "scene")}>Сцена</button>
        <button role="tab" aria-selected={side === "history"} class:on={side === "history"} onclick={() => (side = "history")}>История</button>
      </div>

      <div class="panel">
        {#if side === "marks"}
          {#if !features.length}<p class="muted small">Пометок нет. Выберите инструмент над картой и кликните по ней.</p>{/if}
          <ul class="marks">
            {#each features as f, i (i)}
              <li class:on={i === selected}>
                <button class="mark" onclick={() => { selected = i; tool = "select"; }}>
                  <i style="background:{hex(f.color)}"></i><span class="kind">{TYPE_LABEL[f.type]}</span><span class="name">{title(f)}</span>
                </button>
                {#if i === selected}
                  <button class="btn ghost" onclick={() => swap(i, -1)} disabled={i === 0} aria-label="Выше">↑</button>
                  <button class="btn ghost" onclick={() => swap(i, 1)} disabled={i === features.length - 1} aria-label="Ниже">↓</button>
                {/if}
              </li>
            {/each}
          </ul>
          {#if current && selected !== null}
            <FeatureForm bind:f={() => features[selected!], (v) => (form!.features[selected!] = v)} {options} unknown={regionUnknown} onduplicate={() => duplicate(selected!)} onremove={() => remove(selected!)} />
          {/if}
          {#if errors.features}<p class="err">{errors.features.join(" ")}</p>{/if}
        {:else if side === "scene"}
          <div class="form">
            <label><span class="label">Название</span><input class="field" bind:value={form.title} /></label>
            <label><span class="label">Слаг<Hint text="По нему сцену подключают в вики и ссылках: ::map scene=слаг. Латиница, цифры и дефис." /></span>
              <input class="field mono" class:bad={errors.slug} bind:value={form.slug} />{#if errors.slug}<span class="err">{errors.slug.join(" ")}</span>{/if}</label>
            <label><span class="label">Дата мира<Hint text="Какие владения показывать: на эту дату. Пусто: самые свежие." /></span>
              <input class="field" type="date" bind:value={form.base_date} /></label>
            <label><span class="label">Режим карты</span>
              <select class="field" bind:value={form.mode}>{#each options.modes as [value, label] (value)}<option {value}>{label}</option>{/each}</select></label>
            <label class="check"><input type="checkbox" bind:checked={form.flat} /> плоская карта (без глобуса)</label>

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
              <button class="btn" onclick={() => oncopy(scene!.id)}>Сделать копию</button>
              <button class="btn ghost danger" onclick={onremove}>Удалить сцену</button>
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
      </div>
    </aside>
  </div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

<style>
  .editor { display: grid; grid-template-columns: 1fr 360px; height: 100%; min-height: 0; }
  .mapcol { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--line-soft); flex-wrap: wrap; }
  .tools { display: flex; gap: 4px; flex-wrap: wrap; }
  .tool { height: 28px; padding: 0 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); cursor: pointer; }
  .tool:hover { background: var(--raise); }
  .tool.on { background: var(--accent-soft); border-color: var(--accent); }
  .spacer { flex: 1; }
  .mapbox { position: relative; flex: 1; min-height: 0; }
  .tip { position: absolute; left: 12px; bottom: 12px; margin: 0; padding: 5px 10px; border-radius: var(--radius-s); background: rgba(14, 15, 18, 0.86); border: 1px solid var(--line); pointer-events: none; font-size: 12px; max-width: 70%; }
  .side { display: flex; flex-direction: column; border-left: 1px solid var(--line-soft); min-height: 0; }
  .top { display: flex; align-items: center; gap: 8px; padding: 10px 12px; }
  .names { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  .title { background: transparent; border: 1px solid transparent; font-size: 16px; font-weight: 650; padding: 2px 4px; border-radius: var(--radius-s); width: 100%; }
  .title:hover, .title:focus { border-color: var(--line); outline: none; }
  .tabs { display: flex; gap: 2px; padding: 0 10px; border-bottom: 1px solid var(--line-soft); }
  .tabs button { background: transparent; border: 0; border-bottom: 2px solid transparent; padding: 8px 10px; color: var(--muted); cursor: pointer; }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .panel { flex: 1; overflow: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
  .marks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 260px; overflow: auto; }
  .marks li { display: flex; align-items: center; border-radius: var(--radius-s); }
  .marks li.on { background: var(--accent-soft); }
  .mark { flex: 1; display: flex; align-items: center; gap: 8px; padding: 5px 8px; border: 0; background: transparent; text-align: left; cursor: pointer; min-width: 0; }
  .mark i { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .kind { color: var(--muted); font-size: 12px; flex: none; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .form { display: flex; flex-direction: column; gap: 10px; }
  h4 { margin: 8px 0 0; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
  .row { display: flex; gap: 8px; }
  .check { display: flex; align-items: center; gap: 6px; }
  .revs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .revs li { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
  .bad { border-color: var(--danger); }
  .mono { font-family: var(--mono); font-size: 12px; }
  .pad { padding: 20px; }
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
</style>
