<script lang="ts">
  // Станции эфира: список слева, у выбранной справа передачи по расписанию (игровое время) и ответчики.
  // Логика и проверки в air/events.py и air/schedule.py; здесь формы и показ.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { toast } from "../../lib/toast.svelte";
  import Actions from "../mail/Actions.svelte";
  import type { Action } from "../mail/doc";

  type Station = Schemas["AirStation"];
  type Broadcast = Schemas["AirBroadcast"];
  type Responder = Schemas["AirResponder"];

  let { onchange }: { onchange?: () => void } = $props();

  let stations = $state<Station[]>([]);
  let selected = $state<number | null>(null);
  let broadcasts = $state<Broadcast[]>([]);
  let responders = $state<Responder[]>([]);
  let picks = $state<Schemas["MlPicks"] | null>(null);
  const station = $derived(stations.find((s) => s.id === selected) ?? null);
  const ZONES: string[] = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.("timeZone") ?? ["UTC"];

  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const pad = (n: number) => String(n).padStart(2, "0");
  function game(iso: string | null, zone = "UTC") {
    if (!iso) return "";
    try {
      const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso));
      const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
      return `${get("day")} ${MONTHS[+get("month") - 1]} ${get("year")}, ${get("hour")}:${get("minute")}`;
    } catch { const d = new Date(iso); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`; }
  }
  const cond = (c: unknown) => (typeof c === "string" ? c : c ? JSON.stringify(c) : "");

  async function loadStations() {
    stations = (await api.GET("/studio/api/air/stations")).data ?? [];
    if (selected === null || !stations.some((s) => s.id === selected)) selected = stations[0]?.id ?? null;
  }
  async function loadStation() {
    if (selected === null) { broadcasts = []; responders = []; return; }
    const query = { params: { query: { station: selected } } };
    const [b, r] = await Promise.all([api.GET("/studio/api/air/broadcasts", query), api.GET("/studio/api/air/responders", query)]);
    broadcasts = b.data ?? [];
    responders = r.data ?? [];
  }
  $effect(() => { void selected; loadStation(); });
  onMount(async () => {
    await loadStations();
    picks = (await api.GET("/studio/api/mail/picks", { params: { query: { kind: "key" } } })).data ?? null;
  });

  async function dropStation() {
    if (!station) return;
    if (!(await ask(`Удалить ${station.name}?`, "Уйдут её передачи за сутки, расписание и ответчики, позывной освободится."))) return;
    await api.DELETE("/studio/api/air/stations/{station_id}", { params: { path: { station_id: station.id } } });
    selected = null;
    await loadStations();
    onchange?.();
  }

  // ---------- передача по расписанию ----------
  type BForm = { id: number | null; freq: string; schedule: string; time_zone: string; texts: string; condition: string; note: string; active: boolean; key: string };
  let bform = $state<BForm | null>(null);
  let busy = $state(false);
  function editBroadcast(row: Broadcast | null) {
    bform = row
      ? { id: row.id, freq: row.freq, schedule: row.schedule, time_zone: row.time_zone, texts: row.texts.join("\n"), condition: cond(row.condition), note: row.note, active: row.active, key: row.key }
      : { id: null, freq: broadcasts[0]?.freq ?? responders[0]?.freq ?? "", schedule: "daily 21:00", time_zone: "UTC", texts: "", condition: "", note: "", active: true, key: "" };
  }
  async function saveBroadcast() {
    if (!bform || !station) return;
    busy = true;
    const body = { station: station.id, freq: bform.freq, schedule: bform.schedule, time_zone: bform.time_zone, texts: bform.texts.split("\n"),
                   condition: bform.condition.trim() || null, note: bform.note, active: bform.active, key: bform.key };
    const { error } = bform.id !== null
      ? await api.PUT("/studio/api/air/broadcasts/{broadcast_id}", { params: { path: { broadcast_id: bform.id } }, body })
      : await api.POST("/studio/api/air/broadcasts", { body });
    busy = false;
    if (error) return toast(problem(error), "error");
    toast(bform.id !== null ? "Передача сохранена." : "Передача добавлена в расписание.");
    bform = null;
    loadStation();
  }
  async function toggleBroadcast(row: Broadcast) {
    const body = { station: row.station, freq: row.freq, schedule: row.schedule, time_zone: row.time_zone, texts: row.texts, condition: row.condition ?? null, note: row.note, active: !row.active, key: row.key };
    const { error } = await api.PUT("/studio/api/air/broadcasts/{broadcast_id}", { params: { path: { broadcast_id: row.id } }, body });
    if (error) return toast(problem(error), "error");
    loadStation();
  }
  async function airNow(row: Broadcast) {
    const { error } = await api.POST("/studio/api/air/broadcasts/{broadcast_id}/now", { params: { path: { broadcast_id: row.id } } });
    if (error) return toast(problem(error), "error");
    toast(`Выпущено на ${row.freq}.`);
  }
  async function dropBroadcast(row: Broadcast) {
    if (!(await ask("Удалить передачу из расписания?", "Уже вышедшие выпуски останутся в эфире до суток."))) return;
    await api.DELETE("/studio/api/air/broadcasts/{broadcast_id}", { params: { path: { broadcast_id: row.id } } });
    loadStation();
  }

  // ---------- ответчик ----------
  type RForm = { id: number | null; freq: string; pattern: string; regex: boolean; condition: string; cooldown: number; reply: string; delay: number; actions: Action[]; note: string; active: boolean; key: string };
  let rform = $state<RForm | null>(null);
  const KINDS = ["flag", "unflag", "key", "file", "hook", "world_flag", "world_unflag", "world_count"];
  function editResponder(row: Responder | null) {
    rform = row
      ? { id: row.id, freq: row.freq, pattern: row.pattern, regex: row.regex, condition: cond(row.condition), cooldown: row.cooldown, reply: row.reply, delay: row.delay,
          actions: (row.actions ?? []) as Action[], note: row.note, active: row.active, key: row.key }
      : { id: null, freq: broadcasts[0]?.freq ?? responders[0]?.freq ?? "", pattern: "", regex: false, condition: "", cooldown: 10, reply: "{callsign} DE " + (station?.name ?? ""), delay: 5, actions: [], note: "", active: true, key: "" };
  }
  async function saveResponder() {
    if (!rform || !station) return;
    busy = true;
    const body = { station: station.id, freq: rform.freq, pattern: rform.pattern, regex: rform.regex, condition: rform.condition.trim() || null,
                   cooldown: rform.cooldown, reply: rform.reply, delay: rform.delay, actions: rform.actions as Record<string, unknown>[], note: rform.note, active: rform.active, key: rform.key };
    const { error } = rform.id !== null
      ? await api.PUT("/studio/api/air/responders/{responder_id}", { params: { path: { responder_id: rform.id } }, body })
      : await api.POST("/studio/api/air/responders", { body });
    busy = false;
    if (error) return toast(problem(error), "error");
    toast(rform.id !== null ? "Ответчик сохранён." : "Ответчик добавлен.");
    rform = null;
    loadStation();
  }
  async function dropResponder(row: Responder) {
    if (!(await ask("Удалить ответчика?", "Станция перестанет отвечать на эту фразу."))) return;
    await api.DELETE("/studio/api/air/responders/{responder_id}", { params: { path: { responder_id: row.id } } });
    loadStation();
  }
  const ACTION_TEXT: Record<string, (a: Record<string, unknown>) => string> = {
    flag: (a) => `метка ${a.name ?? ""}`, unflag: (a) => `снять метку ${a.name ?? ""}`, key: (a) => `ключ ${a.slug ?? ""}`,
    file: (a) => `файл ${a.item ?? ""} → ${a.path ?? ""}`, hook: () => "хук",
    world_flag: (a) => `world:${a.name ?? ""}`, world_unflag: (a) => `снять world:${a.name ?? ""}`, world_count: (a) => `world:${a.name ?? ""} +${a.delta ?? 1}`,
  };
  const actionsText = (actions: Record<string, unknown>[]) => actions.map((a) => ACTION_TEXT[String(a.do)]?.(a) ?? String(a.do)).join(", ");
</script>

<div class="layout">
  <aside class="list">
    <h3>Позывные</h3>
    <ul>
      {#each stations as s (s.id)}
        <li><button class:on={s.id === selected} onclick={() => (selected = s.id)}>
          <b class="mono">{s.name}</b><span class="muted small">{s.kind === "character" ? "персонаж" : "станция"}{s.label ? ` · ${s.label}` : ""}</span>
        </button></li>
      {:else}<li class="muted small pad">Станций пока нет.</li>{/each}
    </ul>
    <p class="muted small pad">Позывные заводятся у персонажа: <a href="#/characters">Персонажи</a> → карточка → «Позывные в эфире».</p>
  </aside>

  <section class="detail">
    {#if station}
      <header class="head">
        <div><h2 class="mono">{station.name}</h2><span class="muted small">{station.kind === "character" ? "персонаж" : "станция"}{station.label ? ` · ${station.label}` : ""}</span></div>
        <button class="btn ghost danger" onclick={dropStation}>Удалить станцию</button>
      </header>

      <div class="block">
        <div class="bhead"><h3>Передачи по расписанию</h3><button class="btn" onclick={() => editBroadcast(null)}>+ Передача</button></div>
        <p class="muted small">Выходят в эфир сами, когда в мире наступает время. Время игровое, в поясе передачи.</p>
        {#each broadcasts as b (b.id)}
          <div class="item" class:off={!b.active}>
            <div class="main">
              <div class="line1"><b class="mono">{b.freq}</b> <span>{b.summary || b.schedule}</span>{#if b.time_zone !== "UTC"}<span class="muted small"> · {b.time_zone}</span>{/if}
                {#if !b.active}<span class="badge">выключена</span>{/if}{#if cond(b.condition)}<span class="badge">слышно с ключом {cond(b.condition)}</span>{/if}{#if b.key}<span class="badge">шифр {b.key}</span>{/if}</div>
              <div class="quote">«{b.texts[0]}»{#if b.texts.length > 1}<span class="muted small"> и ещё {b.texts.length - 1} по кругу</span>{/if}</div>
              <div class="muted small">{b.next_at ? `следующий выпуск ${game(b.next_at, b.time_zone)}` : b.active ? "больше не выйдет" : ""}{b.last_at ? ` · последний ${game(b.last_at, b.time_zone)}` : ""}{b.note ? ` · ${b.note}` : ""}</div>
            </div>
            <div class="acts">
              <button class="btn ghost small" onclick={() => airNow(b)} title="Выпустить следующий текст сейчас">Выпустить сейчас</button>
              <button class="btn ghost small" onclick={() => toggleBroadcast(b)}>{b.active ? "Выключить" : "Включить"}</button>
              <button class="btn ghost small" onclick={() => editBroadcast(b)}>Изменить</button>
              <button class="btn ghost small danger" onclick={() => dropBroadcast(b)}>Удалить</button>
            </div>
          </div>
        {:else}<p class="muted small empty">Расписания нет: станция говорит только когда вы передаёте от её имени.</p>{/each}
      </div>

      <div class="block">
        <div class="bhead"><h3>Ответчики</h3><button class="btn" onclick={() => editResponder(null)}>+ Ответчик</button></div>
        <p class="muted small">Станция слушает частоту и отвечает игроку на фразу. Ответ слышат все на частоте, исходы получает только передавший. Проверить: откройте песочницу и передайте фразу из приложения «эфир».</p>
        {#each responders as r (r.id)}
          <div class="item" class:off={!r.active}>
            <div class="main">
              <div class="line1"><b class="mono">{r.freq}</b> <span>на «{r.pattern.split("\n").filter(Boolean).join("» или «")}»</span>{#if r.regex}<span class="badge">regex</span>{/if}
                {#if !r.active}<span class="badge">выключен</span>{/if}{#if cond(r.condition)}<span class="badge">только с ключом {cond(r.condition)}</span>{/if}{#if r.key}<span class="badge">слушает шифром {r.key}</span>{/if}</div>
              {#if r.reply}<div class="quote">→ «{r.reply}» <span class="muted small">через {r.delay} с</span></div>{/if}
              <div class="muted small">{r.actions.length ? `исходы: ${actionsText(r.actions)} · ` : ""}пауза для игрока {r.cooldown} мин · сработал {r.fires} раз{r.note ? ` · ${r.note}` : ""}</div>
            </div>
            <div class="acts">
              <button class="btn ghost small" onclick={() => editResponder(r)}>Изменить</button>
              <button class="btn ghost small danger" onclick={() => dropResponder(r)}>Удалить</button>
            </div>
          </div>
        {:else}<p class="muted small empty">Ответчиков нет.</p>{/each}
      </div>
    {:else}
      <p class="muted pad">Добавьте станцию или персонажа слева: от их имени идут передачи по расписанию и ответы игрокам.</p>
    {/if}
  </section>
</div>

<datalist id="air-zones">{#each ZONES as zone}<option value={zone}></option>{/each}</datalist>

{#if bform}
  <Dialog wide title={bform.id !== null ? "Передача по расписанию" : `Новая передача ${station?.name ?? ""}`} confirm="Сохранить" {busy}
    disabled={!bform.freq.trim() || !bform.schedule.trim() || !bform.texts.trim()} onsubmit={saveBroadcast} onclose={() => (bform = null)}>
    <div class="form">
      <div class="two">
        <label><span class="label">Частота, МГц</span><input class="field mono" bind:value={bform.freq} placeholder="7.115" /></label>
        <label><span class="label">Часовой пояс<Hint text="В нём читается расписание: «daily 21:00» в Europe/Moscow — это 21:00 по Москве в игровом времени." /></span><input class="field mono" list="air-zones" bind:value={bform.time_zone} /></label>
      </div>
      <label><span class="label">Когда (игровое время)</span>
        <textarea class="field mono" rows="3" bind:value={bform.schedule}></textarea>
        <span class="muted small">По строке на правило: <code>daily 21:00</code> · <code>mon-fri 09:00 18:00</code> · <code>hourly :15</code> · <code>every 30m</code> · <code>once 2031-03-01 21:00</code></span>
      </label>
      <label><span class="label">Что передаёт</span>
        <textarea class="field" rows="4" bind:value={bform.texts} placeholder={"QRZ? DE BOREAS\n7 4 1 9 · 2 2 0 5"}></textarea>
        <span class="muted small">По строке на выпуск: если строк несколько, выпуски идут по кругу. До 400 знаков.</span>
      </label>
      <div class="two">
        <label><span class="label">Кому слышно<Hint text="Ключ (slug), без которого игрок эту передачу не услышит. Пусто: всем на частоте." /></span><input class="field mono" bind:value={bform.condition} placeholder="всем" /></label>
        <label><span class="label">Заметка</span><input class="field" bind:value={bform.note} /></label>
      </div>
      <label><span class="label">Шифр (Виженер)<Hint text="Слово-ключ. Пусто: открытым текстом. С ключом выпуск звучит шифровкой: открытым его видит только тот, кто поставил на приёмнике этот ключ." /></span><input class="field mono" bind:value={bform.key} maxlength="32" placeholder="без шифра" /></label>
      <label class="check"><input type="checkbox" bind:checked={bform.active} /> Включена</label>
    </div>
  </Dialog>
{/if}

{#if rform}
  <Dialog wide title={rform.id !== null ? "Ответчик" : `Новый ответчик ${station?.name ?? ""}`} confirm="Сохранить" {busy}
    disabled={!rform.freq.trim() || !rform.pattern.trim()} onsubmit={saveResponder} onclose={() => (rform = null)}>
    <div class="form">
      <div class="two">
        <label><span class="label">Слушает частоту, МГц</span><input class="field mono" bind:value={rform.freq} placeholder="7.115" /></label>
        <label><span class="label">Отвечает только с ключом</span><input class="field mono" bind:value={rform.condition} placeholder="всем" /></label>
      </div>
      <label><span class="label">Шифр станции (Виженер)<Hint text="Станция слушает и отвечает этим словом-ключом: фразу поймёт, только если игрок передал её с тем же ключом, а ответ уйдёт шифровкой. Пусто: слышит эфир как есть." /></span><input class="field mono" bind:value={rform.key} maxlength="32" placeholder="без шифра" /></label>
      <label><span class="label">На что отвечает</span>
        <textarea class="field mono" rows="3" bind:value={rform.pattern} placeholder={"qrz boreas\nкто на частоте"}></textarea>
        <span class="muted small">По строке на вариант: слово или фраза целиком, регистр не важен.</span>
      </label>
      <label class="check"><input type="checkbox" bind:checked={rform.regex} /> Строки — регулярные выражения</label>
      <label><span class="label">Ответ в эфир</span>
        <textarea class="field" rows="2" bind:value={rform.reply}></textarea>
        <span class="muted small"><code>{"{callsign}"}</code> — позывной передавшего. Пусто: станция молчит, но исходы срабатывают.</span>
      </label>
      <div class="two">
        <label><span class="label">Ответ через, секунд</span><input class="field mono" type="number" min="0" bind:value={rform.delay} /></label>
        <label><span class="label">Пауза для одного игрока, минут</span><input class="field mono" type="number" min="0" bind:value={rform.cooldown} /></label>
      </div>
      <div><span class="label">Исходы для передавшего</span>
        <Actions bind:actions={rform.actions} steps={[]} {picks} kinds={KINDS} />
      </div>
      <div class="two">
        <label><span class="label">Заметка</span><input class="field" bind:value={rform.note} /></label>
        <label class="check"><input type="checkbox" bind:checked={rform.active} /> Включён</label>
      </div>
    </div>
  </Dialog>
{/if}

<style>
  .layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; align-items: start; }
  .list, .detail { border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .list { display: flex; flex-direction: column; padding: 12px; gap: 10px; }
  .list h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .list ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .list li button { display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .list li button:hover { background: var(--raise); }
  .list li button.on { background: color-mix(in srgb, var(--accent) 14%, transparent); }
  .detail { display: flex; flex-direction: column; gap: 14px; padding: 14px 16px; min-width: 0; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .head h2 { margin: 0; font-size: 18px; }
  .block { display: flex; flex-direction: column; gap: 8px; }
  .bhead { display: flex; justify-content: space-between; align-items: center; }
  .bhead h3 { margin: 0; font-size: 14px; }
  .block p { margin: 0; }
  .item { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg); }
  .item.off { opacity: 0.6; }
  .main { min-width: 0; display: flex; flex-direction: column; gap: 3px; font-size: 13px; }
  .quote { overflow-wrap: anywhere; }
  .acts { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; align-content: flex-start; max-width: 280px; }
  .badge { margin-left: 6px; padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .empty { padding: 6px 0; }
  .form { display: flex; flex-direction: column; gap: 12px; }
  .form label { display: flex; flex-direction: column; gap: 4px; }
  .form .check { flex-direction: row; align-items: center; gap: 8px; }
  .form .check input { width: auto; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: end; }
  .label { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
  textarea { resize: vertical; font: inherit; }
  .mono { font-family: var(--mono); }
  .small { font-size: 12px; }
  .pad { padding: 8px; }
  code { font-family: var(--mono); font-size: 12px; }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
