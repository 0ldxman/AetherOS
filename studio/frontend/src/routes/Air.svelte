<script lang="ts">
  // Эфир в Студии: живая лента всех частот с модерацией, позывные с настоящими игроками, частоты (полосы и станции), жалобы.
  // Песочные передачи авторов помечены: настоящие игроки их не слышат.
  import { onDestroy, onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Icon from "../lib/Icon.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { toast } from "../lib/toast.svelte";

  type Row = Schemas["AirRow"];
  let { tab }: { tab: string } = $props();
  const TABS = [
    { key: "live", label: "Живой эфир" },
    { key: "callsigns", label: "Позывные" },
    { key: "bands", label: "Частоты" },
    { key: "reports", label: "Жалобы" },
  ];
  const current = $derived(TABS.some((t) => t.key === tab) ? tab : "live");

  const fmt = (at: string) => new Date(at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const when = (at: string | null) => (at ? new Date(at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");
  const who = (p: Schemas["AirPlayer"] | null) => (p ? `${p.username}${p.discord && p.discord !== p.username ? ` · Discord: ${p.discord}` : ""}` : "");

  // ---------- живой эфир ----------
  let rows = $state<Row[]>([]);
  let freq = $state("");
  let q = $state("");
  let paused = $state(false);
  let timer: ReturnType<typeof setInterval> | undefined;
  let stations = $state<Schemas["AirStation"][]>([]);
  let say = $state({ station: 0, freq: "14.230", text: "" });

  async function loadFeed(fresh = true) {
    const after = fresh || !rows.length ? 0 : rows[0].id;
    const { data, error } = await api.GET("/studio/api/air/feed", { params: { query: { freq, q, after } } });
    if (error || !data) return;
    rows = fresh ? data : [...data, ...rows].slice(0, 500);
  }
  let filterTimer: ReturnType<typeof setTimeout>;
  $effect(() => { freq; q; clearTimeout(filterTimer); filterTimer = setTimeout(() => loadFeed(true), 250); });
  $effect(() => {
    clearInterval(timer);
    if (current === "live" && !paused) timer = setInterval(() => loadFeed(false), 3000);
  });
  onDestroy(() => clearInterval(timer));

  function patch(row: Row) { rows = rows.map((r) => (r.id === row.id ? row : r)); }
  async function hide(row: Row) {
    const { data, error } = await api.POST("/studio/api/air/transmissions/{tx_id}/hide", { params: { path: { tx_id: row.id } }, body: { reason: "" } });
    if (error || !data) return toast(problem(error), "error");
    patch(data);
  }
  async function unhide(row: Row) {
    const { data } = await api.POST("/studio/api/air/transmissions/{tx_id}/unhide", { params: { path: { tx_id: row.id } } });
    if (data) patch(data);
  }
  async function sign(userId: number, body: Schemas["AirSignIn"], done: string) {
    const { error } = await api.PUT("/studio/api/air/callsigns/{user_id}", { params: { path: { user_id: userId } }, body });
    if (error) return toast(problem(error), "error");
    toast(done);
    if (current === "callsigns") loadSigns();
  }
  async function transmit() {
    if (!say.station || !say.text.trim()) return;
    const { data, error } = await api.POST("/studio/api/air/transmit", { body: { station: say.station, freq: say.freq, text: say.text } });
    if (error || !data) return toast(problem(error), "error");
    say.text = "";
    loadFeed(false);
  }

  // ---------- позывные ----------
  let signs = $state<Schemas["AirSign"][]>([]);
  let sq = $state("");
  let renaming = $state<number | null>(null);
  let newName = $state("");
  async function loadSigns() {
    signs = (await api.GET("/studio/api/air/callsigns", { params: { query: { q: sq } } })).data ?? [];
  }
  let signTimer: ReturnType<typeof setTimeout>;
  $effect(() => { sq; if (current !== "callsigns") return; clearTimeout(signTimer); signTimer = setTimeout(loadSigns, 200); });
  const muted = (s: Schemas["AirSign"]) => !!s.muted_until && new Date(s.muted_until) > new Date();

  // ---------- частоты ----------
  let bands = $state<Schemas["AirBand"][]>([]);
  let band = $state({ low: "", high: "", kind: "reserved", condition: "", label: "" });
  let station = $state({ name: "", label: "", kind: "station" });
  async function loadBands() {
    const [a, b] = await Promise.all([api.GET("/studio/api/air/bands"), api.GET("/studio/api/air/stations")]);
    bands = a.data ?? [];
    stations = b.data ?? [];
    if (!say.station && stations.length) say.station = stations[0].id;
  }
  async function addBand() {
    const { error } = await api.POST("/studio/api/air/bands", { body: { ...band, condition: band.condition.trim() || null } });
    if (error) return toast(problem(error), "error");
    band = { low: "", high: "", kind: "reserved", condition: "", label: "" };
    loadBands();
  }
  async function dropBand(id: number) {
    if (!(await ask("Удалить полосу?", "Частоты станут обычными: передавать и слушать там смогут все."))) return;
    await api.DELETE("/studio/api/air/bands/{band_id}", { params: { path: { band_id: id } } });
    loadBands();
  }
  async function addStation() {
    const { error } = await api.POST("/studio/api/air/stations", { body: station });
    if (error) return toast(problem(error), "error");
    station = { name: "", label: "", kind: "station" };
    loadBands();
  }
  async function dropStation(id: number) {
    if (!(await ask("Удалить станцию?", "Её передачи за сутки тоже пропадут, а позывной освободится."))) return;
    await api.DELETE("/studio/api/air/stations/{station_id}", { params: { path: { station_id: id } } });
    loadBands();
  }

  // ---------- жалобы ----------
  let reports = $state<Schemas["AirReport"][]>([]);
  async function loadReports() { reports = (await api.GET("/studio/api/air/reports")).data ?? []; }
  async function dismiss(id: number) {
    await api.POST("/studio/api/air/reports/{report_id}/dismiss", { params: { path: { report_id: id } } });
    loadReports();
  }
  async function hideReported(r: Schemas["AirReport"]) {
    await hide(r.transmission);
    loadReports();
  }

  onMount(() => { loadBands(); loadReports(); });
  $effect(() => { if (current === "bands") loadBands(); if (current === "reports") loadReports(); if (current === "callsigns") loadSigns(); });
</script>

<PageHead title="Эфир">
  {#snippet sub()}Открытый радиоэфир игроков: всё, что передают на всех частотах за последние сутки. Игрок слышит только то, что пришло после его выхода на частоту.{/snippet}
</PageHead>

<nav class="tabs" aria-label="Разделы эфира">
  {#each TABS as t (t.key)}
    <a class="tab" class:on={current === t.key} href="#/air/{t.key}">{t.label}{#if t.key === "reports" && reports.length}<span class="n">{reports.length}</span>{/if}</a>
  {/each}
</nav>

<div class="body">
  {#if current === "live"}
    <div class="bar">
      <label class="find"><Icon name="search" size={14} /><input placeholder="Позывной, игрок или текст" bind:value={q} aria-label="Поиск" /></label>
      <input class="field mono freq" placeholder="МГц" bind:value={freq} aria-label="Только частота" />
      {#if freq}<button class="btn ghost" onclick={() => (freq = "")}>Все частоты</button>{/if}
      <span class="grow"></span>
      <button class="btn ghost" onclick={() => (paused = !paused)}><Icon name={paused ? "run" : "stop"} size={14} />{paused ? "Продолжить" : "Пауза"}</button>
    </div>

    <ol class="feed">
      {#each rows as row (row.id)}
        <li class:hidden={row.hidden} class:sbx={row.sandbox}>
          <span class="t mono">{fmt(row.at)}</span>
          <button class="fq mono" onclick={() => (freq = row.freq)} title="Только эта частота">{row.freq}</button>
          <span class="cs mono" class:station={row.station} title={row.station ? "Станция или персонаж" : who(row.player)}>{row.callsign}</span>
          <span class="tx">{row.text}
            {#if row.hidden}<span class="badge">скрыто{row.hidden_reason ? `: ${row.hidden_reason}` : ""}</span>{/if}
            {#if row.sandbox}<span class="badge">песочница</span>{/if}
            {#if row.reports}<span class="badge warn">жалоб: {row.reports}</span>{/if}
          </span>
          <span class="acts">
            {#if row.hidden}<button class="btn ghost small" onclick={() => unhide(row)}>Вернуть</button>
            {:else}<button class="btn ghost small" onclick={() => hide(row)} title="У игроков станет «··· noise ···»">Скрыть</button>{/if}
            {#if row.player}
              <button class="btn ghost small" onclick={() => sign(row.player!.id, { mute_minutes: 60 }, `${row.callsign} заглушён на час.`)}>Заглушить 1 ч</button>
              <a class="btn ghost small" href="#/players/{row.player.id}" title={who(row.player)}>Игрок</a>
            {/if}
          </span>
        </li>
      {:else}
        <li class="empty muted">{freq || q ? "Ничего не нашлось." : "За сутки в эфире тихо."}</li>
      {/each}
    </ol>

    <form class="say" onsubmit={(e) => { e.preventDefault(); transmit(); }}>
      <span class="muted small">Передать как</span>
      <select class="field" bind:value={say.station} aria-label="Станция">
        {#each stations as s (s.id)}<option value={s.id}>{s.name}{s.kind === "character" ? " (персонаж)" : ""}</option>{:else}<option value={0}>нет станций</option>{/each}
      </select>
      <input class="field mono freq" bind:value={say.freq} aria-label="Частота" />
      <input class="field grow" bind:value={say.text} maxlength="280" placeholder={stations.length ? "Текст передачи" : "Сначала заведите станцию на вкладке «Частоты»"} aria-label="Текст" />
      <button class="btn primary" disabled={!stations.length || !say.text.trim()}>Передать</button>
    </form>
  {:else if current === "callsigns"}
    <div class="bar"><label class="find"><Icon name="search" size={14} /><input placeholder="Позывной или игрок" bind:value={sq} aria-label="Поиск позывного" /></label></div>
    <table class="table">
      <thead><tr><th>Позывной</th><th>Игрок</th><th>Состояние</th><th>Прежние</th><th></th></tr></thead>
      <tbody>
        {#each signs as s (s.player.id)}
          <tr>
            <td class="mono">
              {#if renaming === s.player.id}
                <form onsubmit={(e) => { e.preventDefault(); sign(s.player.id, { name: newName }, "Позывной сменён."); renaming = null; }}>
                  <input class="field mono small" bind:value={newName} maxlength="12" aria-label="Новый позывной" />
                </form>
              {:else}<b>{s.name}</b>{/if}
            </td>
            <td><a href="#/players/{s.player.id}">{s.player.username}</a>{#if s.player.discord && s.player.discord !== s.player.username}<span class="muted small"> · {s.player.discord}</span>{/if}</td>
            <td>
              {#if s.rx_only}<span class="badge warn">только приём</span>{/if}
              {#if muted(s)}<span class="badge warn">заглушён до {when(s.muted_until)}</span>{/if}
              {#if !s.rx_only && !muted(s)}<span class="muted small">в эфире</span>{/if}
            </td>
            <td class="muted small">{s.history.map((h) => `${h.old} → ${h.new}${h.by ? ` (${h.by})` : ""}`).join(", ")}</td>
            <td class="acts">
              <button class="btn ghost small" onclick={() => { renaming = s.player.id; newName = s.name; }}>Сменить</button>
              {#if muted(s)}<button class="btn ghost small" onclick={() => sign(s.player.id, { mute_minutes: 0 }, "Заглушка снята.")}>Снять заглушку</button>
              {:else}<button class="btn ghost small" onclick={() => sign(s.player.id, { mute_minutes: 60 }, "Заглушён на час.")}>Заглушить 1 ч</button>{/if}
              <button class="btn ghost small" onclick={() => sign(s.player.id, { rx_only: !s.rx_only }, s.rx_only ? "Передатчик возвращён." : "Передатчик отобран.")}>{s.rx_only ? "Вернуть передатчик" : "Только приём"}</button>
            </td>
          </tr>
        {:else}
          <tr><td colspan="5" class="muted">Позывных пока нет: он появляется у игрока при первом выходе в эфир.</td></tr>
        {/each}
      </tbody>
    </table>
  {:else if current === "bands"}
    <section class="card">
      <h3>Полосы</h3>
      <p class="muted small">«Зарезервирована»: игроки слушают, но не передают (станции, маяки). «По условию»: слышно только с ключом.</p>
      <table class="table">
        <thead><tr><th>Частоты, МГц</th><th>Вид</th><th>Ключ</th><th>Подпись</th><th></th></tr></thead>
        <tbody>
          {#each bands as b (b.id)}
            <tr><td class="mono">{b.low}–{b.high}</td><td>{b.kind === "reserved" ? "зарезервирована" : "по условию"}</td>
              <td class="mono">{typeof b.condition === "string" ? b.condition : b.condition ? JSON.stringify(b.condition) : "—"}</td><td>{b.label}</td>
              <td><button class="btn ghost small danger" onclick={() => dropBand(b.id)}>Удалить</button></td></tr>
          {:else}<tr><td colspan="5" class="muted">Полос нет: весь диапазон 3–30 МГц открыт.</td></tr>{/each}
        </tbody>
      </table>
      <form class="row" onsubmit={(e) => { e.preventDefault(); addBand(); }}>
        <input class="field mono w8" placeholder="с" bind:value={band.low} aria-label="С частоты" />
        <input class="field mono w8" placeholder="по" bind:value={band.high} aria-label="По частоту" />
        <select class="field" bind:value={band.kind} aria-label="Вид"><option value="reserved">зарезервирована</option><option value="conditional">по условию</option></select>
        {#if band.kind === "conditional"}<input class="field mono" placeholder="ключ (slug)" bind:value={band.condition} aria-label="Ключ" />{/if}
        <input class="field grow" placeholder="подпись" bind:value={band.label} aria-label="Подпись" />
        <button class="btn" disabled={!band.low || !band.high}>+ Полоса</button>
      </form>
    </section>
    <section class="card">
      <h3>Станции и персонажи</h3>
      <p class="muted small">От их имени авторы передают в эфир. Позывной зарезервирован: игрок его не займёт, у игроков он выделен цветом.</p>
      <ul class="stations">
        {#each stations as s (s.id)}
          <li><b class="mono">{s.name}</b><span class="muted small">{s.kind === "character" ? "персонаж" : "станция"}{s.label ? ` · ${s.label}` : ""}</span>
            <button class="btn ghost small danger" onclick={() => dropStation(s.id)}>Удалить</button></li>
        {:else}<li class="muted">Станций нет.</li>{/each}
      </ul>
      <form class="row" onsubmit={(e) => { e.preventDefault(); addStation(); }}>
        <input class="field mono w12" placeholder="ПОЗЫВНОЙ" bind:value={station.name} maxlength="12" aria-label="Позывной" />
        <select class="field" bind:value={station.kind} aria-label="Вид"><option value="station">станция</option><option value="character">персонаж</option></select>
        <input class="field grow" placeholder="подпись для авторов" bind:value={station.label} aria-label="Подпись" />
        <button class="btn" disabled={!station.name.trim()}>+ Станция</button>
      </form>
    </section>
  {:else}
    <ol class="feed">
      {#each reports as r (r.id)}
        <li>
          <span class="t mono">{fmt(r.at)}</span>
          <span class="fq mono">{r.transmission.freq}</span>
          <span class="cs mono" title={who(r.transmission.player)}>{r.transmission.callsign}</span>
          <span class="tx">{r.transmission.text}<span class="muted small"> · жалоба от {r.reporter.username}{r.reason ? `: ${r.reason}` : ""}</span></span>
          <span class="acts">
            <button class="btn small" onclick={() => hideReported(r)}>Скрыть передачу</button>
            <button class="btn ghost small" onclick={() => dismiss(r.id)}>Отклонить</button>
          </span>
        </li>
      {:else}<li class="empty muted">Жалоб нет.</li>{/each}
    </ol>
  {/if}
</div>

<style>
  .tabs { display: flex; gap: 2px; padding: 0 32px; border-bottom: 1px solid var(--line-soft); }
  .tab { display: inline-flex; align-items: center; gap: 6px; padding: 10px 12px; color: var(--muted); border-bottom: 2px solid transparent; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .n { padding: 0 6px; border-radius: 999px; background: var(--warn); color: var(--bg); font-size: 11px; }
  .body { display: flex; flex-direction: column; gap: 12px; padding: 16px 32px 32px; }
  .bar, .row, .say { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .grow { flex: 1; min-width: 160px; }
  .find { display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { width: 240px; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .freq { width: 10ch; flex: none; }
  .row select, .say select { width: auto; flex: none; }
  .row .w8, .row .w12 { flex: none; }
  .w8 { width: 9ch; } .w12 { width: 14ch; }
  .mono { font-family: var(--mono); }
  .feed { list-style: none; margin: 0; padding: 0; border: 1px solid var(--line-soft); border-radius: var(--radius); max-height: calc(100vh - 330px); overflow: auto; }
  .feed li { display: grid; grid-template-columns: 9ch 8ch 12ch minmax(0, 1fr) auto; gap: 12px; align-items: baseline; padding: 6px 12px; border-bottom: 1px solid var(--line-soft); }
  .feed li:hover { background: var(--panel); }
  .feed li.hidden .tx { color: var(--muted); text-decoration: line-through; }
  .feed li.sbx { opacity: 0.65; }
  .feed .empty { display: block; }
  .t { color: var(--muted); font-size: 12px; }
  .fq { border: 0; background: none; padding: 0; color: var(--accent); cursor: pointer; font-size: 12.5px; text-align: left; }
  .cs { overflow: hidden; text-overflow: ellipsis; }
  .cs.station { color: var(--warn); }
  .tx { overflow-wrap: anywhere; }
  .badge { margin-left: 6px; padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .badge.warn { color: var(--warn); }
  .acts { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }
  .feed .acts { opacity: 0; transition: opacity 0.12s; }
  .feed li:hover .acts, .feed li:focus-within .acts { opacity: 1; }
  .small { font-size: 12px; }
  .say { padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .table { width: 100%; border-collapse: collapse; }
  .table th { text-align: left; font-size: 12px; color: var(--muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--line-soft); }
  .table td { padding: 8px; border-bottom: 1px solid var(--line-soft); vertical-align: middle; }
  .card { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .card h3 { margin: 0; font-size: 15px; }
  .card p { margin: 0; }
  .stations { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
  .stations li { display: flex; align-items: center; gap: 10px; }
  .stations li .btn { margin-left: auto; }
</style>
