<script lang="ts">
  // Список сценариев-графов: включён ли, сколько нод, сколько ходов идёт, есть ли ошибки. «+ Сценарий» создаёт пустой и открывает холст.
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { canEdit } from "../lib/me.svelte";
  import { slugify } from "../lib/slug";
  import { toast } from "../lib/toast.svelte";

  let rows = $state<Schemas["GrRow"][] | null>(null);
  let dialog = $state(false);
  let draft = $state({ title: "", slug: "" });
  let slugTouched = $state(false);
  const editable = canEdit("world");

  async function list() { rows = (await api.GET("/studio/api/world/graphs")).data ?? []; }
  $effect(() => { list(); });

  async function create() {
    const { data, error } = await api.POST("/studio/api/world/graphs", { body: { title: draft.title, slug: draft.slug, note: "", active: false, doc: { nodes: [], wires: [] } } });
    if (error || !data) return toast(problem(error), "error");
    dialog = false;
    location.hash = `#/graphs/${data.id}`;
  }
  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const when = (iso: string) => { const d = new Date(iso); return `${d.getDate()} ${MONTHS[d.getMonth()]}`; };
</script>

<PageHead title="Сценарии">
  {#snippet sub()}Поведение мира, собранное из нод: что случилось, чего ждать, что сделать. Тот же холст показывает, где стоят игроки.{/snippet}
  {#if editable}<button class="btn primary" onclick={() => { draft = { title: "", slug: "" }; slugTouched = false; dialog = true; }}>+ Сценарий</button>{/if}
</PageHead>

<div class="list">
  {#if rows === null}
    <p class="muted">Загрузка…</p>
  {:else}
    {#each rows as row (row.id)}
      <a class="row" href="#/graphs/{row.id}">
        <span class="dot" class:on={row.active} title={row.active ? "Включён" : "Выключен"}></span>
        <span class="name"><b>{row.title}</b><span class="muted mono">{row.slug}</span></span>
        <span class="muted">нод {row.nodes}</span>
        <span class="muted">ходов {row.running}</span>
        {#if row.errors}<span class="err">ошибок {row.errors}</span>{:else}<span></span>{/if}
        <span class="muted">{when(row.updated_at)}</span>
      </a>
    {:else}
      <p class="muted empty">Сценариев пока нет. Создайте первый: на холсте Shift+A добавляет ноду, провод из выхода в вход задаёт порядок.</p>
    {/each}
  {/if}
</div>

{#if dialog}
  <Dialog title="Новый сценарий" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)}>
    <label><span class="label">Название</span><input class="field" bind:value={draft.title} oninput={() => { if (!slugTouched) draft.slug = slugify(draft.title); }} placeholder="Взлом архива" /></label>
    <label><span class="label">Имя</span><input class="field mono" bind:value={draft.slug} oninput={() => (slugTouched = true)} placeholder="archive-breach" /></label>
  </Dialog>
{/if}

<style>
  .list { display: flex; flex-direction: column; gap: 6px; margin: 12px 32px; max-width: 980px; }
  .row { display: grid; grid-template-columns: 14px minmax(0, 1fr) 70px 70px 90px 60px; align-items: center; gap: 12px; padding: 10px 14px;
         border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel); color: var(--text); font-size: 13px; }
  .row:hover { border-color: var(--line); background: var(--panel-2); }
  .name { display: flex; flex-direction: column; min-width: 0; }
  .name .mono { font-size: 11.5px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--line); }
  .dot.on { background: var(--ok); }
  .err { color: var(--danger); }
  .empty { max-width: 560px; }
  label { display: flex; flex-direction: column; gap: 4px; }
</style>
