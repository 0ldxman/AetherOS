<script lang="ts">
  // Карта связей (engine/links.py): для каждого ключа и метки — где требуется и где игрок может это получить.
  // Сверху разрывы: требуется, но негде взять; выдаётся, но ни на что не влияет.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import PageHead from "../lib/PageHead.svelte";

  type Link = Schemas["EnLink"];
  let rows = $state<Link[] | null>(null);
  let show = $state<"problems" | "all">("problems");
  let kind = $state("");
  let query = $state("");

  async function load() { rows = (await api.GET("/studio/api/engine/links")).data ?? []; }
  onMount(load);

  const KIND: Record<string, string> = { key: "ключ", flag: "метка игрока", world: "метка мира", counter: "счётчик мира" };
  const LEVEL: Record<string, string> = { error: "разрыв", warning: "внимание", info: "лишнее", ok: "в порядке" };
  const fact = (row: Link) => (row.kind === "key" ? row.name : row.kind === "flag" ? `flag:${row.name}` : `world:${row.name}`);
  const count = (level: string) => (rows ?? []).filter((r) => r.level === level).length;
  const shown = $derived((rows ?? []).filter((r) => (show === "all" || r.level !== "ok") && (!kind || r.kind === kind)
    && (!query.trim() || fact(r).toLowerCase().includes(query.trim().toLowerCase()))));
</script>

<PageHead title="Связи">
  {#snippet sub()}Для каждого ключа и метки: где они требуются (условия) и где игрок может их получить (исходы, правила, спрятанные ключи, сборки, моменты). Разрыв — загадку не пройти.{/snippet}
  <button class="btn" onclick={load}>Обновить</button>
</PageHead>

<div class="page">
  {#if rows}
    <div class="bar">
      <div class="seg" role="group" aria-label="Что показать">
        <button class:on={show === "problems"} onclick={() => (show = "problems")}>С замечаниями</button>
        <button class:on={show === "all"} onclick={() => (show = "all")}>Все</button>
      </div>
      <select class="field" bind:value={kind} aria-label="Вид"><option value="">все виды</option>{#each Object.entries(KIND) as [value, label] (value)}<option {value}>{label}</option>{/each}</select>
      <input class="field" bind:value={query} placeholder="поиск: dock, flag:met…" aria-label="Поиск" />
      <span class="counts">
        <span class="lv error">{count("error")} {LEVEL.error}</span>
        <span class="lv warning">{count("warning")} {LEVEL.warning}</span>
        <span class="lv info">{count("info")} {LEVEL.info}</span>
        <span class="lv ok">{count("ok")} {LEVEL.ok}</span>
      </span>
    </div>

    <div class="list">
      {#each shown as row (row.kind + row.name)}
        <article class="row {row.level}">
          <div class="head">
            <span class="lv {row.level}">{LEVEL[row.level]}</span>
            <b class="mono">{fact(row)}</b><span class="muted small">{KIND[row.kind]}</span>
            {#if row.problem}<span class="problem">{row.problem}</span>{/if}
          </div>
          <div class="cols">
            <div><span class="label">Требуется</span>
              {#each row.required as p, i (i)}<a class="place" href={p.href || undefined}><span class="muted">{p.what}</span> {p.label}</a>{:else}<span class="muted small">нигде</span>{/each}</div>
            <div><span class="label">Где взять</span>
              {#each row.granted as p, i (i)}<a class="place" href={p.href || undefined}><span class="muted">{p.what}</span> {p.label}</a>{/each}
              {#each row.manual as p, i (i)}<a class="place" href={p.href || undefined}><span class="muted">{p.what}</span> {p.label}</a>{/each}
              {#if !row.granted.length && !row.manual.length}<span class="muted small">негде</span>{/if}</div>
          </div>
        </article>
      {:else}
        <p class="muted">{show === "problems" ? "Замечаний нет: всё, что требуется, где-то выдаётся." : "Ничего не найдено."}</p>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { margin: 12px 32px; max-width: 1100px; display: flex; flex-direction: column; gap: 12px; }
  .bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .bar .field { width: auto; }
  .seg { display: inline-flex; border: 1px solid var(--line-soft); border-radius: var(--radius-s); overflow: hidden; }
  .seg button { padding: 5px 10px; border: 0; background: none; color: var(--muted); font: inherit; cursor: pointer; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .counts { display: flex; gap: 6px; margin-left: auto; }
  .lv { padding: 1px 7px; border-radius: 999px; font-size: 11.5px; white-space: nowrap; background: var(--panel); color: var(--muted); }
  .lv.error { background: color-mix(in srgb, var(--danger) 18%, transparent); color: var(--danger); }
  .lv.warning { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }
  .lv.info { background: var(--accent-soft); color: var(--text); }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .row { padding: 10px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 8px; }
  .row.error { border-left: 3px solid var(--danger); }
  .row.warning { border-left: 3px solid var(--warn); }
  .head { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
  .problem { font-size: 13px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .cols > div { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .place { font-size: 13px; color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
  .place[href]:hover { color: var(--accent); }
  .small { font-size: 12px; }
</style>
