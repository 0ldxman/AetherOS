<script lang="ts">
  // Подписи стран: список слева, карта с подписями справа. Выбранную подпись двигают мышью или кликом по карте.
  import maplibregl from "maplibre-gl";
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import MapView from "../../lib/MapView.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import { RANKS, type Country } from "./shared";

  type Label = Schemas["MapLabelOut"];
  let { id }: { id: number | null } = $props();

  let labels = $state<Label[]>([]);
  let countries = $state<Country[]>([]);
  let q = $state("");
  let draft = $state<Label | null>(null);
  let saved = $state("");
  let view = $state({ lng: 10, lat: 30, zoom: 2 });
  let dialog = $state(false);
  let newCountry = $state(0);
  let view_: MapView;
  let map: maplibregl.Map | undefined;
  let markers = new Map<number, maplibregl.Marker>();

  const pure = (l: Label) => JSON.stringify({ text: l.text, lng: l.lng, lat: l.lat, rank: l.rank });
  const dirty = $derived(draft !== null && pure(draft) !== saved);
  guardUnsaved(() => saved !== "" && dirty);
  const colorOf = $derived(new Map(countries.map((c) => [c.id, c.color])));

  async function list() {
    labels = (await api.GET("/studio/api/map/labels", { params: { query: { q } } })).data ?? [];
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { q; clearTimeout(timer); timer = setTimeout(list, 200); });
  onMount(async () => { countries = (await api.GET("/studio/api/map/countries")).data ?? []; });

  $effect(() => {
    const found = labels.find((l) => l.id === id);
    draft = found ? { ...found } : null;
    saved = found ? pure(found) : "";
  });
  $effect(() => { if (draft && map) view_?.flyTo(draft.lng, draft.lat, Math.max(map.getZoom(), 3)); });

  // подписи на карте: у выбранной маркер тянется мышью
  function paint() {
    if (!map) return;
    for (const marker of markers.values()) marker.remove();
    markers.clear();
    for (const l of labels) {
      const shown = l.id === id && draft ? draft : l;
      const el = document.createElement("button");
      el.className = "lbl" + (l.id === id ? " sel" : "");
      el.textContent = shown.text || shown.country_name;
      el.style.setProperty("--c", colorOf.get(l.country) ?? "#888");
      el.onclick = (event) => { event.stopPropagation(); go(`/map/labels/${l.id}`); };
      const marker = new maplibregl.Marker({ element: el, draggable: l.id === id }).setLngLat([shown.lng, shown.lat]).addTo(map);
      if (l.id === id) marker.on("dragend", () => { const at = marker.getLngLat(); if (draft) { draft.lng = +at.lng.toFixed(3); draft.lat = +at.lat.toFixed(3); } });
      markers.set(l.id, marker);
    }
  }
  $effect(() => { labels; id; colorOf; draft?.text; draft?.rank; paint(); });
  $effect(() => {
    const marker = id !== null ? markers.get(id) : undefined;
    if (marker && draft) marker.setLngLat([draft.lng, draft.lat]);
  });

  function onpick(_code: string | null, at: { lng: number; lat: number }) {
    if (draft) { draft.lng = +at.lng.toFixed(3); draft.lat = +at.lat.toFixed(3); }
  }

  async function save() {
    if (!draft) return;
    const { data, error } = await api.PUT("/studio/api/map/labels/{label_id}", { params: { path: { label_id: draft.id } }, body: { text: draft.text, lng: draft.lng, lat: draft.lat, rank: draft.rank } });
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    toast("Подпись сохранена.");
    await list();
  }
  async function remove() {
    if (!draft) return;
    if (!(await ask("Удалить подпись?", `«${draft.text || draft.country_name}» пропадёт с карты.`))) return;
    const { error } = await api.DELETE("/studio/api/map/labels/{label_id}", { params: { path: { label_id: draft.id } } });
    if (error) return toast(problem(error), "error");
    await list();
    go("/map/labels");
  }
  async function create() {
    const { data, error } = await api.POST("/studio/api/map/countries/{country_id}/labels", { params: { path: { country_id: newCountry } }, body: { text: "", lng: +view.lng.toFixed(3), lat: +view.lat.toFixed(3), rank: 2 } });
    if (error || !data) return toast(problem(error, "Не добавилась."), "error");
    dialog = false;
    await list();
    go(`/map/labels/${data.id}`);
  }
