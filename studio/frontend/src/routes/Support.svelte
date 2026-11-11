<script lang="ts">
  // Поддержка: очередь обращений игроков слева, переписка посередине, статус, исполнитель и где был игрок справа.
  // Ответ уходит игроку (статус «ждёт игрока»), заметка видна только команде. Вложения: картинки сразу в переписке.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import { canEdit, me } from "../lib/me.svelte";
  import { RoomPing } from "../lib/shared.svelte";
  import { ago, when } from "../lib/time";
  import { toast } from "../lib/toast.svelte";

  let { id }: { id: number | null } = $props();

  let rows = $state<Schemas["SpRow"][]>([]);
  let ticket = $state<Schemas["SpTicket"] | null>(null);
  let meta = $state<Schemas["SpMeta"] | null>(null);
  let filter = $state("active");
  let text = $state("");
  let internal = $state(false);
  let files = $state<File[]>([]);
  let busy = $state(false);
  let loaded = $state(false);
  let zoom = $state("");
  let picker = $state<HTMLInputElement>();
  let thread = $state<HTMLElement>();

  const editable = canEdit("support");
  const MAX_FILES = 5;
  const MAX_SIZE = 5 * 1024 * 1024;
  const FILTERS = [{ value: "active", label: "Открытые" }, { value: "new", label: "Новые" }, { value: "mine", label: "Мои" }, { value: "closed", label: "Закрытые" }, { value: "", label: "Все" }];
  const STATUS_TONE: Record<string, string> = { new: "warn", open: "accent", waiting: "ok", closed: "" };
  const CATEGORY: Record<string, string> = { bug: "ошибка", stuck: "застрял", other: "другое" };
  const statusLabel = (value: string) => meta?.statuses.find((s) => s.value === value)?.label ?? value;
  const fileUrl = (fileId: number) => `${window.STUDIO.api.replace(/\/$/, "")}/support/files/${fileId}`;
  const size = (bytes: number) => (bytes < 1024 ? `${bytes} Б` : bytes < 1048576 ? `${Math.round(bytes / 1024)} КБ` : `${(bytes / 1048576).toFixed(1)} МБ`);

  async function loadList() {
    const query = filter === "mine" ? { mine: true, status: "active" } : { status: filter };
    rows = (await api.GET("/studio/api/support", { params: { query } })).data ?? [];
    loaded = true;
  }
  async function load() {
    if (!id) return;
    const { data } = await api.GET("/studio/api/support/{ticket_id}", { params: { path: { ticket_id: id } } });
    if (!data) return toast("Обращение не найдено.", "error");
    const grew = (data.messages.length ?? 0) !== (ticket?.messages.length ?? -1);
    ticket = data;
    if (grew) queueMicrotask(() => thread?.scrollTo({ top: thread.scrollHeight }));
  }
  onMount(() => {
    api.GET("/studio/api/support/meta").then(({ data }) => (meta = data ?? null));
    loadList();
    load();
    const timer = setInterval(() => { if (!document.hidden) { loadList(); load(); } }, 20000);
    return () => clearInterval(timer);
  });

  const ping = new RoomPing({ room: () => (id ? `support/${id}` : ""), onPing: () => { load(); loadList(); } });

  function pick(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    for (const file of input.files ?? []) {
      if (files.length >= MAX_FILES) { toast(`Не больше ${MAX_FILES} файлов.`, "error"); break; }
      if (file.size > MAX_SIZE) { toast(`${file.name}: больше 5 МБ.`, "error"); continue; }
      files = [...files, file];
    }
    input.value = "";
  }

  async function send() {
    if (!id || (!text.trim() && !files.length)) return;
    busy = true;
    const body = new FormData();
    body.append("text", text);
    body.append("internal", internal ? "true" : "false");
    for (const file of files) body.append("files", file);
    const { data, error } = await api.POST("/studio/api/support/{ticket_id}/reply", {
      params: { path: { ticket_id: id } }, body: {} as never, bodySerializer: () => body,
    });
    busy = false;
    if (error || !data) return toast(problem(error, "Не отправилось."), "error");
    ticket = data;
    text = "";
    files = [];
    ping.send();
    loadList();
    queueMicrotask(() => thread?.scrollTo({ top: thread.scrollHeight }));
    toast(internal ? "Заметка добавлена." : "Ответ отправлен игроку.");
    internal = false;
  }

  async function change(patch: Partial<Schemas["SpChange"]>) {
    if (!id) return;
    const { data, error } = await api.PUT("/studio/api/support/{ticket_id}", { params: { path: { ticket_id: id } }, body: { unassign: false, ...patch } });
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    ticket = data;
    ping.send();
    loadList();
  }

  const contextRows = $derived.by(() => {
    const c = (ticket?.context ?? {}) as Record<string, string | number>;
    const out: { label: string; value: string; link?: string }[] = [];
    if (c.machine) out.push({ label: "Машина", value: String(c.machine), link: c.machine_id ? `#/machines/${c.machine_id}` : undefined });
    if (c.login) out.push({ label: "Учётка", value: String(c.login), link: c.machine_id && c.profile_id ? `#/machines/${c.machine_id}/accounts/${c.profile_id}` : undefined });
    if (c.user_agent) out.push({ label: "Браузер", value: String(c.user_agent) });
    return out;
  });
