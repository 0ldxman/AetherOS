<script lang="ts">
  // Время мира: что сейчас в игре и на машинах, ход времени на шкале, перевод часов одной фразой.
  // Расчёт и проверки на сервере (machines/world/chrono.py); здесь те же формулы только для показа.
  import { onDestroy, onMount } from "svelte";
  import PageHead from "../lib/PageHead.svelte";
  import Dialog from "../lib/Dialog.svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import { toast } from "../lib/toast.svelte";

  type Time = Schemas["TimeOut"];
  type Anchor = Schemas["AnchorOut"];
  type Row = { id: number | null; real: number; game: number; rate: number };

  const MIN = 60000, H = 3600000, D = 24 * H;
  const FROZEN: Row = { id: null, real: Date.UTC(2000, 0, 1), game: Date.UTC(2030, 10, 14, 3, 14), rate: 0 };

  let time = $state<Time | null>(null);
  let loadedAt = 0;
  let tick = $state(0);
  let timer: ReturnType<typeof setInterval>;

  // ---------- формулы, как в chrono.py ----------
  const rowsOf = (data: Time | null, skip: number | null = null): Row[] => {
    const rows = (data?.anchors ?? []).filter((a) => a.id !== skip).map((a) => ({ id: a.id, real: Date.parse(a.real_at), game: Date.parse(a.game_at), rate: a.rate }));
    return rows.length ? rows : [FROZEN];
  };
  function at(real: number, rows: Row[]) {
    let found = rows[0];
    for (const row of rows) { if (row.real <= real) found = row; else break; }
    return found;
  }
  const toGame = (real: number, rows: Row[]) => { const row = at(real, rows); return row.game + (real - row.real) * row.rate; };
  function toReal(game: number, after: number, rows: Row[]): number | null {
    const first = rows.indexOf(at(after, rows));
    for (let i = first; i < rows.length; i++) {
      const row = rows[i];
      const begin = i === first ? Math.max(row.real, after) : row.real;
      const end = i + 1 < rows.length ? rows[i + 1].real : Infinity;
      if (row.game + (begin - row.real) * row.rate >= game) return begin;
      if (row.rate > 0) { const reach = row.real + (game - row.game) / row.rate; if (reach < end) return Math.max(reach, begin); }
    }
    return null;
  }

  const realNow = $derived.by(() => { void tick; return time ? Date.parse(time.real_now) + (Date.now() - loadedAt) : Date.now(); });
  const rows = $derived(rowsOf(time));
  const gameNow = $derived(toGame(realNow, rows));
  const rateNow = $derived(at(realNow, rows).rate);

  // ---------- слова и даты ----------
  const pad = (n: number) => String(n).padStart(2, "0");
  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const MONTHS_FULL = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const d = (ms: number) => new Date(ms);
  const hm = (ms: number) => `${pad(d(ms).getUTCHours())}:${pad(d(ms).getUTCMinutes())}`;
  const day = (ms: number, year = true) => `${d(ms).getUTCDate()} ${MONTHS[d(ms).getUTCMonth()]}${year ? " " + d(ms).getUTCFullYear() : ""}`;
  const when = (ms: number, year = true) => `${day(ms, year)}, ${hm(ms)}`;
  const longDay = (ms: number) => `${d(ms).getUTCDate()} ${MONTHS_FULL[d(ms).getUTCMonth()]} ${d(ms).getUTCFullYear()}`;
  const field = (ms: number) => `${d(ms).getUTCFullYear()}-${pad(d(ms).getUTCMonth() + 1)}-${pad(d(ms).getUTCDate())}T${hm(ms)}`;
  const parseField = (value: string) => (value ? Date.parse(`${value}:00Z`) : NaN);
  function span(ms: number) {
    const total = Math.round(Math.abs(ms) / MIN);
    const days = Math.floor(total / 1440), hours = Math.floor((total % 1440) / 60), minutes = total % 60;
    if (days >= 365) return `${(days / 365).toFixed(1).replace(".0", "").replace(".", ",")} г`;
    return [days ? `${days} д` : "", hours ? `${hours} ч` : "", !days && minutes ? `${minutes} мин` : ""].filter(Boolean).join(" ") || "меньше минуты";
  }
  const signed = (ms: number) => (ms >= 0 ? "+" : "−") + span(ms);

  const RATES: { value: number; label: string }[] = [
    { value: 1, label: "идти как в жизни" }, { value: 0, label: "стоять" }, { value: 0.5, label: "идти вдвое медленнее" },
    { value: 0.33, label: "идти втрое медленнее" }, { value: 2, label: "идти вдвое быстрее" }, { value: 24, label: "идти сутки за реальный час" },
  ];
  const rateLabel = (rate: number) => RATES.find((r) => r.value === rate)?.label ?? (rate < 1 ? `идти в ${+(1 / rate).toFixed(2)} раза медленнее (×${rate})` : `идти в ${+rate.toFixed(2)} раза быстрее (×${rate})`);
  const goes = (rate: number) => (rate === 0 ? "стоит" : rateLabel(rate).replace("идти", "идёт"));

  function inZone(ms: number, zone: string) {
    try {
      const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "short", day: "numeric" }).formatToParts(d(ms));
      const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
      return { clock: `${get("hour")}:${get("minute")}`, abbr: get("timeZoneName"), other: Number(get("day")) !== d(ms).getUTCDate() };
    } catch { return { clock: hm(ms), abbr: zone, other: false }; }
  }

  async function load() {
    const { data } = await api.GET("/studio/api/world/time");
    if (data) { time = data; loadedAt = Date.now(); }
  }
  onMount(() => {
    load();
    timer = setInterval(() => {
      tick++;
      if (time?.anchors.some((a) => !a.past && Date.parse(a.real_at) <= realNow)) load();
    }, 1000);
  });
  onDestroy(() => clearInterval(timer));

  // ---------- одно действие на сервер ----------
  type Draft = { real_at: string | null; game_at: string; rate: number; note: string };
  async function send(body: Draft, editId: number | null = null) {
    const { data, error } = editId !== null
      ? await api.PUT("/studio/api/world/time/{anchor_id}", { params: { path: { anchor_id: editId } }, body })
      : await api.POST("/studio/api/world/time", { body });
    if (error || !data) { toast(problem(error, "Не сохранилось."), "error"); return false; }
    time = data;
    loadedAt = Date.now();
    return true;
  }

  // остановить / пустить: в один клик, с возвратом в уведомлении
  async function toggle() {
    const previous = rateNow;
    const next = previous === 0 ? 1 : 0;
    if (!(await send({ real_at: null, game_at: new Date(gameNow).toISOString(), rate: next, note: next ? "пуск" : "остановка" }))) return;
    toast(next ? "Время пошло как в жизни." : "Время остановлено.", "ok", {
      label: "Вернуть",
      run: () => send({ real_at: null, game_at: new Date(gameNow).toISOString(), rate: previous, note: "возврат хода" }),
    });
  }

  // ---------- окно «перевести часы» / «запланировать» ----------
  let dialog = $state<null | { plan: boolean; edit: number | null }>(null);
  let realField = $state("");
  let gameField = $state("");
  let gameTouched = $state(false);
  let rateChoice = $state<string>("1");          // значение из RATES или "custom"
  let rateCustom = $state("1");
  let note = $state("");
  let warn = $state<string[]>([]);
  let busy = $state(false);

  const realAt = $derived(dialog?.plan ? parseField(realField) : realNow);
  const baseRows = $derived(rowsOf(time, dialog?.edit ?? null));
  const before = $derived(Number.isFinite(realAt) ? toGame(realAt, baseRows) : NaN);       // каким было бы без изменения
  const rateBefore = $derived(Number.isFinite(realAt) ? at(realAt, baseRows).rate : rateNow);
  const gameAt = $derived(dialog?.plan && !gameTouched ? before : parseField(gameField));
  const rateValue = $derived(rateChoice === "custom" ? Number(rateCustom.replace(",", ".")) : Number(rateChoice));
  const delta = $derived(gameAt - before);
  const moved = $derived(Math.abs(delta) >= MIN);
  const issue = $derived(
    dialog?.plan && !Number.isFinite(realAt) ? "Укажите, когда это случится." :
    dialog?.plan && realAt < realNow - 30000 ? "Этот момент уже прошёл: прошлое не переписывается." :
    !Number.isFinite(gameAt) ? "Укажите, что станет в мире." :
    !(rateValue >= 0) ? "Скорость: число от 0, например 1, 0.5 или 24." :
    !moved && rateValue === rateBefore ? "Ничего не меняется: та же дата и тот же ход." : "",
  );
  const same = $derived(issue.startsWith("Ничего"));
  const confirmText = $derived(
    dialog?.edit != null ? "Сохранить" :
    dialog?.plan ? "Запланировать" :
    moved ? `Перевести ${delta > 0 ? "вперёд" : "назад"} на ${span(delta)}` : "Изменить ход",
  );

  function open(plan: boolean, anchor: Anchor | null = null) {
    dialog = { plan, edit: anchor?.id ?? null };
    warn = [];
    note = anchor?.note ?? "";
    if (anchor) {
      realField = field(Date.parse(anchor.real_at));
      gameField = field(Date.parse(anchor.game_at));
      gameTouched = true;
      setRate(anchor.rate);
    } else {
      realField = plan ? field(Math.ceil((realNow + D) / H) * H) : "";
      gameField = field(plan ? toGame(parseField(realField), rows) : gameNow);
      gameTouched = !plan;
      setRate(rateNow);
    }
  }
  function setRate(rate: number) {
    if (RATES.some((r) => r.value === rate)) rateChoice = String(rate);
    else { rateChoice = "custom"; rateCustom = String(rate); }
  }
  function nudge(ms: number) {
    const base = Number.isFinite(gameAt) ? gameAt : before;
    gameField = field(base + ms);
    gameTouched = true;
  }
  // пока автор не трогал игровую дату, в плане она идёт за реальным моментом
  $effect(() => { if (dialog?.plan && !gameTouched && Number.isFinite(before)) gameField = field(before); });

  function draft(): Draft {
    return { real_at: dialog?.plan && Number.isFinite(realAt) ? new Date(realAt).toISOString() : null,
             game_at: Number.isFinite(gameAt) ? new Date(gameAt).toISOString() : "", rate: rateValue, note: note.trim() };
  }

  // что скажет сервер о сдвиге назад: сколько записей окажется «в будущем»
  let checkTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const body = draft();
    if (!dialog || issue || delta >= -MIN) { warn = []; return; }
    clearTimeout(checkTimer);
    checkTimer = setTimeout(async () => {
      const { data } = await api.POST("/studio/api/world/time/check", { body, params: { query: { skip: dialog?.edit ?? undefined } } });
      warn = data?.items.filter((line) => !line.startsWith("Сдвиг назад")) ?? [];
    }, 300);
  });

  async function submit() {
    if (issue || !dialog) return;
    busy = true;
    const ok = await send(draft(), dialog.edit);
    busy = false;
    if (!ok) return;
    toast(dialog.edit !== null ? "Изменение сохранено." : dialog.plan ? "Изменение запланировано." : "Часы переведены.");
    dialog = null;
  }

  async function cancelPlan(anchor: Anchor) {
    const { data, error } = await api.DELETE("/studio/api/world/time/{anchor_id}", { params: { path: { anchor_id: anchor.id } } });
    if (error || !data) return toast(problem(error, "Не отменилось."), "error");
    time = data;
    loadedAt = Date.now();
    toast("Запланированное изменение отменено.");
  }

  // ---------- шкала и списки ----------
  const items = $derived.by(() => {
    if (!time) return [];
    const list = time.anchors;
    return list.map((anchor, i) => {
      const real = Date.parse(anchor.real_at), game = Date.parse(anchor.game_at);
      const prev = i > 0 ? list[i - 1] : null;
      const reached = prev ? Date.parse(prev.game_at) + (real - Date.parse(prev.real_at)) * prev.rate : game;
      const until = i + 1 < list.length ? Date.parse(list[i + 1].real_at) : null;
      const state = anchor.current ? "now" : anchor.past ? "past" : "plan";
      return { anchor, real, game, jump: prev ? game - reached : 0, until, state };
    });
  });
  const ahead = $derived(items.filter((x) => x.state === "plan"));
  const current = $derived(items.find((x) => x.state === "now") ?? null);
  const earlier = $derived(items.filter((x) => x.state === "past").reverse());

  const scale = $derived.by(() => {
    if (!items.length) return null;
    const start = realNow - 7 * D;
    const end = Math.max(realNow + 14 * D, items[items.length - 1].real + 7 * D);
    const x = (ms: number) => ((Math.min(Math.max(ms, start), end) - start) / (end - start)) * 100;
    const blocks = items.filter((item) => (item.until ?? end) > start).map((item) => {
      const to = item.until ?? end;
      const gameTo = item.game + (Math.min(to, end) - item.real) * item.anchor.rate;
      return { item, left: x(item.real), width: Math.max(0.4, x(to) - x(item.real)),
               label: item.anchor.rate === 0 ? `${day(item.game, false)}, стоит` : `${day(item.game, false)} → ${day(gameTo, false)}` };
    });
    // подписи прыжков: из нескольких изменений почти в одно время показываем последнее
    blocks.forEach((b, i) => { (b as { crowded?: boolean }).crowded = i + 1 < blocks.length && blocks[i + 1].left - b.left < 3; });
    const ticks = Array.from({ length: 5 }, (_, i) => start + ((end - start) * i) / 4).map((t) => ({ left: x(t), text: day(t, false) }));
    return { blocks, now: x(realNow), ticks };
  });

  // ---------- быстрый перевод дат ----------
  let askReal = $state("");
  let askGame = $state("");
  const answerReal = $derived(Number.isFinite(parseField(askReal)) ? when(toGame(parseField(askReal), rows)) : "…");
  const answerGame = $derived.by(() => {
    const game = parseField(askGame);
    if (!Number.isFinite(game)) return "…";
    if (game <= gameNow) return "уже наступил";
    const found = toReal(game, realNow, rows);
    return found === null ? "никогда: время встанет раньше" : `${when(found)} UTC реального времени`;
  });
