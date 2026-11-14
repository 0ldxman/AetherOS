<script lang="ts">
  // Входящие персонажа в одном канале: список слева; справа сообщение, ответ от персонажа (сразу или через игровое время, с действиями мира),
  // карточка игрока и вся его переписка с персонажем.
  import { api, problem, type Schemas } from "../../lib/api";
  import ActionsEditor from "../../lib/ActionsEditor.svelte";
  import type { Act } from "../../lib/engine.svelte";
  import { canEdit } from "../../lib/me.svelte";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  type Row = Schemas["ChInbound"];
  let { character, code, channel, onchange }: { character: number; code: string; channel: string; onchange: () => void } = $props();

  const editable = canEdit("characters");
  const FILTERS = [
    { key: "open", label: "Открытые" }, { key: "new", label: "Новые" }, { key: "taken", label: "Взятые" },
    { key: "answered", label: "Отвеченные" }, { key: "skipped", label: "Пропущенные" }, { key: "all", label: "Все" },
  ];
  const STATUS: Record<string, string> = { new: "новое", taken: "взято", answered: "отвечено", skipped: "пропущено" };
  const RSTATUS: Record<string, string> = { pending: "ждёт отправки", sent: "отправлено", failed: "не ушло", cancelled: "отменено" };
  const CH: Record<string, string> = { mail: "почта", forum: "форум", air: "эфир" };
  const EMPTY: Record<string, string> = {
    mail: "Писем вне сценариев нет. Сюда попадает письмо игрока на адрес персонажа, если игрок не выбрал вариант ответа.",
    forum: "Сообщений нет. Сюда попадает ответ игрока на сообщение персонажа и полный позывной персонажа в тексте.",
    air: "Передач нет. Сюда попадает передача игрока, в которой есть полный позывной персонажа.",
  };
  const DELAYS = [{ v: 0, l: "сразу" }, { v: 5, l: "через 5 мин" }, { v: 20, l: "через 20 мин" }, { v: 60, l: "через час" }, { v: 180, l: "через 3 часа" }, { v: 720, l: "через 12 часов" }, { v: 1440, l: "через сутки" }];

  let filter = $state("open");
  let rows = $state<Row[]>([]);
  let picked = $state<Row | null>(null);
  let ctx = $state<Schemas["ChContext"] | null>(null);
  let loaded = $state(false);
  let draft = $state({ text: "", subject: "", delay: 0, station: null as number | null, actions: [] as Act[] });
  let busy = $state(false);

  async function load() {
    const { data } = await api.GET("/studio/api/characters/{character_id}/inbox", { params: { path: { character_id: character }, query: { channel, status: filter } } });
    rows = data ?? [];
    loaded = true;
    if (picked) picked = rows.find((r) => r.id === picked!.id) ?? picked;
  }
  $effect(() => { void filter; void channel; load(); });

  async function open(row: Row) {
    picked = row;
    draft = { text: "", subject: "", delay: 0, station: null, actions: [] };
    ctx = (await api.GET("/studio/api/characters/inbox/{inbound_id}/context", { params: { path: { inbound_id: row.id } } })).data ?? null;
    if (ctx?.stations.length) draft.station = ctx.stations[0].id;
  }
  async function mark(status: string) {
    if (!picked) return;
    const { data, error } = await api.POST("/studio/api/characters/inbox/{inbound_id}/status", { params: { path: { inbound_id: picked.id } }, body: { status } });
    if (error || !data) return toast(problem(error), "error");
    picked = data;
    await load();
    onchange();
  }
  async function send() {
    if (!picked) return;
    busy = true;
    const actions = draft.actions;
    const { data, error } = await api.POST("/studio/api/characters/inbox/{inbound_id}/answer", {
      params: { path: { inbound_id: picked.id } }, body: { text: draft.text, subject: draft.subject, delay: draft.delay, actions, station: draft.station } });
    busy = false;
    if (error || !data) return toast(Object.values((error as { fields?: Record<string, string> } | undefined)?.fields ?? {})[0] ?? problem(error), "error");
    toast(data.status === "pending" ? `Уйдёт ${when(data.send_at)}.` : data.status === "sent" ? "Отправлено." : `Не ушло: ${data.error}`, data.status === "failed" ? "error" : undefined);
    const sent = { ...picked, status: "answered" };
    await load();
    await open(rows.find((r) => r.id === sent.id) ?? sent);
    onchange();
  }
  async function cancel(id: number) {
    const { error } = await api.POST("/studio/api/characters/replies/{reply_id}/cancel", { params: { path: { reply_id: id } } });
    if (error) return toast(Object.values((error as { fields?: Record<string, string> }).fields ?? {})[0] ?? problem(error), "error");
    if (picked) await open(picked);
  }
  const excerpt = (text: string) => (text.length > 110 ? text.slice(0, 109) + "…" : text);
  const target = $derived(!picked ? "" : channel === "mail" ? `письмо на ${picked.sender}` : channel === "forum" ? `ответ под сообщением ${picked.sender} в теме «${picked.subject}»`
    : `передача на ${picked.link.replace("частота ", "")}`);
</script>