</script>

<div class="support">
  <aside class="queue">
    <h1>Поддержка</h1>
    <div class="filters" role="tablist">
      {#each FILTERS as f (f.value)}
        <button role="tab" class:on={filter === f.value} aria-selected={filter === f.value} onclick={() => { filter = f.value; loadList(); }}>{f.label}</button>
      {/each}
    </div>
    <div class="rows">
      {#each rows as r (r.id)}
        <a class="row" class:on={r.id === id} href={`#/support/${r.id}`}>
          <span class="row-head"><b>{r.subject}</b>{#if r.waiting_on_team}<span class="dot" title="Последнее слово за игроком"></span>{/if}</span>
          <span class="muted small"><span class="tone {STATUS_TONE[r.status]}">{statusLabel(r.status)}</span> · {r.player} · {ago(r.updated_at)}</span>
          {#if r.assignee}<span class="muted small">исполнитель: {r.assignee}</span>{/if}
        </a>
      {:else}
        {#if loaded}<p class="muted small pad-s">Обращений нет.</p>{/if}
      {/each}
    </div>
  </aside>

  {#if !id}
    <div class="pad"><h2>Поддержка игроков</h2><p class="muted">Игрок пишет из приложения support на своём столе. Выберите обращение слева.</p></div>
  {:else if !ticket}
    <p class="muted pad">Загрузка…</p>
  {:else}
    <section class="talk">
      <header class="head">
        <h2>#{ticket.id} {ticket.subject}</h2>
        <span class="muted small">{CATEGORY[ticket.category] ?? ticket.category} · {when(ticket.created_at)}</span>
      </header>
      <div class="thread" bind:this={thread}>
        {#each ticket.messages as m (m.id)}
          <div class="msg" class:staff={m.staff && !m.internal} class:note={m.internal}>
            <div class="msg-head"><b>{m.staff ? m.author : ticket.player}</b>{#if m.staff && !m.internal}<span class="muted">как {ticket.responder || ticket.default_responder}</span>{/if}{#if m.internal}<span class="tag">заметка команды</span>{/if}<span class="muted">{when(m.created_at)}</span></div>
            {#if m.text}<div class="msg-text">{m.text}</div>{/if}
            {#if m.files.length}
              <div class="files">
                {#each m.files as f (f.id)}
                  {#if f.image}
                    <button class="shot" onclick={() => (zoom = fileUrl(f.id))} title={f.name}><img src={fileUrl(f.id)} alt={f.name} loading="lazy" /></button>
                  {:else}
                    <a class="file" href={fileUrl(f.id)} download={f.name}>⎙ {f.name} · {size(f.size)}</a>
                  {/if}
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
      {#if editable}
        <form class="reply" class:note={internal} onsubmit={(e) => { e.preventDefault(); send(); }}>
          <textarea class="field" rows="3" bind:value={text} placeholder={internal ? "Заметка для команды: игрок её не увидит" : `Ответ игроку от имени ${ticket.responder || ticket.default_responder} (по-английски)`}
                    onkeydown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }} aria-label="Сообщение"></textarea>
          {#if files.length}
            <div class="picked">
              {#each files as f, i (i)}<span class="file">{f.name} · {size(f.size)}<button type="button" class="x" onclick={() => (files = files.filter((_, n) => n !== i))} aria-label="Убрать {f.name}">✕</button></span>{/each}
            </div>
          {/if}
          <div class="reply-bar">
            <input type="file" multiple hidden bind:this={picker} onchange={pick} />
            <button type="button" class="btn ghost" onclick={() => picker?.click()} disabled={files.length >= MAX_FILES}>Приложить файлы</button>
            <label class="check"><input type="checkbox" bind:checked={internal} />Заметка команды</label>
            <span class="spacer"></span>
            <button class="btn primary" disabled={busy || (!text.trim() && !files.length)}>{internal ? "Добавить заметку" : "Ответить"}</button>
          </div>
        </form>
      {/if}
    </section>

    <aside class="side">
      <label><span class="label">Статус</span>
        <select class="field" value={ticket.status} onchange={(e) => change({ status: e.currentTarget.value })} disabled={!editable}>
          {#each meta?.statuses ?? [] as s (s.value)}<option value={s.value}>{s.label}</option>{/each}
        </select></label>
      <label><span class="label">Исполнитель</span>
        <select class="field" value={ticket.assignee_id ?? ""} disabled={!editable}
                onchange={(e) => change(e.currentTarget.value ? { assignee: +e.currentTarget.value } : { unassign: true })}>
          <option value="">не назначен</option>
          {#each meta?.authors ?? [] as a (a.id)}<option value={a.id}>{a.username}</option>{/each}
        </select></label>
      {#if editable && ticket.assignee_id !== me.data?.id}<button class="btn ghost tiny" onclick={() => change({ assignee: me.data?.id as number })}>Взять себе</button>{/if}
      <label><span class="label">Кто отвечает игроку</span>
        <input class="field" value={ticket.responder} placeholder={ticket.default_responder} maxlength="60" disabled={!editable}
               onchange={(e) => change({ responder: e.currentTarget.value })} />
        <span class="muted small">Этим именем подписаны все ответы в диалоге: для игрока это ИИ узла. Пусто: {ticket.default_responder}.</span></label>
      <div class="block">
        <span class="label">Игрок</span>
        <a href={`#/players/${ticket.player_id}`}>{ticket.player}</a>
      </div>
      <div class="block">
        <span class="label">Где был, когда писал</span>
        {#each contextRows as c (c.label)}
          <div class="ctx"><span class="muted">{c.label}</span>{#if c.link}<a href={c.link}>{c.value}</a>{:else}<span class="wrap">{c.value}</span>{/if}</div>
        {:else}
          <span class="muted small">Не известно.</span>
        {/each}
      </div>
    </aside>
  {/if}
</div>

{#if zoom}
  <button class="lightbox" onclick={() => (zoom = "")} aria-label="Закрыть картинку"><img src={zoom} alt="" /></button>
{/if}

<style>
  .support { display: grid; grid-template-columns: 300px minmax(0, 1fr) 280px; height: 100vh; }
  .queue { display: flex; flex-direction: column; gap: 8px; padding: 20px 8px; border-right: 1px solid var(--line-soft); min-height: 0; }
  h1 { margin: 0 10px 4px; font-size: 18px; }
  .filters { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 6px; }
  .filters button { padding: 3px 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); cursor: pointer; font: inherit; font-size: 12.5px; }
  .filters button.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .rows { display: flex; flex-direction: column; gap: 2px; overflow-y: auto; min-height: 0; }
  .row { display: flex; flex-direction: column; gap: 1px; padding: 8px 10px; border-radius: var(--radius-s); color: var(--text); }
  .row:hover { background: var(--panel); text-decoration: none; }
  .row.on { background: var(--accent-soft); }
  .row-head { display: flex; align-items: center; gap: 6px; }
  .row-head b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  .tone.warn { color: var(--warn); }
  .tone.accent { color: var(--accent); }
  .tone.ok { color: var(--ok); }
  .small { font-size: 12px; margin: 0; }
  .pad { padding: 20px 32px; }
  .pad-s { padding: 4px 10px; }
  .talk { display: flex; flex-direction: column; min-height: 0; min-width: 0; }
  .head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; padding: 16px 24px 10px; border-bottom: 1px solid var(--line-soft); }
  .head h2 { margin: 0; font-size: 18px; }
  .thread { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding: 16px 24px; }
  .msg { max-width: 720px; padding: 10px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .msg.staff { align-self: flex-end; border-color: color-mix(in srgb, var(--accent) 45%, transparent); background: var(--accent-soft); }
  .msg.note { align-self: flex-end; border-style: dashed; border-color: var(--warn); background: rgba(242, 198, 109, 0.07); }
  .msg-head { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; margin-bottom: 4px; }
  .tag { padding: 0 6px; border-radius: 999px; border: 1px solid var(--warn); color: var(--warn); font-size: 11px; }
  .msg-text { white-space: pre-wrap; overflow-wrap: anywhere; }
  .files { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  .shot { padding: 0; border: 1px solid var(--line); border-radius: var(--radius-s); background: none; cursor: zoom-in; }
  .shot img { display: block; max-width: 260px; max-height: 180px; border-radius: var(--radius-s); }
  .file { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); color: var(--text); font-size: 12.5px; }
  .reply { display: flex; flex-direction: column; gap: 8px; padding: 12px 24px 18px; border-top: 1px solid var(--line-soft); }
  .reply.note textarea { border-color: var(--warn); }
  textarea { resize: vertical; font: inherit; }
  .picked { display: flex; flex-wrap: wrap; gap: 6px; }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 0 2px; }
  .x:hover { color: var(--danger); }
  .reply-bar { display: flex; align-items: center; gap: 10px; }
  .spacer { flex: 1; }
  .check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .side { display: flex; flex-direction: column; gap: 14px; padding: 16px; border-left: 1px solid var(--line-soft); overflow-y: auto; }
  .side label, .block { display: flex; flex-direction: column; gap: 4px; }
  .tiny { padding: 3px 10px; font-size: 12.5px; align-self: flex-start; }
  .ctx { display: flex; flex-direction: column; font-size: 12.5px; }
  .wrap { overflow-wrap: anywhere; font-size: 11.5px; color: var(--muted); }
  .lightbox { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; border: 0; background: rgba(0, 0, 0, 0.82); cursor: zoom-out; }
  .lightbox img { max-width: 92vw; max-height: 92vh; }
</style>
