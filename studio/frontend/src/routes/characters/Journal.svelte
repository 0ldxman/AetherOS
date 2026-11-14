<script lang="ts">
  // Журнал персонажа: всё, что авторы сказали за него, кто и кому, в каком канале; отложенное можно отменить.
  import { api, problem, type Schemas } from "../../lib/api";
  import { canEdit } from "../../lib/me.svelte";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  let { character }: { character: number } = $props();
  const STATUS: Record<string, string> = { pending: "ждёт отправки", sent: "отправлено", failed: "не ушло", cancelled: "отменено" };
  const CH: Record<string, string> = { mail: "почта", forum: "форум", air: "эфир" };
  let rows = $state<Schemas["ChReply"][]>([]);
  let loaded = $state(false);

  async function load() {
    rows = (await api.GET("/studio/api/characters/{character_id}/replies", { params: { path: { character_id: character } } })).data ?? [];
    loaded = true;
  }
  load();
  async function cancel(id: number) {
    const { error } = await api.POST("/studio/api/characters/replies/{reply_id}/cancel", { params: { path: { reply_id: id } } });
    if (error) return toast(problem(error), "error");
    await load();
  }
</script>

<div class="list">
  {#each rows as r (r.id)}
    <div class="row {r.status}">
      <div class="meta">
        <b>{r.author || "—"}</b><span class="muted small">→ {r.player || "?"} · {CH[r.channel]} · {r.where}</span>
        <span class="spacer"></span><span class="st">{STATUS[r.status]}</span><span class="muted small">{when(r.sent_at ?? r.send_at)}</span>
      </div>
      {#if r.subject}<span class="subject">{r.subject}</span>{/if}
      <span class="text">{r.text}</span>
      {#if r.actions.length}<span class="muted small">действия: {r.actions.map((a) => `${a.do} ${a.name ?? ""}`).join(", ")}</span>{/if}
      {#if r.error}<span class="error small">{r.error}</span>{/if}
      {#if r.status === "pending" && canEdit("characters")}<button class="link" onclick={() => cancel(r.id)}>отменить</button>{/if}
    </div>
  {:else}
    {#if loaded}<p class="muted">Персонаж ещё ничего не сказал из панели.</p>{/if}
  {/each}
</div>

<style>
  .list { display: flex; flex-direction: column; gap: 8px; max-width: 860px; }
  .row { display: flex; flex-direction: column; gap: 3px; padding: 8px 12px; border: 1px solid var(--line-soft); border-left: 3px solid var(--accent); border-radius: var(--radius-s); }
  .row.pending { border-left-color: var(--warn); }
  .row.failed { border-left-color: var(--danger, #f85149); }
  .row.cancelled { opacity: 0.6; }
  .meta { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
  .spacer { flex: 1; }
  .st { font-size: 11px; color: var(--muted); }
  .subject { font-weight: 600; }
  .text { white-space: pre-wrap; overflow-wrap: anywhere; }
  .small { font-size: 12px; }
  .link { align-self: flex-start; padding: 0; border: 0; background: none; color: var(--accent); font: inherit; font-size: 12px; cursor: pointer; }
</style>
