<script lang="ts">
  // Пульт мира: мировые метки, счётчики с вкладами и порогами, триггеры, журнал. Одно состояние на всех игроков.
  // Логика в world/state.py; здесь показ и кнопки автора.
  import { onDestroy, onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Hint from "../lib/Hint.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { toast } from "../lib/toast.svelte";

  type State = Schemas["WsState"];
  type Counter = Schemas["WsCounter"];
  type Trigger = Schemas["WsTrigger"];
  type Act = { do: string; name?: string; delta?: number; title?: string; text?: string; station?: string; freq?: string; key?: string; important?: boolean; item?: string; systems?: string; machines?: string; section?: number | string; mode?: string; character?: string };
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
  let flagForm = $state({ name: "", label: "" });
  async function setFlag(name: string, on: boolean, label = "") {
    const { data: next, error } = await api.POST("/studio/api/world/state/flags", { body: { name, label, on } });
    if (take(next, error)) toast(on ? `world:${name} поставлена.` : `world:${name} снята.`);
  }
  async function addFlag() {
    const { data: next, error } = await api.POST("/studio/api/world/state/flags", { body: { ...flagForm, on: false } });
    if (take(next, error)) flagForm = { name: "", label: "" };
  }
  async function dropFlag(name: string) {
    if (!(await ask(`Удалить world:${name}?`, "Условия с этой меткой станут неверными."))) return;
    const { data: next, error } = await api.DELETE("/studio/api/world/state/flags/{name}", { params: { path: { name } } });
    take(next, error);
  }

  // ---------- счётчики ----------
  let counterForm = $state({ name: "", label: "", mode: "sum" });
  let setting = $state<{ name: string; value: number } | null>(null);
  async function addCounter() {
    const { data: next, error } = await api.POST("/studio/api/world/state/counters", { body: counterForm });
    if (take(next, error)) counterForm = { name: "", label: "", mode: "sum" };
  }
  async function bump(name: string, value: number) {
    const { data: next, error } = await api.POST("/studio/api/world/state/counters/{name}/add", { params: { path: { name } }, body: { value } });
    take(next, error);
  }
  async function setValue() {
    if (!setting) return;
    const { data: next, error } = await api.POST("/studio/api/world/state/counters/{name}/set", { params: { path: { name: setting.name } }, body: { value: setting.value } });
    if (take(next, error)) setting = null;
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
  function scale(c: Counter) {
    const top = Math.max(c.value, ...c.thresholds.map((t) => t.value), 1);
    return (v: number) => Math.max(0, Math.min(100, (v / (top * 1.08)) * 100));
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
  const KINDS = [
    { value: "flag", label: "Поставить метку мира" }, { value: "unflag", label: "Снять метку мира" }, { value: "count", label: "Вклад в счётчик" },
    { value: "news", label: "Опубликовать новость" }, { value: "air", label: "Передать в эфир" }, { value: "letter", label: "Письмо всем" },
    { value: "forum", label: "Запись на форуме" },
  ];
  let forumOptions = $state<Schemas["WsForumOptions"]>({ sections: [], characters: [] });
  onMount(async () => { const { data: found } = await api.GET("/studio/api/world/state/forum-options"); if (found) forumOptions = found; });
  const sectionLabel = (id: unknown) => forumOptions.sections.find((s) => s.id === String(id))?.label ?? `раздел ${id}`;
  function editTrigger(t: Trigger | null) {
    tform = t ? { id: t.id, name: t.name, label: t.label, condition_text: t.condition_text, actions: (t.actions as Act[]).map((a) => ({ ...a })), repeat: t.repeat, active: t.active }
              : { id: null, name: "", label: "", condition_text: "", actions: [{ do: "flag", name: "" }], repeat: false, active: true };
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
  function describe(a: Act) {
    switch (a.do) {
      case "flag": return `поставить world:${a.name}`;
      case "unflag": return `снять world:${a.name}`;
      case "count": return `world:${a.name} ${(a.delta ?? 1) >= 0 ? "+" : ""}${a.delta ?? 1}`;
      case "news": return `новость «${a.title}»`;
      case "air": return `${(a.station ?? "").toUpperCase()} в эфир ${a.freq}${a.key ? " шифром" : ""}`;
      case "letter": return `письмо всем «${a.item}»${a.machines ? ` на ${a.machines}` : ""}${a.systems ? ` (ОС ${a.systems})` : ""}`;
      case "forum": return `${a.character || "SYS"} ${a.mode === "append" ? "дописывает в" : "открывает тему"} «${a.title}» · ${sectionLabel(a.section)}`;
      default: return a.do;
    }
  }
  function triggerState(t: Trigger) {
    if (!t.active) return { text: "выключен", cls: "off" };
    if (t.fired_count && !t.repeat) return { text: `сработал ${when(t.fired_at)}`, cls: "done" };
    if (t.fired_count) return { text: `срабатывал ${t.fired_count} раз, последний ${when(t.fired_at)}`, cls: "done" };
    return { text: t.was_true ? "условие верно" : "ждёт условия", cls: "wait" };
  }
</script>

<PageHead title="Состояние мира">
  {#snippet sub()}Метки и счётчики, одни на всех игроков. В любом условии пишутся как <code>world:core-online</code> и <code>world:fragments&gt;=7</code>. Триггеры следят за ними и меняют мир.{/snippet}
</PageHead>

{#if data}
  <div class="grid">
    <section class="card">
      <div class="bhead"><h2>Метки</h2></div>
      <ul class="flags">
        {#each data.flags as f (f.name)}
          <li class:on={f.on}>
            <button class="switch" role="switch" aria-checked={f.on} onclick={() => setFlag(f.name, !f.on, f.label)} aria-label="{f.on ? 'Снять' : 'Поставить'} world:{f.name}"><span></span></button>
            <div class="who"><b class="mono">world:{f.name}</b>{#if f.label}<span class="muted small">{f.label}</span>{/if}
              {#if f.changed_at}<span class="muted small">{f.on ? "поставлена" : "снята"} {when(f.changed_at)}{f.changed_by ? ` · ${f.changed_by}` : ""}</span>{/if}</div>
            <button class="x" onclick={() => dropFlag(f.name)} title="Удалить метку" aria-label="Удалить метку">✕</button>
          </li>
        {:else}<li class="muted small empty">Меток пока нет.</li>{/each}
      </ul>
      <form class="add" onsubmit={(e) => { e.preventDefault(); addFlag(); }}>
        <input class="field mono" placeholder="имя: core-online" bind:value={flagForm.name} aria-label="Имя метки" />
        <input class="field" placeholder="подпись для авторов" bind:value={flagForm.label} aria-label="Подпись" />
        <button class="btn" disabled={!flagForm.name.trim()}>+ Метка</button>
      </form>
    </section>

    <section class="card">
      <div class="bhead"><h2>Счётчики</h2></div>
      {#each data.counters as c (c.name)}
        {@const x = scale(c)}
        <div class="counter">
          <div class="ctop">
            <div class="who"><b class="mono">world:{c.name}</b>{#if c.label}<span class="muted small">{c.label}</span>{/if}
              <span class="muted small">{c.mode === "players" ? `каждый игрок один раз · вложились ${c.players}` : "сумма вкладов"}</span></div>
            <div class="value"><span class="mono">{c.value}</span>{#if c.labels[String(c.value)]}<span class="vlabel">{c.labels[String(c.value)]}</span>{/if}</div>
          </div>
          <div class="bar" aria-hidden="true">
            <div class="fill" style="width:{x(c.value)}%"></div>
            {#each c.thresholds as t}<span class="mark" class:passed={c.value >= t.value} style="left:{x(t.value)}%" title="{t.op}{t.value}: триггер {t.trigger}"><i>{t.value}</i></span>{/each}
          </div>
          {#if c.thresholds.length}<div class="muted small">пороги: {c.thresholds.map((t) => `${t.op}${t.value} → ${t.trigger}`).join(" · ")}</div>{/if}
          <div class="crow">
            <div class="btns">
              <button class="btn small" onclick={() => bump(c.name, -1)}>−1</button>
              <button class="btn small" onclick={() => bump(c.name, 1)}>+1</button>
              <button class="btn ghost small" onclick={() => (setting = { name: c.name, value: c.value })}>Задать…</button>
              <button class="btn ghost small" onclick={() => openLabels(c)} title="Подписи значений: акты, уровни тревоги">Подписи…</button>
            </div>
            <button class="x" onclick={() => dropCounter(c.name)} title="Удалить счётчик" aria-label="Удалить счётчик">✕</button>
          </div>
          {#if c.recent.length}
            <ul class="recent">
              {#each c.recent as r}<li><span class="mono">{r.delta >= 0 ? "+" : ""}{r.delta}</span><span>{r.who || r.source || "—"}</span><span class="muted small">{r.who && r.source ? r.source + " · " : ""}{when(r.at)}</span></li>{/each}
            </ul>
          {/if}
        </div>
      {:else}<p class="muted small empty">Счётчиков пока нет.</p>{/each}
      <form class="add" onsubmit={(e) => { e.preventDefault(); addCounter(); }}>
        <input class="field mono" placeholder="имя: fragments" bind:value={counterForm.name} aria-label="Имя счётчика" />
        <input class="field" placeholder="подпись для авторов" bind:value={counterForm.label} aria-label="Подпись" />
        <select class="field mode" bind:value={counterForm.mode} aria-label="Как считать"><option value="sum">сумма вкладов</option><option value="players">каждый игрок один раз</option></select>
        <button class="btn" disabled={!counterForm.name.trim()}>+ Счётчик</button>
      </form>
    </section>
  </div>

  <section class="card wide">
    <div class="bhead"><h2>Моменты</h2><button class="btn" onclick={() => editMoment(null)}>+ Момент</button></div>
    <p class="muted small">Событие в игровом времени. Пока идёт, стоит метка <code>world:имя</code>: на неё открываются узлы и файлы, а триггер с условием <code>world:имя</code> срабатывает на начале, с <code>not world:имя</code> — на конце.</p>
    {#each data.moments as m (m.id)}
      <div class="trigger" class:off={!m.active}>
        <div class="tmain">
          <div class="line1"><b class="mono">{m.name}</b>{#if m.title}<span> · {m.title}</span>{/if}{#if m.label}<span class="muted"> · {m.label}</span>{/if}
            {#if m.in_list || m.ticker || m.toast}<span class="badge">{[m.in_list ? "at" : "", m.ticker ? "строка" : "", m.toast ? "уведомление" : ""].filter(Boolean).join(" · ")}{(m.ticker || m.toast) && m.warn ? `, за ${m.warn} мин` : ""}</span>{:else}<span class="badge">скрытый</span>{/if}
            <span class="state" class:live={m.running} class:wait={!m.running}>{m.running ? `идёт до ${inZone(m.ends_at, m.time_zone)}` : m.next_at ? `${inZone(m.next_at, m.time_zone)} · ${until(m.next_real)}` : "больше не наступит"}</span></div>
          <div class="muted small">{m.summary || m.schedule} · {m.duration} мин{m.time_zone !== "UTC" ? ` · ${m.time_zone}` : ""} · видят: {audience(m)}</div>
        </div>
        <div class="tacts">
          <button class="btn ghost small" onclick={() => startStop(m)}>{m.running ? "Закончить" : "Начать сейчас"}</button>
          <button class="btn ghost small" onclick={() => editMoment(m)}>Изменить</button>
          <button class="btn ghost small danger" onclick={() => dropMoment(m)}>Удалить</button>
        </div>
      </div>
    {:else}<p class="muted small empty">Моментов нет.</p>{/each}
  </section>

  <section class="card wide">
    <div class="bhead"><h2>Триггеры</h2><button class="btn" onclick={() => editTrigger(null)}>+ Триггер</button></div>
    {#each data.triggers as t (t.id)}
      {@const st = triggerState(t)}
      <div class="trigger" class:off={!t.active}>
        <div class="tmain">
          <div class="line1"><b class="mono">{t.name}</b>{#if t.label}<span class="muted"> · {t.label}</span>{/if}{#if t.repeat}<span class="badge">повторный</span>{/if}<span class="state {st.cls}">{st.text}</span></div>
          <div class="cond">когда <code>{t.condition_text}</code></div>
          <div class="muted small">→ {(t.actions as Act[]).map(describe).join(", ")}</div>
        </div>
        <div class="tacts">
          <button class="btn ghost small" onclick={() => editTrigger(t)}>Изменить</button>
          <button class="btn ghost small" onclick={() => fire(t)}>Запустить сейчас</button>
          {#if t.fired_count && !t.repeat}<button class="btn ghost small" onclick={() => reset(t)} title="Сработает ещё раз, когда условие снова станет верным">Сбросить</button>{/if}
          <button class="btn ghost small danger" onclick={() => dropTrigger(t)}>Удалить</button>
        </div>
      </div>
    {:else}<p class="muted small empty">Триггеров нет: мир меняется только руками.</p>{/each}
  </section>

  <section class="card wide">
    <div class="bhead"><h2>Журнал мира</h2></div>
    <ol class="log">
      {#each data.events as e}<li><span class="muted small mono">{when(e.at)}</span><span>{e.text}</span><span class="muted small">{e.source}</span></li>
      {:else}<li class="muted small">Пока ничего не происходило.</li>{/each}
    </ol>
  </section>
{:else}<p class="muted pad">Загрузка…</p>{/if}

{#if labeling}
  <Dialog title="Подписи значений world:{labeling.name}" confirm="Сохранить" onsubmit={saveLabels} onclose={() => (labeling = null)}>
    <textarea class="field mono" rows="6" bind:value={labeling.text} placeholder={"1 = Тишина\n2 = Архив\n3 = Буря"}></textarea>
    <p class="muted small">По строке: число = подпись. Так счётчик <code>act</code> становится актами: на пульте видно «2 · Архив», а контент акта открывается условием <code>world:act&gt;=2</code>.</p>
  </Dialog>
{/if}

{#if setting}
  <Dialog title="Задать world:{setting.name}" confirm="Задать" onsubmit={setValue} onclose={() => (setting = null)}>
    <input class="field mono" type="number" bind:value={setting.value} aria-label="Значение" />
    <p class="muted small">Запишется вкладом автора на разницу. Триггеры проверятся сразу.</p>
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
        <div class="acts-list">
          {#each tform.actions as a, i}
            <div class="act">
              <select class="field kind" bind:value={a.do} aria-label="Действие">{#each KINDS as k}<option value={k.value}>{k.label}</option>{/each}</select>
              {#if a.do === "flag" || a.do === "unflag"}
                <input class="field mono" bind:value={a.name} placeholder="метка" aria-label="Метка" />
              {:else if a.do === "count"}
                <input class="field mono" bind:value={a.name} placeholder="счётчик" aria-label="Счётчик" />
                <input class="field mono num" type="number" bind:value={a.delta} placeholder="1" aria-label="Сколько" />
              {:else if a.do === "news"}
                <div class="stack">
                  <input class="field" bind:value={a.title} placeholder="Заголовок" aria-label="Заголовок" />
                  <textarea class="field" rows="2" bind:value={a.text} placeholder="Текст новости" aria-label="Текст"></textarea>
                  <label class="check"><input type="checkbox" bind:checked={a.important} /> Важная: всплывает на столе</label>
                </div>
              {:else if a.do === "letter"}
                <div class="stack">
                  <input class="field mono" bind:value={a.item} placeholder="слаг объекта письма (.msg)" aria-label="Письмо" />
                  <div class="row"><input class="field mono" bind:value={a.machines} placeholder="только машины: aether-main, …" aria-label="Машины" />
                    <input class="field mono" bind:value={a.systems} placeholder="только ОС: AETHER, …" aria-label="ОС" /></div>
                  <span class="muted small">Придёт каждому игроку один раз, когда он откроет почту на подходящей машине.</span>
                </div>
              {:else if a.do === "forum"}
                <div class="stack">
                  <div class="row">
                    <select class="field" bind:value={a.section} aria-label="Раздел">
                      <option value={undefined} disabled>раздел форума…</option>
                      {#each forumOptions.sections as s (s.id)}<option value={Number(s.id)}>{s.label}</option>{/each}
                    </select>
                    <select class="field" bind:value={a.character} aria-label="От кого">
                      <option value={undefined}>от системы (SYS)</option>
                      {#each forumOptions.characters as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
                    </select>
                  </div>
                  <div class="row">
                    <select class="field" bind:value={a.mode} aria-label="Режим">
                      <option value={undefined}>новая тема</option><option value="append">дописать в тему</option>
                    </select>
                    <input class="field" bind:value={a.title} placeholder={a.mode === "append" ? "заголовок темы, например World log" : "заголовок новой темы"} aria-label="Заголовок" />
                  </div>
                  <textarea class="field" rows="2" bind:value={a.text} placeholder="текст: {'{time}'}, {'{player}'}, {'{world_счётчик}'}" aria-label="Текст"></textarea>
                  <span class="muted small">«Дописать» пишет в последний открытый том темы с этим заголовком (нет такой — создаёт). Хроника — это обычный раздел, куда пишут такие действия.</span>
                </div>
              {:else if a.do === "air"}
                <div class="stack">
                  <div class="row"><input class="field mono" bind:value={a.station} placeholder="СТАНЦИЯ" aria-label="Станция" />
                    <input class="field mono" bind:value={a.freq} placeholder="МГц" aria-label="Частота" />
                    <input class="field mono" bind:value={a.key} placeholder="шифр (необязательно)" aria-label="Шифр" /></div>
                  <input class="field" bind:value={a.text} placeholder="Текст передачи" aria-label="Текст" />
                </div>
              {/if}
              <button type="button" class="x" onclick={() => (tform!.actions = tform!.actions.filter((_, j) => j !== i))} aria-label="Убрать действие">✕</button>
            </div>
          {/each}
          <button type="button" class="btn ghost small add-act" onclick={() => tform!.actions.push({ do: "flag", name: "" })}>+ действие</button>
        </div>
      </div>
      <div class="two">
        <label class="check"><input type="checkbox" bind:checked={tform.repeat} /> Повторный: каждый раз, когда условие снова станет верным</label>
        <label class="check"><input type="checkbox" bind:checked={tform.active} /> Включён</label>
      </div>
    </div>
  </Dialog>
{/if}

<style>
  .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 12px; margin: 12px 32px; align-items: start; }
  .card { padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .card.wide { margin: 12px 32px; }
  .bhead { display: flex; justify-content: space-between; align-items: center; }
  h2 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .small { font-size: 12px; }
  .mono { font-family: var(--mono); }
  code { font-family: var(--mono); font-size: 12.5px; }
  .empty { margin: 0; padding: 4px 0; }
  .who { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .x { border: 0; background: none; color: var(--faint, var(--muted)); cursor: pointer; padding: 0 4px; align-self: flex-start; }
  .x:hover { color: var(--danger); }
  .add { display: flex; gap: 6px; flex-wrap: wrap; padding-top: 8px; border-top: 1px solid var(--line-soft); }
  .add .field { flex: 1; min-width: 120px; }
  .add .mode { flex: 0 0 auto; width: auto; }

  .flags { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .flags li { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 6px 4px; border-radius: var(--radius-s); }
  .flags li.on b { color: var(--accent); }
  .switch { position: relative; width: 34px; height: 18px; border: 1px solid var(--line-soft); border-radius: 999px; background: var(--bg); cursor: pointer; padding: 0; }
  .switch span { position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; border-radius: 50%; background: var(--muted); transition: left 0.12s; }
  .switch[aria-checked="true"] { background: color-mix(in srgb, var(--accent) 30%, transparent); border-color: var(--accent); }
  .switch[aria-checked="true"] span { left: 18px; background: var(--accent); }

  .counter { display: flex; flex-direction: column; gap: 6px; padding: 10px 0; border-bottom: 1px solid var(--line-soft); }
  .ctop { display: flex; justify-content: space-between; gap: 12px; }
  .value { display: flex; flex-direction: column; align-items: flex-end; font-size: 24px; font-weight: 600; }
  .vlabel { font-size: 12px; font-weight: 500; color: var(--accent); }
  .bar { position: relative; height: 8px; margin: 8px 0 14px; border-radius: 999px; background: var(--bg); }
  .fill { position: absolute; inset: 0 auto 0 0; border-radius: 999px; background: var(--accent); }
  .mark { position: absolute; top: -4px; width: 2px; height: 16px; margin-left: -1px; background: var(--muted); }
  .mark.passed { background: var(--ok, #4cc38a); }
  .mark i { position: absolute; top: 16px; left: 50%; transform: translateX(-50%); font-style: normal; font-size: 10px; color: var(--muted); }
  .crow { display: flex; justify-content: space-between; align-items: center; }
  .btns { display: flex; gap: 4px; }
  .recent { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1px; font-size: 12.5px; }
  .recent li { display: grid; grid-template-columns: 4ch minmax(0, auto) minmax(0, 1fr); gap: 8px; align-items: baseline; }

  .trigger { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg); }
  .trigger.off { opacity: 0.6; }
  .tmain { display: flex; flex-direction: column; gap: 3px; min-width: 0; font-size: 13px; }
  .line1 { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
  .badge { padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .state { margin-left: auto; padding: 0 8px; border-radius: 999px; font-size: 11px; background: var(--raise); color: var(--muted); }
  .state.done { background: color-mix(in srgb, var(--ok, #4cc38a) 15%, transparent); color: var(--ok, #4cc38a); }
  .state.wait { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
  .state.live { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }
  .three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
  .col2 { display: flex; flex-direction: column; gap: 10px; }
  .shownin { display: flex; flex-direction: column; gap: 6px; }
  .tacts { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; align-content: flex-start; max-width: 340px; }

  .log { list-style: none; margin: 0; padding: 0; max-height: 320px; overflow: auto; display: flex; flex-direction: column; }
  .log li { display: grid; grid-template-columns: 12ch minmax(0, 1fr) minmax(0, auto); gap: 12px; padding: 4px 0; border-bottom: 1px solid var(--line-soft); font-size: 13px; }

  .form { display: flex; flex-direction: column; gap: 12px; }
  .form label { display: flex; flex-direction: column; gap: 4px; }
  .label { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .check { flex-direction: row !important; align-items: center; gap: 8px !important; font-size: 13px; }
  .check input { width: auto; }
  .acts-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
  .act { display: flex; gap: 6px; align-items: flex-start; padding: 6px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .act .kind { flex: 0 0 200px; width: 200px; }
  .act > .field { flex: 1; min-width: 0; }
  .act .num { flex: 0 0 80px; width: 80px; }
  .stack { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .row { display: flex; gap: 6px; }
  textarea { resize: vertical; font: inherit; }
  .add-act { align-self: flex-start; }
  .pad { padding: 24px 32px; }
  @media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
</style>
