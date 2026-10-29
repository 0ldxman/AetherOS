<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  let { item, dirty, onrestore }: { item: Schemas["ItemOut"]; dirty: boolean; onrestore: () => void } = $props();

  let rows = $state<Schemas["Revision"][]>([]);
  let chosen = $state<Schemas["RevisionOut"] | null>(null);

  const path = $derived({ item_id: item.id });

  async function list() {
    rows = (await api.GET("/studio/api/items/{item_id}/revisions", { params: { path } })).data ?? [];
    if (rows.length > 1 && !chosen) open(rows[1].id);
  }
  onMount(list);

  async function open(revision: number) {
    chosen = (await api.GET("/studio/api/items/{item_id}/revisions/{revision_id}", { params: { path: { ...path, revision_id: revision } } })).data ?? null;
  }

  async function restore() {
    if (!chosen) return;
    const { error } = await api.POST("/studio/api/items/{item_id}/revisions/{revision_id}/restore", { params: { path: { ...path, revision_id: chosen.id } } });
    if (error) return toast(problem(error), "error");
    toast(`Версия от ${when(chosen.saved_at)} восстановлена.`);
    chosen = null;
    onrestore();
    list();
  }

  type Diff = [string, string][];
  const LABEL: Record<string, string> = { name: "Название", format: "Формат", body: "Текст", meta: "Врезка" };
</script>

<div class="split">
  <aside class="list">
    {#each rows as row, i (row.id)}
      <button class="rev" class:on={chosen?.id === row.id} onclick={() => open(row.id)}>
        <b>{when(row.saved_at)}</b>
        <span class="muted small">{row.saved_by ?? "—"}{i === 0 ? " · текущая" : ""}</span>
      </button>
    {:else}
      <p class="muted pad">Версий нет: у объекта без текста история не ведётся.</p>
    {/each}
  </aside>

  <section class="diff">
    {#if chosen}
      <header class="top">
        <span>Версия от <b>{when(chosen.saved_at)}</b>{chosen.saved_by ? ` · ${chosen.saved_by}` : ""} — чем отличается от текущей</span>
        <button class="btn primary" disabled={dirty || !Object.keys(chosen.changes).length} onclick={restore}
                title={dirty ? "Сначала сохраните или отмените свою правку" : ""}>Восстановить эту версию</button>
      </header>
      {#each Object.entries(chosen.changes) as [field, change]}
        <h3>{LABEL[field] ?? field}</h3>
        {#if field === "name" || field === "format"}
          <p class="mono"><span class="del">{(change as string[])[0] || "—"}</span> → <span class="add">{(change as string[])[1] || "—"}</span></p>
        {:else}
          <pre class="lines">{#each change as Diff as [kind, line]}<span class={kind}>{kind === "add" ? "+ " : kind === "del" ? "- " : kind === "hunk" ? "" : "  "}{line}
</span>{/each}</pre>
        {/if}
      {:else}
        <p class="muted">Совпадает с текущей.</p>
      {/each}
    {:else}
      <p class="muted pad">Выберите версию слева.</p>
    {/if}
  </section>
</div>

<style>
  .split { display: grid; grid-template-columns: 240px 1fr; min-height: 0; flex: 1; }
  .list { display: flex; flex-direction: column; gap: 2px; padding: 12px 8px; border-right: 1px solid var(--line-soft); overflow: auto; }
  .rev { display: flex; flex-direction: column; align-items: flex-start; padding: 7px 10px; border: 0; border-radius: var(--radius-s); background: none; cursor: pointer; text-align: left; }
  .rev:hover { background: var(--panel); }
  .rev.on { background: var(--accent-soft); }
  .small { font-size: 12px; }
  .pad { padding: 12px; }
  .diff { padding: 16px 20px 24px; overflow: auto; }
  .top { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
  h3 { margin: 14px 0 6px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .lines { margin: 0; padding: 10px 0; border-radius: var(--radius-s); background: var(--bg); font: 12.5px/1.6 var(--mono); white-space: pre-wrap; }
  .lines span { display: block; padding: 0 12px; }
  .add { background: rgba(95, 208, 160, 0.12); color: var(--ok); }
  .del { background: var(--danger-soft); color: var(--danger); }
  .hunk { color: var(--accent); background: var(--accent-soft); }
  .same { color: var(--muted); }
</style>
