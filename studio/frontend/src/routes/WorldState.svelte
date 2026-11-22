<script lang="ts">
  // Пульт мира: мировые метки, счётчики с вкладами и порогами, триггеры, журнал. Одно состояние на всех игроков.
  // Логика в world/state.py; здесь показ и кнопки автора.
  import { onDestroy, onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import ActionsEditor from "../lib/ActionsEditor.svelte";
  import Hint from "../lib/Hint.svelte";
  import { summary, type Act } from "../lib/engine.svelte";
  import Icon from "../lib/Icon.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import Switch from "../lib/Switch.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { toast } from "../lib/toast.svelte";

  type State = Schemas["WsState"];
  type Counter = Schemas["WsCounter"];
  type Trigger = Schemas["WsTrigger"];
  type Moment = Schemas["WsMoment"];

  let data = $state<State | null>(null);
  let timer: ReturnType<typeof setInterval>;

  function take(next: State | undefined, error?: unknown) {
    if (error || !next) { toast(problem(error), "error"); return false; }
    data = next;
    return true;
  }
  async function load() {
    const { data: next } = await api.GET("/studio/api/world/state");
    if (next) data = next;
  }
  onMount(() => { load(); timer = setInterval(load, 10000); });
  onDestroy(() => clearInterval(timer));

  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const when = (iso: string | null | undefined) => { if (!iso) return ""; const d = new Date(iso); return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };

  // ---------- метки ----------
  async function setFlag(name: string, on: boolean, label = "") {
    const { data: next, error } = await api.POST("/studio/api/world/state/flags", { body: { name, label, on } });
    if (take(next, error)) toast(on ? `world:${name} поставлена.` : `world:${name} снята.`);
  }
  async function dropFlag(name: string) {
    if (!(await ask(`Удалить world:${name}?`, "Условия с этой меткой станут неверными."))) return;
    const { data: next, error } = await api.DELETE("/studio/api/world/state/flags/{name}", { params: { path: { name } } });
    take(next, error);
  }

  // ---------- счётчики ----------
  async function bump(name: string, value: number) {
    const { data: next, error } = await api.POST("/studio/api/world/state/counters/{name}/add", { params: { path: { name } }, body: { value } });
    take(next, error);
  }
  async function dropCounter(name: string) {
    if (!(await ask(`Удалить world:${name}?`, "Значение и все вклады пропадут, условия на счётчик будут считать его нулём."))) return;
    const { data: next, error } = await api.DELETE("/studio/api/world/state/counters/{name}", { params: { path: { name } } });
    take(next, error);
  }
  let labeling = $state<{ name: string; text: string } | null>(null);
  function openLabels(c: Counter) {
    labeling = { name: c.name, text: Object.entries(c.labels).sort((a, b) => +a[0] - +b[0]).map(([k, v]) => `${k} = ${v}`).join("\n") };
  }
  async function saveLabels() {
    if (!labeling) return;
    const labels: Record<string, string> = {};
    for (const line of labeling.text.split("\n")) {
      const [k, ...rest] = line.split("=");
      if (k && rest.length && /^-?\d+$/.test(k.trim())) labels[k.trim()] = rest.join("=").trim();
    }
    const { data: next, error } = await api.PUT("/studio/api/world/state/counters/{name}/labels", { params: { path: { name: labeling.name } }, body: { labels } });
    if (take(next, error)) labeling = null;
  }

  // ---------- моменты ----------
  type MForm = { id: number | null; name: string; label: string; title: string; schedule: string; time_zone: string; duration: number; in_list: boolean; ticker: boolean; toast: boolean; warn: number;
                 systems: string; machines: string; groups: string; condition_text: string; active: boolean };
  let mform = $state<MForm | null>(null);
  const ZONES: string[] = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.("timeZone") ?? ["UTC"];
  const list = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);
  function editMoment(m: Moment | null) {
    mform = m ? { id: m.id, name: m.name, label: m.label, title: m.title, schedule: m.schedule, time_zone: m.time_zone, duration: m.duration, in_list: m.in_list, ticker: m.ticker, toast: m.toast, warn: m.warn,
                  systems: m.systems.join(", "), machines: m.machines.join(", "), groups: m.groups.join(", "), condition_text: condText(m.condition), active: m.active }
              : { id: null, name: "", label: "", title: "", schedule: "once 2031-03-01 21:00", time_zone: "UTC", duration: 30, in_list: true, ticker: true, toast: false, warn: 15,
                  systems: "", machines: "", groups: "", condition_text: "", active: true };
  }
  function condText(c: unknown): string {
    if (!c) return "";
    if (typeof c === "string") return c;
    const o = c as Record<string, unknown>;
    if (Array.isArray(o.all)) return o.all.map((x) => wrap(x)).join(" and ");
    if (Array.isArray(o.any)) return o.any.map((x) => wrap(x)).join(" or ");
    if (o.not !== undefined) return `not ${wrap(o.not)}`;
    return "";
  }
  const wrap = (x: unknown) => (typeof x === "string" ? x : `(${condText(x)})`);
  async function saveMoment() {
    if (!mform) return;
    busy = true;
    const body = { name: mform.name, label: mform.label, title: mform.title, schedule: mform.schedule, time_zone: mform.time_zone, duration: mform.duration, in_list: mform.in_list, ticker: mform.ticker, toast: mform.toast,
                   warn: mform.warn, systems: list(mform.systems), machines: list(mform.machines), groups: list(mform.groups), condition_text: mform.condition_text, active: mform.active };
    const { data: next, error } = mform.id !== null
      ? await api.PUT("/studio/api/world/state/moments/{moment_id}", { params: { path: { moment_id: mform.id } }, body })
      : await api.POST("/studio/api/world/state/moments", { body });
    busy = false;
    if (take(next, error)) { toast(mform.id !== null ? "Момент сохранён." : "Момент добавлен."); mform = null; }
  }
  async function startStop(m: Moment) {
    const { data: next, error } = m.running
      ? await api.POST("/studio/api/world/state/moments/{moment_id}/stop", { params: { path: { moment_id: m.id } } })
      : await api.POST("/studio/api/world/state/moments/{moment_id}/start", { params: { path: { moment_id: m.id } } });
    if (take(next, error)) toast(m.running ? `${m.name} закончен.` : `${m.name} начался: world:${m.name} стоит.`);
  }
  async function dropMoment(m: Moment) {
    if (!(await ask(`Удалить момент ${m.name}?`, "Метка world:" + m.name + " больше не будет ставиться по расписанию."))) return;
    const { data: next, error } = await api.DELETE("/studio/api/world/state/moments/{moment_id}", { params: { path: { moment_id: m.id } } });
    take(next, error);
  }
  function inZone(iso: string | null | undefined, zone: string) {
    if (!iso) return "";
    try {
      return new Intl.DateTimeFormat("ru-RU", { timeZone: zone, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(new Date(iso));
    } catch { return when(iso); }
  }
  function until(iso: string | null | undefined) {
    if (!iso) return "";
    const ms = Date.parse(iso) - Date.now();
    if (ms <= 0) return "сейчас";
    const m = Math.round(ms / 60000), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60);
    return d ? `через ${d} д ${h} ч` : h ? `через ${h} ч ${m % 60} мин` : `через ${m} мин`;
  }
  const audience = (m: Moment) => [m.systems.length ? `ОС ${m.systems.join(", ")}` : "", m.machines.length ? `машины ${m.machines.join(", ")}` : "",
    m.groups.length ? `группы ${m.groups.join(", ")}` : "", m.condition ? `с условием ${condText(m.condition)}` : ""].filter(Boolean).join(" · ") || "все";

  // ---------- триггеры ----------
  type TForm = { id: number | null; name: string; label: string; condition_text: string; actions: Act[]; repeat: boolean; active: boolean };
  let tform = $state<TForm | null>(null);
  let busy = $state(false);
  function editTrigger(t: Trigger | null) {
    tform = t ? { id: t.id, name: t.name, label: t.label, condition_text: t.condition_text, actions: (t.actions as Act[]).map((a) => ({ ...a })), repeat: t.repeat, active: t.active }
              : { id: null, name: "", label: "", condition_text: "", actions: [{ do: "world_flag", name: "" }], repeat: false, active: true };
  }
  async function saveTrigger() {
    if (!tform) return;
    busy = true;
    const body = { name: tform.name, label: tform.label, condition_text: tform.condition_text, actions: tform.actions as Record<string, unknown>[], repeat: tform.repeat, active: tform.active };
    const { data: next, error } = tform.id !== null
      ? await api.PUT("/studio/api/world/state/triggers/{trigger_id}", { params: { path: { trigger_id: tform.id } }, body })
      : await api.POST("/studio/api/world/state/triggers", { body });
    busy = false;
    if (take(next, error)) { toast(tform.id !== null ? "Триггер сохранён." : "Триггер добавлен."); tform = null; }
  }
  async function fire(t: Trigger) {
    if (!(await ask(`Запустить ${t.name} сейчас?`, "Действия выполнятся сразу, независимо от условия."))) return;
    const { data: next, error } = await api.POST("/studio/api/world/state/triggers/{trigger_id}/fire", { params: { path: { trigger_id: t.id } } });
    if (take(next, error)) toast(`${t.name} выполнен.`);
  }
  async function reset(t: Trigger) {
    const { data: next, error } = await api.POST("/studio/api/world/state/triggers/{trigger_id}/reset", { params: { path: { trigger_id: t.id } } });
    if (take(next, error)) toast(`${t.name} снова ждёт своего условия.`);
  }
  async function dropTrigger(t: Trigger) {
    if (!(await ask(`Удалить триггер ${t.name}?`, "Мир перестанет реагировать на его условие."))) return;
    const { data: next, error } = await api.DELETE("/studio/api/world/state/triggers/{trigger_id}", { params: { path: { trigger_id: t.id } } });
    take(next, error);
  }
  const describe = (a: Act) => summary(a);
  function triggerState(t: Trigger) {
    if (!t.active) return { text: "выключен", cls: "off" };
    if (t.fired_count && !t.repeat) return { text: `сработал ${when(t.fired_at)}`, cls: "done" };
    if (t.fired_count) return { text: `срабатывал ${t.fired_count} раз, последний ${when(t.fired_at)}`, cls: "done" };
    return { text: t.was_true ? "условие верно" : "ждёт условия", cls: "wait" };
  }

  // ---------- таблица переменных ----------
  type Use = { id: number; title: string };
  let uses = $state<Record<string, Use[]>>({});                      // где имя встречается в сценариях (грузится один раз)
  let query = $state("");
  let varForm = $state<{ type: "flag" | "counter"; name: string; label: string } | null>(null);
  let editing = $state<{ name: string; value: number } | null>(null);
  let said = $state("");
  onMount(() => { api.GET("/studio/api/world/state/uses").then(({ data: found }) => { if (found) uses = found; }); });

  type Row = { kind: "flag" | "counter"; name: string; label: string; flag?: Schemas["WsFlag"]; counter?: Counter };
  const rows = $derived<Row[]>(
    data
      ? [...data.flags.map((f): Row => ({ kind: "flag", name: f.name, label: f.label, flag: f })), ...data.counters.map((c): Row => ({ kind: "counter", name: c.name, label: c.label, counter: c }))]
          .filter((r) => !query.trim() || `${r.name} ${r.label}`.toLowerCase().includes(query.trim().toLowerCase()))
          .sort((a, b) => a.name.localeCompare(b.name))
      : [],
  );
  async function createVar() {
    if (!varForm) return;
    busy = true;
    const body = { name: varForm.name, label: varForm.label };
    const { data: next, error } = varForm.type === "flag"
      ? await api.POST("/studio/api/world/state/flags", { body: { ...body, on: false } })
      : await api.POST("/studio/api/world/state/counters", { body });
    busy = false;
    if (take(next, error)) { said = `world:${varForm.name} добавлена`; varForm = null; }
  }
  async function commitEdit() {
    if (!editing) return;
    const { data: next, error } = await api.POST("/studio/api/world/state/counters/{name}/set", { params: { path: { name: editing.name } }, body: { value: Math.trunc(Number(editing.value) || 0) } });
    if (take(next, error)) { said = `world:${editing.name}: значение задано`; editing = null; }
  }
  const focusOnMount = (el: HTMLInputElement) => { el.focus(); el.select(); };
  const place = (list: Use[] | undefined) => (list ?? []);
</script>

<PageHead title="Состояние мира">
  {#snippet sub()}Метки и счётчики мира, одни на всех игроков. В условиях пишутся как <code>world:core-online</code> и <code>world:fragments&gt;=7</code>.{/snippet}
  {#if data && data.flags.length + data.counters.length > 6}
    <label class="find"><Icon name="search" size={14} /><input placeholder="Найти переменную" bind:value={query} aria-label="Найти переменную" /></label>
  {/if}
  <button class="btn primary" onclick={() => (varForm = { type: "flag", name: "", label: "" })}>+ Переменная</button>
</PageHead>

<p class="sr" aria-live="polite" role="status">{said}</p>

{#if data}
  <section class="block" aria-labelledby="h-vars">
    <h2 id="h-vars">Переменные <span class="count">{rows.length}</span></h2>
    {#if rows.length}
      <div class="tablewrap">
        <table class="grid">
          <thead><tr><th scope="col">Имя</th><th scope="col">Значение</th><th scope="col">Пороги</th><th scope="col">В сценариях</th><th scope="col"><span class="sr">Действия</span></th></tr></thead>
          <tbody>
            {#each rows as r (r.kind + ":" + r.name)}
              <tr>
                <td class="name">
                  <code>world:{r.name}</code>
                  <span class="muted small">{r.kind === "flag" ? "метка" : "счётчик"}{r.label ? ` · ${r.label}` : ""}</span>
                </td>
                <td class="value">
                  {#if r.flag}
                    {@const f = r.flag}
                    <Switch checked={f.on} label={f.on ? "стоит" : "снята"} onchange={(next) => setFlag(f.name, next, f.label)} />
                    {#if f.changed_at}<span class="muted small" title="{f.changed_by}">{when(f.changed_at)}</span>{/if}
                  {:else if r.counter}
                    {@const c = r.counter}
                    <span class="stepper">
                      <button class="btn ghost" onclick={() => bump(c.name, -1)} aria-label="Уменьшить world:{c.name} на 1"><Icon name="minus" size={14} /></button>
                      {#if editing?.name === c.name}
                        <input class="field num" type="number" bind:value={editing.value} use:focusOnMount aria-label="Значение world:{c.name}"
                               onkeydown={(e) => { if (e.key === "Enter") commitEdit(); else if (e.key === "Escape") editing = null; }} onblur={() => (editing = null)} />
                      {:else}
                        <button class="numbtn" onclick={() => (editing = { name: c.name, value: c.value })} title="Задать значение" aria-label="world:{c.name} = {c.value}. Задать значение">{c.value}</button>
                      {/if}
                      <button class="btn ghost" onclick={() => bump(c.name, 1)} aria-label="Увеличить world:{c.name} на 1"><Icon name="plus" size={14} /></button>
                    </span>
                    {#if c.labels[String(c.value)]}<span class="vlabel">{c.labels[String(c.value)]}</span>{/if}
                  {/if}
                </td>
                <td class="thr">
                  {#if r.counter && r.counter.thresholds.length}
                    {#each r.counter.thresholds as t (t.op + t.value + t.trigger)}<span class="chip" class:hit={r.counter.value >= t.value} title="Триггер {t.trigger}">{t.op}{t.value} → {t.trigger}</span>{/each}
                  {:else}<span class="muted">—</span>{/if}
                </td>
                <td class="uses">
                  {#each place(uses[r.name]).slice(0, 2) as u (u.id)}<a class="chip link" href="#/world/scenario/{u.id}/flow">{u.title}</a>{/each}
                  {#if place(uses[r.name]).length > 2}<span class="muted small" title={place(uses[r.name]).slice(2).map((u) => u.title).join(", ")}>+{place(uses[r.name]).length - 2}</span>{/if}
                  {#if !place(uses[r.name]).length}<span class="muted" title="Ни один сценарий не называет эту переменную">—</span>{/if}
                </td>
                <td class="acts">
                  {#if r.counter}<button class="btn ghost" onclick={() => openLabels(r.counter!)} aria-label="Подписи значений world:{r.name}" title="Подписи значений: акты, уровни тревоги"><Icon name="pencil" size={14} /></button>{/if}
                  <button class="btn ghost danger" onclick={() => (r.flag ? dropFlag(r.name) : dropCounter(r.name))} aria-label="Удалить world:{r.name}" title="Удалить"><Icon name="trash" size={14} /></button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if query}
      <p class="muted small">Ничего не нашлось по «{query}».</p>
    {:else}
      <p class="muted small">Переменных пока нет. Метка — да или нет («дверь открыта»), счётчик — число («собрано фрагментов»).</p>
    {/if}
  </section>

  <section class="block" aria-labelledby="h-triggers">
    <div class="bhead"><h2 id="h-triggers">Триггеры <span class="count">{data.triggers.length}</span></h2><button class="btn" onclick={() => editTrigger(null)}>+ Триггер</button></div>
    {#if data.triggers.length}
      <div class="tablewrap">
        <table class="grid">
          <thead><tr><th scope="col">Имя</th><th scope="col">Когда</th><th scope="col">Что делает</th><th scope="col">Состояние</th><th scope="col"><span class="sr">Действия</span></th></tr></thead>
          <tbody>
            {#each data.triggers as t (t.id)}
              {@const st = triggerState(t)}
              <tr class:off={!t.active}>
                <td class="name"><code>{t.name}</code>{#if t.label}<span class="muted small">{t.label}</span>{/if}{#if t.repeat}<span class="muted small">повторный</span>{/if}</td>
                <td><code class="cond">{t.condition_text}</code></td>
                <td class="small">{(t.actions as Act[]).map(describe).join(", ")}</td>
                <td><span class="state {st.cls}">{st.text}</span></td>
                <td class="acts">
                  <button class="btn ghost" onclick={() => editTrigger(t)} aria-label="Изменить триггер {t.name}" title="Изменить"><Icon name="pencil" size={14} /></button>
                  <button class="btn ghost" onclick={() => fire(t)} aria-label="Запустить {t.name} сейчас" title="Запустить сейчас"><Icon name="zap" size={14} /></button>
                  {#if t.fired_count && !t.repeat}<button class="btn ghost" onclick={() => reset(t)} aria-label="Сбросить {t.name}" title="Сработает ещё раз, когда условие снова станет верным"><Icon name="redo" size={14} /></button>{/if}
                  <button class="btn ghost danger" onclick={() => dropTrigger(t)} aria-label="Удалить триггер {t.name}" title="Удалить"><Icon name="trash" size={14} /></button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}<p class="muted small">Триггеров нет: мир меняется только руками.</p>{/if}
  </section>

  <section class="block" aria-labelledby="h-moments">
    <div class="bhead"><h2 id="h-moments">Моменты <span class="count">{data.moments.length}</span></h2><button class="btn" onclick={() => editMoment(null)}>+ Момент</button></div>
    <p class="muted small">Событие в игровом времени. Пока идёт, стоит метка <code>world:имя</code>: на неё открываются ноды и файлы, а триггер с условием <code>world:имя</code> срабатывает на начале.</p>
    {#if data.moments.length}
      <div class="tablewrap">
        <table class="grid">
          <thead><tr><th scope="col">Имя</th><th scope="col">Когда</th><th scope="col">Состояние</th><th scope="col">Видят</th><th scope="col"><span class="sr">Действия</span></th></tr></thead>
          <tbody>
            {#each data.moments as m (m.id)}
              <tr class:off={!m.active}>
                <td class="name"><code>{m.name}</code>{#if m.title}<span class="muted small">{m.title}</span>{/if}</td>
                <td class="small">{m.summary || m.schedule} · {m.duration} мин{m.time_zone !== "UTC" ? ` · ${m.time_zone}` : ""}</td>
                <td><span class="state" class:live={m.running} class:wait={!m.running}>{m.running ? `идёт до ${inZone(m.ends_at, m.time_zone)}` : m.next_at ? `${inZone(m.next_at, m.time_zone)} · ${until(m.next_real)}` : "больше не наступит"}</span></td>
                <td class="small muted">{audience(m)}</td>
                <td class="acts">
                  <button class="btn ghost" onclick={() => startStop(m)} aria-label="{m.running ? 'Закончить' : 'Начать'} момент {m.name}" title={m.running ? "Закончить" : "Начать сейчас"}><Icon name={m.running ? "stop" : "run"} size={14} /></button>
                  <button class="btn ghost" onclick={() => editMoment(m)} aria-label="Изменить момент {m.name}" title="Изменить"><Icon name="pencil" size={14} /></button>
                  <button class="btn ghost danger" onclick={() => dropMoment(m)} aria-label="Удалить момент {m.name}" title="Удалить"><Icon name="trash" size={14} /></button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}<p class="muted small">Моментов нет.</p>{/if}
  </section>

  <details class="block log">
    <summary><h2>Журнал мира</h2></summary>
    <ol>
      {#each data.events as e}<li><span class="muted small mono">{when(e.at)}</span><span>{e.text}</span><span class="muted small">{e.source}</span></li>
      {:else}<li class="muted small">Пока ничего не происходило.</li>{/each}
    </ol>
  </details>
{:else}<p class="muted pad">Загрузка…</p>{/if}

{#if varForm}
  <Dialog title="Новая переменная" confirm="Добавить" {busy} disabled={!varForm.name.trim()} onsubmit={createVar} onclose={() => (varForm = null)}>
    <div class="form">
      <fieldset class="kinds"><legend class="label">Что это</legend>
        <label class="check"><input type="radio" bind:group={varForm.type} value="flag" /> Метка: да или нет («дверь открыта»)</label>
        <label class="check"><input type="radio" bind:group={varForm.type} value="counter" /> Счётчик: число («собрано фрагментов»)</label>
      </fieldset>
      <label><span class="label">Имя</span><input class="field mono" bind:value={varForm.name} placeholder={varForm.type === "flag" ? "core-online" : "fragments"} /></label>
      <label><span class="label">Подпись для авторов</span><input class="field" bind:value={varForm.label} /></label>
    </div>
  </Dialog>
{/if}

{#if labeling}
  <Dialog title="Подписи значений world:{labeling.name}" confirm="Сохранить" onsubmit={saveLabels} onclose={() => (labeling = null)}>
    <textarea class="field mono" rows="6" bind:value={labeling.text} placeholder={"1 = Тишина\n2 = Архив\n3 = Буря"}></textarea>
    <p class="muted small">По строке: число = подпись. Так счётчик <code>act</code> становится актами: на пульте видно «2 · Архив», а контент акта открывается условием <code>world:act&gt;=2</code>.</p>
  </Dialog>
{/if}

{#if mform}
  <Dialog wide title={mform.id !== null ? `Момент ${mform.name}` : "Новый момент"} confirm="Сохранить" {busy}
    disabled={!mform.name.trim() || !mform.schedule.trim()} onsubmit={saveMoment} onclose={() => (mform = null)}>
    <div class="form">
      <div class="two">
        <label><span class="label">Имя (метка мира)</span><input class="field mono" bind:value={mform.name} placeholder="boreas-online" /></label>
        <label><span class="label">Название для игроков</span><input class="field mono" bind:value={mform.title} placeholder="BOREAS UPLINK" /></label>
      </div>
      <label><span class="label">Подпись для авторов</span><input class="field" bind:value={mform.label} /></label>
      <div class="two">
        <label><span class="label">Когда (игровое время)</span><textarea class="field mono" rows="2" bind:value={mform.schedule}></textarea>
          <span class="muted small"><code>once 2031-03-01 21:00</code> · <code>daily 21:00</code> · <code>mon,fri 22:00</code></span></label>
        <div class="col2">
          <label><span class="label">Часовой пояс</span><input class="field mono" list="moment-zones" bind:value={mform.time_zone} /></label>
          <label><span class="label">Длится, минут</span><input class="field mono" type="number" min="1" bind:value={mform.duration} /></label>
        </div>
      </div>
      <datalist id="moment-zones">{#each ZONES as zone}<option value={zone}></option>{/each}</datalist>
      <div class="shownin">
        <span class="label">Где видят игроки</span>
        <label class="check"><input type="checkbox" bind:checked={mform.in_list} /> В <code>at</code> и в <code>{"{next_event}"}</code> приветствия</label>
        <label class="check"><input type="checkbox" bind:checked={mform.ticker} /> Бегущая строка на столе: до начала и пока идёт</label>
        <label class="check"><input type="checkbox" bind:checked={mform.toast} /> Жёлтое уведомление: «скоро» и в момент начала</label>
      </div>
      {#if mform.in_list || mform.ticker || mform.toast}
        <div class="two">
          <label><span class="label">Предупреждать за, минут<Hint text="Когда появляются бегущая строка и уведомление «скоро». 0 — только в момент начала." /></span><input class="field mono" type="number" min="0" bind:value={mform.warn} /></label>
          <label><span class="label">Кому виден (условие)</span><input class="field mono" bind:value={mform.condition_text} placeholder="всем; или uplink-key and world:act>=2" /></label>
        </div>
        <div class="three">
          <label><span class="label">Только ОС</span><input class="field mono" bind:value={mform.systems} placeholder="AETHER, VMS" /></label>
          <label><span class="label">Только машины</span><input class="field mono" bind:value={mform.machines} placeholder="aether-main" /></label>
          <label><span class="label">Только группы учётки</span><input class="field mono" bind:value={mform.groups} placeholder="ops, radio" /></label>
        </div>
      {/if}
      <label class="check"><input type="checkbox" bind:checked={mform.active} /> Включён</label>
    </div>
  </Dialog>
{/if}

{#if tform}
  <Dialog wide title={tform.id !== null ? `Триггер ${tform.name}` : "Новый триггер"} confirm="Сохранить" {busy}
    disabled={!tform.name.trim() || !tform.condition_text.trim() || !tform.actions.length} onsubmit={saveTrigger} onclose={() => (tform = null)}>
    <div class="form">
      <div class="two">
        <label><span class="label">Имя</span><input class="field mono" bind:value={tform.name} placeholder="act-2" /></label>
        <label><span class="label">Подпись для авторов</span><input class="field" bind:value={tform.label} placeholder="переход во второй акт" /></label>
      </div>
      <label><span class="label">Когда<Hint text="Условие на мир: world:метка, world:счётчик>=число (>=, >, <=, <, =), and, or, not и скобки. Срабатывает, когда условие из неверного становится верным." /></span>
        <input class="field mono" bind:value={tform.condition_text} placeholder="world:fragments>=7 and not world:sealed" /></label>
      <div><span class="label">Что сделать</span>
        <ActionsEditor bind:actions={tform.actions} provides={["world"]} />
      </div>
      <div class="two">
        <label class="check"><input type="checkbox" bind:checked={tform.repeat} /> Повторный: каждый раз, когда условие снова станет верным</label>
        <label class="check"><input type="checkbox" bind:checked={tform.active} /> Включён</label>
      </div>
    </div>
  </Dialog>
{/if}


<style>
  .block { margin: 12px 32px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .bhead { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  h2 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .count { margin-left: 4px; padding: 0 7px; border-radius: 999px; background: var(--raise); color: var(--text); font-size: 11px; letter-spacing: 0; }
  .small { font-size: 12px; }
  .mono { font-family: var(--mono); }
  code { font-family: var(--mono); font-size: 12.5px; }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .find { display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; height: 32px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel); color: var(--muted); }
  .find input { border: 0; background: transparent; color: var(--text); outline: none; width: 150px; font: inherit; }
  .find:focus-within { border-color: var(--accent); }

  .tablewrap { overflow-x: auto; }
  table.grid { width: 100%; border-collapse: collapse; font-size: 13px; }
  .grid th { text-align: left; padding: 4px 10px 6px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
  .grid td { padding: 6px 10px; border-bottom: 1px solid var(--line-soft); vertical-align: middle; }
  .grid tr:last-child td { border-bottom: 0; }
  .grid tbody tr:hover { background: var(--panel-2); }
  .grid tr.off { opacity: 0.6; }
  .name { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 8px; min-width: 190px; }
  .name code { color: var(--text); font-weight: 600; }
  .value { white-space: nowrap; }
  .value :global(.switch) { vertical-align: middle; }
  .stepper { display: inline-flex; align-items: center; gap: 2px; vertical-align: middle; }
  .stepper .btn { height: 28px; width: 28px; padding: 0; justify-content: center; }
  .numbtn { min-width: 44px; height: 28px; padding: 0 6px; border: 1px solid transparent; border-radius: var(--radius-s); background: transparent; color: var(--text); font: inherit; font-family: var(--mono); font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; cursor: text; text-align: center; }
  .numbtn:hover { border-color: var(--line); background: var(--panel-2); }
  .field.num { width: 64px; height: 28px; padding: 0 6px; text-align: center; font-family: var(--mono); }
  .vlabel { margin-left: 8px; font-size: 12px; color: var(--accent); }
  .thr, .uses { max-width: 280px; }
  .chip { display: inline-block; margin: 1px 4px 1px 0; padding: 0 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11.5px; line-height: 19px; white-space: nowrap; }
  .chip.hit { color: var(--ok, #4cc38a); }
  .chip.link { color: var(--text); text-decoration: none; }
  .chip.link:hover { background: var(--panel-2); text-decoration: underline; }
  .acts { white-space: nowrap; text-align: right; }
  .acts .btn { height: 28px; padding: 0 7px; }
  .cond { white-space: normal; overflow-wrap: anywhere; }
  .state { display: inline-block; padding: 0 8px; border-radius: 999px; font-size: 11.5px; line-height: 19px; background: var(--raise); color: var(--muted); white-space: nowrap; }
  .state.done { background: color-mix(in srgb, var(--ok, #4cc38a) 15%, transparent); color: var(--ok, #4cc38a); }
  .state.wait { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
  .state.live { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }

  details.log summary { cursor: pointer; list-style: none; }
  details.log summary h2 { display: inline; }
  details.log summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
  details.log ol { list-style: none; margin: 10px 0 0; padding: 0; max-height: 320px; overflow: auto; display: flex; flex-direction: column; }
  details.log li { display: grid; grid-template-columns: 12ch minmax(0, 1fr) minmax(0, auto); gap: 12px; padding: 4px 0; border-bottom: 1px solid var(--line-soft); font-size: 13px; }

  .form { display: flex; flex-direction: column; gap: 12px; }
  .form label { display: flex; flex-direction: column; gap: 4px; }
  .kinds { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .label { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
  .three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .col2 { display: flex; flex-direction: column; gap: 10px; }
  .shownin { display: flex; flex-direction: column; gap: 6px; }
  .check { flex-direction: row !important; align-items: center; gap: 8px !important; font-size: 13px; }
  .check input { width: auto; }
  textarea { resize: vertical; font: inherit; }
  .pad { padding: 24px 32px; }
  @media (max-width: 720px) { .block { margin-left: 16px; margin-right: 16px; } }
</style>