<div class="bar">
  {#each FILTERS as f (f.key)}<button class="chip" class:on={filter === f.key} onclick={() => (filter = f.key)}>{f.label}</button>{/each}
</div>

<div class="split">
  <div class="list">
    {#each rows as row (row.id)}
      <button class="row" class:on={picked?.id === row.id} class:fresh={row.status === "new"} onclick={() => open(row)}>
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
          {#if picked.status === "new"}<button class="btn" onclick={() => mark("taken")}>Взять себе</button>{/if}
          {#if picked.status !== "answered"}<button class="btn ghost" onclick={() => mark("answered")}>Отвечено без ответа</button>{/if}
          {#if picked.status !== "skipped"}<button class="btn ghost" onclick={() => mark("skipped")}>Пропустить</button>{/if}
          {#if picked.status !== "new"}<button class="btn ghost" onclick={() => mark("new")}>Вернуть в новые</button>{/if}
        </div>

        <section class="compose">
          <h4>Ответ от {code}: {target}</h4>
          {#if channel === "mail"}<input class="field" bind:value={draft.subject} placeholder={`Re: ${picked.subject}`} aria-label="Тема письма" />{/if}
          {#if channel === "air" && ctx && ctx.stations.length > 1}
            <select class="field" bind:value={draft.station} aria-label="Позывной">{#each ctx.stations as s (s.id)}<option value={s.id}>{s.label}</option>{/each}</select>
          {/if}
          <textarea class="field" rows="5" bind:value={draft.text} placeholder="что скажет персонаж"></textarea>
          <div class="acts">
            <ActionsEditor bind:actions={draft.actions} provides={["world", "user"]} addLabel="+ действие при отправке" />
          </div>
          <div class="send">
            <select class="field" bind:value={draft.delay} aria-label="Когда">{#each DELAYS as d (d.v)}<option value={d.v}>{d.l}</option>{/each}</select>
            <button class="btn primary" disabled={busy || !draft.text.trim()} onclick={send}>{draft.delay ? "Запланировать" : "Отправить"}</button>
            <span class="muted small">Задержка в игровых минутах; входящее станет «отвечено».</span>
          </div>
        </section>
      {/if}

      {#if ctx?.replies.length}
        <section class="block">
          <h4>Ответы на это сообщение</h4>
          {#each ctx.replies as r (r.id)}
            <div class="reply {r.status}">
              <span class="muted small">{r.author} · {RSTATUS[r.status]} · {when(r.sent_at ?? r.send_at)}{r.error ? ` · ${r.error}` : ""}</span>
              <span class="text">{r.text}</span>
              {#if r.status === "pending" && editable}<button class="link" onclick={() => cancel(r.id)}>отменить</button>{/if}
            </div>
          {/each}
        </section>
      {/if}

      {#if ctx?.player}
        <section class="block">
          <h4>Игрок {ctx.player.username} <span class="muted small">позывной {ctx.player.callsign}{ctx.player.online ? " · в сети" : ""}</span></h4>
          <p class="muted small">Учётки: {ctx.player.accounts.join(", ") || "нет"}</p>
          <p class="muted small">Ключи: {ctx.player.keys.join(", ") || "нет"}</p>
          <h4>Переписка с {code}</h4>
          <div class="history">
            {#each ctx.history as h, n (n)}
              <div class="h {h.kind}">
                <span class="muted small">{h.kind === "in" ? ctx.player.username : `${code}${h.author ? " (" + h.author + ")" : ""}`} · {CH[h.channel]} · {when(h.at)}{h.kind === "out" && h.status !== "sent" ? ` · ${RSTATUS[h.status]}` : ""}</span>
                <span class="text">{h.subject ? h.subject + ": " : ""}{h.text}</span>
              </div>
            {/each}
          </div>
        </section>
      {/if}
    {:else}
      <p class="muted">Выберите сообщение слева.</p>
    {/if}
  </div>
</div>

<style>
  .bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip { padding: 3px 12px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .split { display: grid; grid-template-columns: minmax(260px, 330px) minmax(0, 1fr); gap: 20px; align-items: start; }
  .list { display: flex; flex-direction: column; gap: 4px; }
  .row { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .row:hover { background: var(--panel); }
  .row.on { border-color: var(--accent); background: var(--accent-soft); }
  .row.fresh { border-left: 3px solid var(--accent); }
  .top { display: flex; align-items: baseline; gap: 8px; }
  .spacer { flex: 1; }
  .subject { font-weight: 600; overflow-wrap: anywhere; }
  .text { overflow-wrap: anywhere; white-space: pre-wrap; }
  .small { font-size: 12px; }
  .st { align-self: flex-start; padding: 0 6px; border-radius: 999px; font-size: 11px; background: var(--panel); color: var(--muted); white-space: nowrap; }
  .st.new { background: var(--accent-soft); color: var(--text); }
  .st.taken { color: var(--warn); }
  .st.answered { color: var(--ok); }
  .empty { padding: 8px 2px; max-width: 320px; }
  .view { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .head h3 { margin: 0; overflow-wrap: anywhere; }
  .head p { margin: 2px 0 0; }
  .body { margin: 0; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
  .tools { display: flex; flex-wrap: wrap; gap: 8px; }
  .compose { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px solid var(--accent); border-radius: var(--radius-s); }
  h4 { margin: 0; font-size: 13px; }
  .acts { display: flex; flex-direction: column; gap: 6px; }
  .send { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .send .field { width: auto; }
  .link { padding: 0; border: 0; background: none; color: var(--accent); font: inherit; font-size: 12px; cursor: pointer; }
  .block { display: flex; flex-direction: column; gap: 6px; padding-top: 10px; border-top: 1px solid var(--line-soft); }
  .block p { margin: 0; }
  .reply, .h { display: flex; flex-direction: column; gap: 2px; padding: 6px 10px; border-left: 2px solid var(--line-soft); }
  .reply.pending { border-left-color: var(--warn); }
  .reply.failed { border-left-color: var(--danger, #f85149); }
  .h.out { border-left-color: var(--accent); }
  .history { display: flex; flex-direction: column; gap: 6px; max-height: 360px; overflow: auto; }
  .mono { font-family: var(--mono); }
</style>
