<script lang="ts">
  // Материал страны или провинции: объект, который игрок откроет из карточки на карте, флаг «Показывать карточку игроку»
  // и свёрнутая внешняя ссылка (запасной вариант, когда материала нет). Объект ищется по названию и слагу.
  import Hint from "../../lib/Hint.svelte";
  import Icon from "../../lib/Icon.svelte";
  import Switch from "../../lib/Switch.svelte";
  import { api, type Schemas } from "../../lib/api";

  type Row = Schemas["LibraryRow"];
  type Info = Schemas["MapMaterial"];

  let { material, info, showInfo, url, scope, error = "", onmaterial, onshow, onurl }: {
    material: number | null | undefined; info: Info | null | undefined; showInfo: boolean; url: string; scope: "country" | "province"; error?: string;
    onmaterial: (id: number | null) => void; onshow: (value: boolean) => void; onurl: (value: string) => void;
  } = $props();

  let query = $state("");
  let found = $state<Row[]>([]);
  let open = $state(false);
  let chosen = $state<Row | null>(null);                  // выбрано только что: сервер ещё не сохранил
  let timer: ReturnType<typeof setTimeout>;

  // что показываем: только что выбранное, иначе сохранённое
  const shown = $derived<{ id: number; slug: string; name: string; format: string; where: string[] } | null>(
    material === null || material === undefined ? null
      : chosen && chosen.id === material ? { id: chosen.id, slug: chosen.slug, name: chosen.name, format: chosen.format, where: chosen.where }
      : info && info.id === material ? { id: info.id, slug: info.slug, name: info.name, format: info.format, where: info.where } : { id: material, slug: "", name: `объект ${material}`, format: "", where: [] },
  );

  $effect(() => {
    const text = query.trim();
    clearTimeout(timer);
    if (!open) return;
    timer = setTimeout(async () => {
      found = (await api.GET("/studio/api/items", { params: { query: { q: text, limit: 12, sort: "name" } } })).data ?? [];
    }, 200);
  });

  function pick(row: Row) {
    chosen = row;
    onmaterial(row.id);
    query = "";
    open = false;
  }
  function clear() {
    chosen = null;
    onmaterial(null);
  }
  const whoOpens = $derived(scope === "country" ? "провинций этой страны, у которых нет своего материала" : "этой провинции");
</script>

<div class="field-block">
  <span class="label">Материал<Hint text="Объект, который игрок откроет кнопкой «Открыть материал» в карточке {whoOpens}. Он открывается через вики игрока: том с объектом должен быть смонтирован на его машине, и ключи должны подходить." /></span>
  {#if shown}
    <div class="chosen">
      <Icon name="items" size={16} />
      <span class="what"><b>{shown.name}</b>{#if shown.slug}<code>{shown.slug}</code>{/if}{#if shown.format}<span class="chip">{shown.format}</span>{/if}</span>
      <a class="small" href="#/items/{shown.id}">Открыть объект</a>
      <button class="x" onclick={clear} aria-label="Убрать материал"><Icon name="close" size={14} /></button>
    </div>
    {#if shown.where.length}
      <p class="muted small">Лежит: {shown.where.join(", ")}. Игрок откроет, если один из этих дисков смонтирован на его машине.</p>
    {:else if shown.slug}
      <p class="warn small">Объект не лежит ни на одном диске: игрок его не откроет.</p>
    {/if}
  {:else}
    <div class="search">
      <label class="find"><Icon name="search" size={14} />
        <input placeholder="Найти объект по названию или слагу" bind:value={query} onfocus={() => (open = true)} aria-label="Поиск объекта" autocomplete="off" /></label>
      {#if open}
        <ul class="results" role="listbox">
          {#each found as row (row.id)}
            <li><button role="option" aria-selected="false" onmousedown={(e) => { e.preventDefault(); pick(row); }}>
              <span class="what"><b>{row.name}</b><code>{row.slug}</code></span>
              <span class="muted small">{row.format} · {row.places ? `мест: ${row.places}` : "нигде не лежит"}</span>
            </button></li>
          {:else}
            <li class="muted small pad">Ничего не нашлось.</li>
          {/each}
        </ul>
      {/if}
    </div>
    <p class="muted small">Не выбран: у карточки не будет кнопки с материалом{url ? ", останется внешняя ссылка" : ""}.</p>
  {/if}
  {#if error}<p class="err">{error}</p>{/if}

  <Switch checked={showInfo} label="Показывать карточку игроку" onchange={onshow} />
  <p class="muted small">{scope === "country" ? "Выключено: в карточке провинции этой страны нет блока страны и её материала." : "Выключено: клик по провинции в приложении карты ничего не откроет."}</p>

  <details class="ext" open={!!url && !shown}>
    <summary>Внешняя ссылка</summary>
    <input class="field" value={url} oninput={(e) => onurl(e.currentTarget.value)} placeholder="https://… или /wiki/…" aria-label="Внешняя ссылка" />
    <p class="muted small">Запасной вариант: открывается, только если материала нет.</p>
  </details>
</div>

<style>
  .field-block { display: flex; flex-direction: column; gap: 8px; }
  .chosen { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .what { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .what b { overflow-wrap: anywhere; }
  code { font-family: var(--mono); font-size: 11.5px; color: var(--muted); }
  .chip { padding: 0 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11.5px; }
  .x { display: grid; place-items: center; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px; background: none; color: var(--muted); cursor: pointer; }
  .x:hover { background: var(--panel-2); color: var(--text); }
  .x:focus-visible { outline: 2px solid var(--accent); }
  .search { position: relative; }
  .find { display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 7px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .results { position: absolute; z-index: 10; left: 0; right: 0; top: calc(100% + 4px); max-height: 280px; overflow: auto; margin: 0; padding: 4px; list-style: none; border: 1px solid var(--line); border-radius: var(--radius); background: var(--raise); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
  .results button { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; width: 100%; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .results button:hover, .results button:focus-visible { background: var(--accent-soft); outline: none; }
  .pad { padding: 8px; }
  .ext summary { cursor: pointer; color: var(--muted); font-size: 13px; }
  .ext summary:hover { color: var(--text); }
  .ext[open] summary { margin-bottom: 6px; }
  .small { font-size: 12px; margin: 0; }
  .warn { color: var(--warn); margin: 0; }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
</style>
