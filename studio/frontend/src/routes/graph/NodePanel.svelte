<script lang="ts">
  // Свойства выбранной ноды: поля вида (и настройки старта или ожидания у существительного), проблемы, кто ждёт, запуск «Вручную».
  import { api, problem } from "../../lib/api";
  import { engine } from "../../lib/engine.svelte";
  import { toast } from "../../lib/toast.svelte";
  import type { Catalog, Field, GNode, Kind } from "./kinds";

  let { node, kind, catalog, waiting, fed, problems, stat, statKey, graphId, editable, onchange, onremove, onstarted, groupTitle = null, ongrouptitle, onenter }: {
    node: GNode; kind: Kind; catalog: Catalog; waiting: boolean; fed: Record<string, string>; problems: { text: string; level: string }[];
    stat: { hits: number; players: number; waiting: number; oldest_days: number } | null; statKey: string; graphId: number; editable: boolean;
    onchange: (patch: Partial<GNode>) => void; onremove: () => void; onstarted: () => void;
    groupTitle?: string | null; ongrouptitle?: (title: string) => void; onenter?: () => void;
  } = $props();

  const store = engine();
  const picks = (k: string) => store.catalog?.picks[k] ?? [];
  const PICKED = ["key", "letter", "item", "object", "section", "character", "station", "machine", "moment", "graph"];
  const LISTED = ["flag", "world_flag", "counter"];
  const fields = $derived([...kind.fields, ...(kind.group === "noun" && !kind.start_only ? (waiting ? catalog.wait_fields : catalog.start_fields) : [])]);
  const data = $derived(node.data);
  const value = (name: string) => (data[name] === undefined || data[name] === null ? "" : String(data[name]));
  const set = (name: string, v: unknown) => onchange({ data: { ...data, [name]: v === "" ? undefined : v } });
  const uid = Math.random().toString(36).slice(2, 8);

  const list = (name: string) => (Array.isArray(data[name]) ? (data[name] as unknown[]) : []);
  const rows = $derived(list("rows") as { label?: string; condition?: string }[]);
  const weights = $derived(list("branches") as number[]);
  function setRow(i: number, patch: Record<string, string>) { set("rows", rows.map((r, n) => (n === i ? { ...r, ...patch } : r))); }
  const socks = $derived(list("sockets") as { name: string; label: string }[]);
  function addSock() {
    const taken = new Set(socks.map((x) => x.name));
    let n = socks.length + 1;
    while (taken.has(`s${n}`)) n += 1;
    set("sockets", [...socks, { name: `s${n}`, label: `${kind.name === "group_in" ? "Вход" : "Выход"} ${n}` }]);
  }

  // запуск «Вручную»
  let players = $state<{ id: number; username: string }[]>([]);
  let player = $state("");
  $effect(() => {
    if (kind.name !== "manual" || players.length) return;
    api.GET("/studio/api/players").then(({ data: rowsFound }) => { players = (rowsFound ?? []).filter((r) => !r.staff).map((r) => ({ id: r.id, username: r.username })); });
  });
  async function start() {
    const { data: done, error } = await api.POST("/studio/api/world/graphs/{graph_id}/start", { params: { path: { graph_id: graphId } }, body: { node: node.id, player: player ? +player : null } });
    if (error || !done) return toast(problem(error), "error");
    toast(done.status === "skipped" ? "Не запущено." : done.status === "running" ? "Прохождение идёт: ждёт на нодах." : `Прохождение закончено${done.outcome ? `: ${done.outcome}` : ""}.`);
    onstarted();
  }

  // кто ждёт на ноде
  let waiters = $state<{ player: string; player_id: number | null; since: string }[]>([]);
  $effect(() => {
    const id = statKey;
    if (!stat?.waiting) { waiters = []; return; }
    api.GET("/studio/api/world/graphs/{graph_id}/waiting/{node}", { params: { path: { graph_id: graphId, node: id } } }).then(({ data: found }) => { waiters = found ?? []; });
  });
  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const when = (iso: string) => { const d = new Date(iso); return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const shown = (f: Field) => f.kind !== "hidden" && !(kind.name === "wait" && ((f.name === "minutes" && (data.mode ?? "delay") !== "delay") || (f.name === "at" && data.mode !== "until")
                                  || (f.name === "condition" && data.mode !== "condition") || (f.name === "timeout" && data.mode !== "condition")))
                              && !(kind.name === "time" && f.name === "date" && data.mode !== "once");
</script>

<div class="panel">
  <div class="title">
    <b>{kind.label}</b><span class="muted mono small">{node.id}</span>
    <span class="spacer"></span>
    {#if editable}<button class="btn ghost danger tiny" onclick={onremove}>Удалить</button>{/if}
  </div>
  {#if kind.group === "noun"}
    <p class="muted small">{kind.start_only ? "Только старт: запускает прохождение." : waiting ? "Ждёт: прохождение стоит здесь, пока событие не случится у этого игрока." : "Старт: событие запускает прохождение для игрока, у которого оно случилось. Подведите провод на вход, чтобы нода ждала."}</p>
  {/if}

  {#if kind.name === "group" && groupTitle !== null}
    <label class="cell"><span class="label">Название группы</span>
      <input class="field" value={groupTitle} disabled={!editable} oninput={(e) => ongrouptitle?.(e.currentTarget.value)} /></label>
    <button class="btn" onclick={() => onenter?.()}>Открыть группу (Tab)</button>
    <p class="muted small">Внутри: «Вход» и «Выход» задают сокеты этой ноды. Та же группа может стоять в графе несколько раз (Ctrl+D).</p>
  {:else if kind.name === "scenario"}
    <p class="muted small">Другой сценарий целиком, как группа: его ноды «Вход» и «Выход» — сокеты этой ноды. Работает в прохождении этого сценария; старты вложенного здесь не срабатывают.</p>
  {:else if kind.name === "group_in" || kind.name === "group_out"}
    <p class="muted small">{kind.name === "group_in" ? "Сокеты слева у ноды группы (или у ноды «Сценарий» в других графах)." : "Сокеты справа у ноды группы."} На верхнем уровне сценария «Вход» — куда приходит «Запустить сценарий».</p>
  {/if}

  <fieldset class="fields" disabled={!editable}>
    {#each fields.filter(shown) as f (f.name)}
      {#if f.kind === "sockets"}
        <div class="cell"><span class="label">{f.label}</span>
          {#each socks as sock, i (sock.name)}
            <div class="line">
              <span class="muted mono small">{sock.name}</span>
              <input class="field" value={sock.label} oninput={(e) => set("sockets", socks.map((x, n) => (n === i ? { ...x, label: e.currentTarget.value } : x)))} />
              <button class="x" onclick={() => set("sockets", socks.filter((_, n) => n !== i))} aria-label="Убрать сокет">✕</button>
            </div>
          {/each}
          <button class="btn ghost tiny" onclick={addSock}>+ сокет</button>
        </div>
      {:else if fed[f.name]}
        <div class="cell"><span class="label">{f.label}</span><span class="fed">◆ из ноды «{fed[f.name]}»</span></div>
      {:else if f.kind === "bool"}
        <label class="check"><input type="checkbox" checked={!!data[f.name]} onchange={(e) => set(f.name, e.currentTarget.checked || undefined)} />{f.label}</label>
      {:else if PICKED.includes(f.kind)}
        <label class="cell"><span class="label">{f.label}{f.required ? "" : " (необязательно)"}</span>
          <select class="field" value={value(f.name)} onchange={(e) => set(f.name, f.kind === "section" ? Number(e.currentTarget.value) || undefined : e.currentTarget.value)}>
            <option value="">{f.placeholder || "— выбрать —"}</option>
            {#if data[f.name] && !picks(f.kind).some((o) => o.value === value(f.name))}<option value={value(f.name)}>{value(f.name)}</option>{/if}
            {#each picks(f.kind) as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
          </select></label>
      {:else if f.kind === "select"}
        <label class="cell"><span class="label">{f.label}</span>
          <select class="field" value={value(f.name) || f.options[0]?.value} onchange={(e) => set(f.name, e.currentTarget.value)}>
            {#each f.options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
          </select></label>
      {:else if f.kind === "number"}
        <label class="cell"><span class="label">{f.label}</span>
          <input class="field" type="number" min="0" value={value(f.name)} placeholder={f.placeholder} oninput={(e) => set(f.name, e.currentTarget.value === "" ? undefined : +e.currentTarget.value)} /></label>
      {:else if f.kind === "textarea"}
        <label class="cell"><span class="label">{f.label}</span>
          <textarea class="field" rows="4" value={value(f.name)} placeholder={f.placeholder} oninput={(e) => set(f.name, e.currentTarget.value)}></textarea></label>
      {:else if f.kind === "condition"}
        <label class="cell"><span class="label">{f.label}</span>
          <input class="field mono" value={value(f.name)} placeholder="flag:met and boreas-key or world:alarm" oninput={(e) => set(f.name, e.currentTarget.value)} /></label>
      {:else if f.kind === "rows"}
        <div class="cell"><span class="label">{f.label}: первая верная строка ведёт в свой выход, иначе «Иначе»</span>
          {#each rows as row, i (i)}
            <div class="line">
              <input class="field small-in" value={row.label ?? ""} placeholder="Подпись" oninput={(e) => setRow(i, { label: e.currentTarget.value })} />
              <input class="field mono" value={row.condition ?? ""} placeholder="flag:x" oninput={(e) => setRow(i, { condition: e.currentTarget.value })} />
              <button class="x" onclick={() => set("rows", rows.filter((_, n) => n !== i))} aria-label="Убрать строку">✕</button>
            </div>
          {/each}
          <button class="btn ghost tiny" onclick={() => set("rows", [...rows, { label: "", condition: "" }])}>+ строка</button>
        </div>
      {:else if f.kind === "weights"}
        <div class="cell"><span class="label">{f.label}: чем больше вес, тем чаще ветка</span>
          {#each weights as w, i (i)}
            <div class="line"><span class="muted small">Ветка {i + 1}</span>
              <input class="field num" type="number" min="0" value={w} oninput={(e) => set("branches", weights.map((x, n) => (n === i ? +e.currentTarget.value : x)))} />
              <button class="x" onclick={() => set("branches", weights.filter((_, n) => n !== i))} aria-label="Убрать ветку">✕</button></div>
          {/each}
          <button class="btn ghost tiny" onclick={() => set("branches", [...weights, 1])}>+ ветка</button>
        </div>
      {:else}
        <label class="cell"><span class="label">{f.label}{f.required ? "" : " (необязательно)"}</span>
          <input class="field" class:mono={LISTED.includes(f.kind) || f.kind === "clock"} value={value(f.name)} placeholder={f.placeholder}
                 list={LISTED.includes(f.kind) ? `gr-${uid}-${f.kind}` : undefined} oninput={(e) => set(f.name, e.currentTarget.value)} /></label>
      {/if}
    {/each}
    <label class="check"><input type="checkbox" checked={!!node.mute} onchange={(e) => onchange({ mute: e.currentTarget.checked || undefined })} />Выключена (M): поток идёт насквозь</label>
  </fieldset>
  {#each LISTED as k (k)}<datalist id={`gr-${uid}-${k}`}>{#each picks(k) as o (o.value)}<option value={o.value}></option>{/each}</datalist>{/each}

  {#if problems.length}
    <div class="problems">
      {#each problems as p, i (i)}<p class="problem" class:error={p.level === "error"}>{p.text}</p>{/each}
    </div>
  {/if}

  {#if kind.name === "manual"}
    <div class="box">
      <span class="label">Запустить сейчас</span>
      <div class="line">
        <select class="field" bind:value={player}>
          <option value="">для мира (без игрока)</option>
          {#each players as p (p.id)}<option value={String(p.id)}>{p.username}</option>{/each}
        </select>
        <button class="btn" onclick={start}>Запустить</button>
      </div>
      <p class="muted small">Сценарий должен быть включён и сохранён.</p>
    </div>
  {/if}

  {#if stat && (stat.hits || stat.waiting)}
    <div class="box">
      <span class="label">Прошли {stat.hits} раз · игроков {stat.players}{stat.waiting ? ` · ждут ${stat.waiting}` : ""}</span>
      {#each waiters as w, i (i)}
        <div class="waiter">{#if w.player_id}<a href="#/players/{w.player_id}">{w.player}</a>{:else}<span>{w.player}</span>{/if}<span class="muted small">с {when(w.since)}</span></div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .panel { display: flex; flex-direction: column; gap: 10px; }
  .title { display: flex; align-items: baseline; gap: 8px; }
  .spacer { flex: 1; }
  .fields { display: flex; flex-direction: column; gap: 9px; border: 0; padding: 0; margin: 0; min-width: 0; }
  .cell { display: flex; flex-direction: column; gap: 3px; }
  .label { font-size: 11.5px; color: var(--muted); margin: 0; }
  .check { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; }
  .line { display: flex; gap: 6px; align-items: center; }
  .line .field { flex: 1; min-width: 0; }
  .small-in { flex: 0 0 90px !important; }
  .num { flex: 0 0 80px !important; }
  .fed { font-size: 12px; color: #c792ea; }
  textarea { resize: vertical; font: inherit; }
  .small { font-size: 12px; margin: 0; }
  .tiny { padding: 2px 8px; font-size: 12px; align-self: flex-start; }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 0 4px; }
  .x:hover { color: var(--danger); }
  .problems { display: flex; flex-direction: column; gap: 4px; }
  .problem { margin: 0; padding: 6px 8px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); font-size: 12px; }
  .problem.error { background: var(--danger-soft); color: var(--danger); }
  .box { display: flex; flex-direction: column; gap: 6px; padding: 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .waiter { display: flex; justify-content: space-between; gap: 8px; font-size: 12.5px; }
</style>