</script>

<div class="screen">
  <aside class="list">
    <input class="field" placeholder="Подпись или страна…" bind:value={q} />
    <div class="items">
      {#each labels as l (l.id)}
        <a class="item" class:on={l.id === id} href="#/map/labels/{l.id}">
          <span class="line"><i style="background:{colorOf.get(l.country) ?? '#888'}"></i><b>{l.text || l.country_name}</b></span>
          <span class="muted small">{l.country_name} · {RANKS.find((r) => r.value === l.rank)?.label.toLowerCase()}</span>
        </a>
      {:else}
        <p class="muted small pad">Подписей нет.</p>
      {/each}
    </div>
    <button class="btn" onclick={() => { newCountry = countries[0]?.id ?? 0; dialog = true; }} disabled={!countries.length}>+ Подпись</button>
  </aside>

  <div class="mapbox">
    <MapView bind:this={view_} {onpick} oncamera={(v) => (view = v)} onready={(m) => { map = m; paint(); }} />
    {#if draft}
      <div class="panel block">
        <h3>{draft.country_name}</h3>
        <label><span class="label">Текст</span><input class="field" placeholder={draft.country_name} bind:value={draft.text} /></label>
        <div class="two">
          <label><span class="label">Долгота</span><input class="field" type="number" step="0.01" bind:value={draft.lng} /></label>
          <label><span class="label">Широта</span><input class="field" type="number" step="0.01" bind:value={draft.lat} /></label>
        </div>
        <label><span class="label">Ранг</span><select class="field" bind:value={draft.rank}>{#each RANKS as r (r.value)}<option value={r.value}>{r.label}</option>{/each}</select></label>
        <p class="muted small">Тяните подпись мышью или кликните по карте, чтобы поставить её в точку.</p>
        <div class="row">
          <button class="btn ghost danger" onclick={remove}>Удалить</button>
          <span class="spacer"></span>
          <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
        </div>
      </div>
    {/if}
  </div>
</div>

{#if dialog}
  <Dialog title="Новая подпись" confirm="Добавить" onsubmit={create} onclose={() => (dialog = false)} disabled={!newCountry}>
    <p class="muted small">Подпись появится в центре текущего вида карты, потом её можно передвинуть.</p>
    <label><span class="label">Страна</span>
      <select class="field" bind:value={newCountry}>{#each countries as c (c.id)}<option value={c.id}>{c.name} ({c.code})</option>{/each}</select></label>
  </Dialog>
{/if}

<style>
  .screen { display: grid; grid-template-columns: 280px 1fr; height: 100%; min-height: 0; }
  .list { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-right: 1px solid var(--line-soft); min-height: 0; }
  .items { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 2px; }
  .item { display: flex; flex-direction: column; padding: 6px 10px; border-radius: var(--radius-s); color: var(--text); }
  .item:hover { background: var(--panel); text-decoration: none; }
  .item.on { background: var(--accent-soft); }
  .line { display: flex; align-items: center; gap: 8px; }
  i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; border: 1px solid rgba(255, 255, 255, 0.2); }
  .mapbox { position: relative; min-height: 0; }
  .panel { position: absolute; top: 12px; right: 12px; width: 270px; background: rgba(21, 23, 28, 0.94); }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .row { display: flex; align-items: center; }
  .spacer { flex: 1; }
  .pad { padding: 10px; }
  :global(.lbl) { padding: 2px 7px; border-radius: 999px; border: 1px solid var(--c); background: rgba(10, 23, 34, 0.85); color: #fff; font: 11px var(--font); cursor: pointer; white-space: nowrap; }
  :global(.lbl.sel) { background: var(--c); color: #0b1020; font-weight: 700; box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.35); cursor: grab; }
</style>
