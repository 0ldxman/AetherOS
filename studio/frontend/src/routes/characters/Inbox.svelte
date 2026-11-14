<script lang="ts">
  // Входящие персонажа в одном канале: что игроки написали ему вне сценариев. Слева список, справа текст и статус.
  import { api, problem, type Schemas } from "../../lib/api";
  import { canEdit } from "../../lib/me.svelte";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  type Row = Schemas["ChInbound"];
  let { character, channel, onchange }: { character: number; channel: string; onchange: () => void } = $props();

  const editable = canEdit("characters");
  const FILTERS = [
    { key: "open", label: "Открытые" }, { key: "new", label: "Новые" }, { key: "taken", label: "Взятые" },
    { key: "answered", label: "Отвеченные" }, { key: "skipped", label: "Пропущенные" }, { key: "all", label: "Все" },
  ];
  const STATUS: Record<string, string> = { new: "новое", taken: "взято", answered: "отвечено", skipped: "пропущено" };
  const EMPTY: Record<string, string> = {
    mail: "Писем вне сценариев нет. Сюда попадает письмо игрока на адрес персонажа, если игрок не выбрал вариант ответа.",
    forum: "Сообщений нет. Сюда попадает ответ игрока на сообщение персонажа и полный позывной персонажа в тексте.",
    air: "Передач нет. Сюда попадает передача игрока, в которой есть полный позывной персонажа.",
  };

  let filter = $state("open");
  let rows = $state<Row[]>([]);
  let picked = $state<Row | null>(null);
  let loaded = $state(false);

  async function load() {
    const { data } = await api.GET("/studio/api/characters/{character_id}/inbox", { params: { path: { character_id: character }, query: { channel, status: filter } } });
    rows = data ?? [];
    loaded = true;
    if (picked) picked = rows.find((r) => r.id === picked!.id) ?? null;
  }
  $effect(() => { void filter; void channel; load(); });

  async function mark(status: string) {
    if (!picked) return;
    const { data, error } = await api.POST("/studio/api/characters/inbox/{inbound_id}/status", { params: { path: { inbound_id: picked.id } }, body: { status } });
    if (error || !data) return toast(problem(error), "error");
    picked = data;
    await load();
    onchange();
  }
  const excerpt = (text: string) => (text.length > 110 ? text.slice(0, 109) + "…" : text);
</script>

<div class="bar">
  {#each FILTERS as f (f.key)}<button class="chip" class:on={filter === f.key} onclick={() => (filter = f.key)}>{f.label}</button>{/each}
</div>

<div class="split">
  <div class="list">
    {#each rows as row (row.id)}
      <button class="row" class:on={picked?.id === row.id} class:fresh={row.status === "new"} onclick={() => (picked = row)}>
        <span class="top"><b>{row.sender}</b>{#if row.player && row.player !== row.sender}<span class="muted small">игрок {row.player}</span>{/if}<span class="spacer"></span><span class="muted small">{when(row.created_at)}</span></span>
        {#if row.subject}<span class="subject">{row.subject}</span>{/if}
        <span class="muted small text">{excerpt(row.text)}</span>
        <span class="st {row.status}">{STATUS[row.status]}{row.taken_by ? ` · ${row.taken_by}` : ""}</span>
      </button>
    {:else}
      {#if loaded}<p class="muted small empty">{filter === "open" ? EMPTY[channel] : "Ничего нет."}</p>{/if}
    {/each}
  </div>

  <div class="view">
    {#if picked}
      <header class="head">
        <div>
          <h3>{picked.subject || picked.sender}</h3>
          <p class="muted small">{picked.sender}{picked.player && picked.player !== picked.sender ? ` (игрок ${picked.player})` : ""} · {when(picked.created_at)}{picked.link ? " · " : ""}
            {#if picked.link.startsWith("#/")}<a href={picked.link}>открыть тему</a>{:else}<span class="mono">{picked.link}</span>{/if}</p>
        </div>
        <span class="st {picked.status}">{STATUS[picked.status]}{picked.taken_by ? ` · ${picked.taken_by}` : ""}</span>
      </header>
      <pre class="body">{picked.text}</pre>
      {#if editable}
        <div class="tools">
          {#if picked.status === "new"}<button class="btn primary" onclick={() => mark("taken")}>Взять себе</button>{/if}
          {#if picked.status !== "answered"}<button class="btn" onclick={() => mark("answered")}>Отвечено</button>{/if}
          {#if picked.status !== "skipped"}<button class="btn ghost" onclick={() => mark("skipped")}>Пропустить</button>{/if}
          {#if picked.status !== "new"}<button class="btn ghost" onclick={() => mark("new")}>Вернуть в новые</button>{/if}
        </div>
      {/if}
      <p class="muted small note">Ответ от персонажа прямо отсюда — следующий шаг. Пока отвечайте в канале (почта, форум, эфир) и отмечайте «Отвечено».</p>
    {:else}
      <p class="muted">Выберите сообщение слева.</p>
    {/if}
  </div>
</div>

<style>
  .bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip { padding: 3px 12px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .split { display: grid; grid-template-columns: minmax(260px, 340px) minmax(0, 1fr); gap: 20px; align-items: start; }
  .list { display: flex; flex-direction: column; gap: 4px; }
  .row { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .row:hover { background: var(--panel); }
  .row.on { border-color: var(--accent); background: var(--accent-soft); }
  .row.fresh { border-left: 3px solid var(--accent); }
  .top { display: flex; align-items: baseline; gap: 8px; }
  .spacer { flex: 1; }
  .subject { font-weight: 600; overflow-wrap: anywhere; }
  .text { overflow-wrap: anywhere; }
  .small { font-size: 12px; }
  .st { align-self: flex-start; padding: 0 6px; border-radius: 999px; font-size: 11px; background: var(--panel); color: var(--muted); }
  .st.new { background: var(--accent-soft); color: var(--text); }
  .st.taken { color: var(--warn); }
  .st.answered { color: var(--ok); }
  .empty { padding: 8px 2px; max-width: 320px; }
  .view { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .head h3 { margin: 0; overflow-wrap: anywhere; }
  .head p { margin: 2px 0 0; }
  .body { margin: 0; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
  .tools { display: flex; flex-wrap: wrap; gap: 8px; }
  .note { margin: 0; }
  .mono { font-family: var(--mono); }
</style>