</script>

<PageHead title="Время мира">
  {#snippet sub()}В мире одно время на всех, машины показывают его в своих часовых поясах. Прошлое не переписывается, будущее можно планировать и отменять.{/snippet}
</PageHead>

{#if time}
  <section class="hero">
    <div class="clock">
      <div class="date">{longDay(gameNow)}</div>
      <div class="hms mono">{hm(gameNow)}<span class="sec">:{pad(d(gameNow).getUTCSeconds())}</span> <span class="utc">UTC</span></div>
      <div class="state"><span class="dot" class:stopped={rateNow === 0}></span>Время {goes(rateNow)}</div>
      {#if time.zones.length}
        <div class="zones">
          {#each time.zones as row (row.zone)}
            {@const z = inZone(gameNow, row.zone)}
            <span class="zone" title="{row.zone}: {row.machines.join(', ')}"><b class="mono">{z.clock}</b> {z.abbr}{z.other ? " (другие сутки)" : ""} <span class="muted">{row.machines[0]}{row.machines.length > 1 ? ` и ещё ${row.machines.length - 1}` : ""}</span></span>
          {/each}
        </div>
      {/if}
    </div>
    <div class="actions">
      <button class="btn primary" onclick={() => open(false)}>Перевести часы…</button>
      <button class="btn" onclick={toggle}>{rateNow === 0 ? "Пустить время" : "Остановить время"}</button>
      <button class="btn" onclick={() => open(true)}>Запланировать…</button>
    </div>
  </section>

  <section class="card">
    <h2>Ход времени</h2>
    {#if scale}
      <div class="scale" aria-hidden="true">
        <div class="track">
          {#each scale.blocks as b (b.item.anchor.id)}
            <div class="block {b.item.state}" style="left:{b.left}%;width:{b.width}%" title="с {when(b.item.real)}: в мире {when(b.item.game)}, время {goes(b.item.anchor.rate)}">
              {#if b.width > 9}<span>{b.label}</span>{/if}
            </div>
            {#if Math.abs(b.item.jump) >= MIN && b.left > 2 && !(b as { crowded?: boolean }).crowded}<span class="jump" class:back={b.item.jump < 0} style="left:{b.left}%">{signed(b.item.jump)}</span>{/if}
          {/each}
          <div class="today" style="left:{scale.now}%"></div>
        </div>
        <div class="ticks">{#each scale.ticks as t}<span style="left:{t.left}%">{t.text}</span>{/each}<span class="nowlabel" style="left:{scale.now}%">сейчас</span></div>
        <div class="legend muted small"><span class="key past"></span>было <span class="key now"></span>идёт сейчас <span class="key plan"></span>запланировано <span class="sep">·</span> по горизонтали реальное время, в полосе: какие дни идут в мире</div>
      </div>
    {/if}

    {#if ahead.length}
      <h3>Впереди</h3>
      <ul class="list">
        {#each ahead as item (item.anchor.id)}
          <li class="plan">
            <div class="what">
              <b>{when(item.real)}</b> в мире станет <b>{when(item.game)}</b>{#if Math.abs(item.jump) >= MIN} <span class="chip" class:back={item.jump < 0}>{signed(item.jump)}</span>{/if}, дальше время будет {rateLabel(item.anchor.rate)}
              <div class="muted small">через {span(item.real - realNow)}{item.anchor.note ? ` · ${item.anchor.note}` : ""}</div>
            </div>
            <div class="row-acts">
              <button class="btn ghost" onclick={() => open(true, item.anchor)}>Изменить</button>
              <button class="btn ghost danger" onclick={() => cancelPlan(item.anchor)}>Отменить</button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    <h3>Сейчас</h3>
    {#if current}
      <ul class="list"><li class="now">
        <div class="what">
          С <b>{when(current.real)}</b> мир идёт от <b>{when(current.game)}</b>, время {goes(current.anchor.rate)}
          <div class="muted small">уже {span(realNow - current.real)}{current.anchor.rate > 0 ? `, в мире прошло ${span((realNow - current.real) * current.anchor.rate)}` : ""}{current.anchor.note ? ` · ${current.anchor.note}` : ""}</div>
        </div>
      </li></ul>
    {:else}
      <p class="muted">Время ещё не настраивали: мир стоит на {when(FROZEN.game)} UTC. Нажмите «Перевести часы…», задайте дату и ход.</p>
    {/if}

    {#if earlier.length}
      <details class="past-list">
        <summary>Было раньше ({earlier.length})</summary>
        <ul class="list">
          {#each earlier as item (item.anchor.id)}
            <li class="past">
              <div class="what">
                <b>{when(item.real)}</b> в мире стало <b>{when(item.game)}</b>{#if Math.abs(item.jump) >= MIN} <span class="chip" class:back={item.jump < 0}>{signed(item.jump)}</span>{/if}, время {goes(item.anchor.rate)}
                <div class="muted small">так было {span((item.until ?? realNow) - item.real)}{item.anchor.note ? ` · ${item.anchor.note}` : ""}</div>
              </div>
            </li>
          {/each}
        </ul>
      </details>
    {/if}

    <div class="ask">
      <h3>Свериться</h3>
      <label>Реальный момент <input class="field mono" type="datetime-local" bind:value={askReal} /> UTC — в мире будет <b class="mono">{answerReal}</b></label>
      <label>Игровой момент <input class="field mono" type="datetime-local" bind:value={askGame} /> UTC — наступит <b class="mono">{answerGame}</b></label>
      <span class="muted small">Считается по нынешнему плану.</span>
    </div>
  </section>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

{#if dialog}
  <Dialog wide title={dialog.edit !== null ? "Изменить запланированное" : dialog.plan ? "Запланировать изменение времени" : "Перевести часы мира"} confirm={confirmText} {busy} disabled={!!issue} onsubmit={submit} onclose={() => (dialog = null)}>
    <div class="phrase">
      {#if dialog.plan}
        <div class="line">
          <span class="word">Когда</span>
          <input class="field mono" type="datetime-local" bind:value={realField} aria-label="реальный момент, UTC" />
          <span class="muted small">реальное время, UTC</span>
        </div>
        {#if Number.isFinite(before)}<p class="muted small hint">к этому моменту в мире будет {when(before)}, время {goes(rateBefore)}</p>{/if}
      {/if}
      <div class="line">
        <span class="word">{dialog.plan ? "в мире станет" : "Сейчас в мире станет"}</span>
        <input class="field mono" type="datetime-local" bind:value={gameField} oninput={() => (gameTouched = true)} aria-label="игровой момент, UTC" />
        <span class="muted small">UTC</span>
      </div>
      <div class="nudges">
        {#each [[-D, "−1 д"], [-H, "−1 ч"], [H, "+1 ч"], [D, "+1 д"], [7 * D, "+1 нед"]] as [ms, label]}
          <button type="button" class="chip-btn" onclick={() => nudge(ms as number)}>{label}</button>
        {/each}
        <button type="button" class="chip-btn ghost" onclick={() => { gameTouched = !!dialog?.plan ? false : true; gameField = field(before); }}>без скачка</button>
      </div>
      <div class="line">
        <span class="word">и время будет</span>
        <select class="field" bind:value={rateChoice} aria-label="ход времени">
          {#each RATES as r}<option value={String(r.value)}>{r.label}</option>{/each}
          <option value="custom">своя скорость…</option>
        </select>
        {#if rateChoice === "custom"}<input class="field mono rate" inputmode="decimal" bind:value={rateCustom} aria-label="во сколько раз быстрее реального" /><span class="muted small">× реального</span>{/if}
      </div>
      <label class="note"><span class="muted small">Заметка для команды, необязательно</span><input class="field" maxlength="200" bind:value={note} placeholder="акт II, ночь события…" /></label>
    </div>

    <div class="result" class:bad={!!issue && !same} class:back={!issue && delta < -MIN}>
      {#if issue}
        {same ? (dialog.plan ? "Задайте, что станет в мире в этот момент, или другой ход времени." : "Поменяйте дату или ход времени: пока всё как сейчас.") : issue}
      {:else}
        <div><span class="muted">было</span> <span class="mono">{when(before)}</span> <span class="muted">→ станет</span> <b class="mono">{when(gameAt)}</b></div>
        <div>{moved ? `${delta > 0 ? "Вперёд" : "Назад"} на ${span(delta)}` : "Дата без скачка"}, дальше время {goes(rateValue)}.</div>
        {#if delta < -MIN}
          <div class="warnline">Игроки снова увидят время, которое уже было.{#each warn as line}{" "}{line}{/each}</div>
        {/if}
      {/if}
    </div>
  </Dialog>
{/if}

<style>
  .hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; flex-wrap: wrap; margin: 12px 32px; padding: 18px 20px;
          border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .clock { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .date { font-size: 15px; color: var(--muted); }
  .hms { font-size: 40px; font-weight: 600; line-height: 1.1; letter-spacing: 0.5px; }
  .sec { color: var(--muted); font-weight: 500; }
  .utc { font-size: 14px; color: var(--muted); font-weight: 500; }
  .state { display: flex; align-items: center; gap: 8px; font-size: 14px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok, #4cc38a); }
  .dot.stopped { background: var(--warn, #e0b050); }
  .zones { display: flex; flex-wrap: wrap; gap: 4px 18px; margin-top: 6px; font-size: 13px; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }

  .card { margin: 12px 32px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 10px; }
  h2 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3 { margin: 6px 0 0; font-size: 13px; font-weight: 600; }
  .small { font-size: 12px; }

  .scale { display: flex; flex-direction: column; gap: 4px; margin-bottom: 4px; }
  .track { position: relative; height: 40px; margin-top: 18px; border-radius: var(--radius); background: var(--bg); }
  .block { position: absolute; top: 0; bottom: 0; display: flex; align-items: center; padding: 0 8px; overflow: hidden; white-space: nowrap; font-size: 12px; border-right: 1px solid var(--panel); }
  .block.past { background: color-mix(in srgb, var(--muted) 22%, transparent); color: var(--muted); }
  .block.now { background: color-mix(in srgb, var(--accent) 30%, transparent); font-weight: 600; }
  .block.plan { background: repeating-linear-gradient(135deg, color-mix(in srgb, var(--accent) 16%, transparent) 0 6px, transparent 6px 12px); outline: 1px dashed var(--accent); outline-offset: -1px; }
  .block span { overflow: hidden; text-overflow: ellipsis; }
  .jump { position: absolute; top: -18px; transform: translateX(-50%); font-size: 11px; color: var(--accent); white-space: nowrap; }
  .jump.back { color: var(--warn, #e0b050); }
  .today { position: absolute; top: -4px; bottom: -4px; width: 2px; margin-left: -1px; background: var(--warn, #e0b050); }
  .ticks { position: relative; height: 16px; margin-top: 4px; font-size: 11px; color: var(--muted); }
  .ticks span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
  .ticks span:first-child { transform: none; }
  .ticks .nowlabel { color: var(--warn, #e0b050); background: var(--panel); padding: 0 4px; }
  .legend { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .key { display: inline-block; width: 14px; height: 10px; border-radius: 2px; margin-left: 6px; }
  .key.past { background: color-mix(in srgb, var(--muted) 22%, transparent); }
  .key.now { background: color-mix(in srgb, var(--accent) 30%, transparent); }
  .key.plan { outline: 1px dashed var(--accent); outline-offset: -1px; }
  .sep { margin: 0 4px; }

  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .list li { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 8px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); font-size: 13px; }
  .list li.now { border-color: color-mix(in srgb, var(--accent) 50%, transparent); }
  .list li.plan { border-style: dashed; }
  .list li.past { opacity: 0.75; }
  .what { min-width: 0; line-height: 1.5; }
  .chip { padding: 0 6px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); font-size: 12px; }
  .chip.back { background: color-mix(in srgb, var(--warn, #e0b050) 15%, transparent); color: var(--warn, #e0b050); }
  .row-acts { display: flex; gap: 6px; flex-shrink: 0; }
  .past-list summary { cursor: pointer; font-size: 13px; font-weight: 600; margin: 6px 0; }

  .ask { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; padding-top: 10px; border-top: 1px solid var(--line-soft); font-size: 13px; }
  .ask label { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .ask input { width: auto; }

  .phrase { display: flex; flex-direction: column; gap: 10px; }
  .line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .word { min-width: 160px; font-size: 14px; }
  .line input, .line select { width: auto; }
  .rate { width: 80px !important; }
  .hint { margin: -4px 0 0 170px; }
  .nudges { display: flex; gap: 6px; flex-wrap: wrap; margin-left: 170px; }
  .chip-btn { padding: 3px 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: inherit; font: inherit; font-size: 12px; cursor: pointer; }
  .chip-btn:hover { border-color: var(--accent); color: var(--accent); }
  .chip-btn.ghost { border-style: dashed; color: var(--muted); }
  .note { display: flex; flex-direction: column; gap: 4px; }
  .result { margin-top: 12px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg); font-size: 13px; line-height: 1.6; }
  .result.back { border-color: var(--warn, #e0b050); }
  .result.bad { border-color: var(--danger); color: var(--danger); }
  .result:not(.bad):not(.back) { color: inherit; }
  .warnline { color: var(--warn, #e0b050); }
  .pad { padding: 24px 32px; }
  @media (max-width: 700px) { .word { min-width: 0; } .hint, .nudges { margin-left: 0; } }
</style>
