<script lang="ts">
  // Владения: события (записи одной даты и одной страны-получателя, права внутри могут различаться) и плоские записи.
  // Фильтры чипами, проблемы данных, бесконечный скролл, пачки: сменить дату, сменить права, удалить.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import Icon from "../../lib/Icon.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { toast } from "../../lib/toast.svelte";
  import FilterChip from "./FilterChip.svelte";
  import { fieldErrors, NO_COLOR, showDate, today, type Country } from "./shared";

  const SIZE = 80;
  type Row = Schemas["MapOwnershipRow"];
  type Event = Schemas["MapEvent"];
  type View = "events" | "records";

  const VIEW_KEY = "studio.ownView";
  let view = $state<View>((() => { try { return localStorage.getItem(VIEW_KEY) === "records" ? "records" : "events"; } catch { return "events"; } })());
  function setView(next: View) {
    view = next;
    try { localStorage.setItem(VIEW_KEY, next); } catch { /* память браузера может быть закрыта */ }
  }

  // ---------- фильтры ----------
  let q = $state("");
  let country = $state("");
  let role = $state<"to" | "from">("to");
  let after = $state("");
  let before = $state("");
  let flag = $state("");
  let issue = $state("");                                  // early | late | dup
  let sort = $state("-date");
  let countries = $state<Country[]>([]);
  let counts = $state<Schemas["MapProblemCounts"] | null>(null);

  const PROBLEMS: Record<string, string> = { early: "до рождения страны", late: "после распада страны", dup: "дубли на одну дату" };
  const FLAGS: Record<string, string> = { both: "оба права", jure: "только де-юре", facto: "только де-факто" };
  const countryName = $derived(countries.find((c) => String(c.id) === country)?.name ?? "");
  const anyFilter = $derived(!!(q.trim() || country || after || before || flag || issue));
  const problemTotal = $derived(counts ? counts.early + counts.late + counts.dup : 0);

  function reset() {
    q = ""; country = ""; role = "to"; after = ""; before = ""; flag = ""; issue = "";
  }

  const params = () => {
    const found: Record<string, string | number> = { q, flag, problem: issue, role, sort };
    if (country) found.country = +country;
    if (after) found.after = after;
    if (before) found.before = before;
    return found;
  };

  // ---------- загрузка: события или записи, бесконечный скролл ----------
  let events = $state<Schemas["MapEventPage"]>({ total: 0, records: 0, rows: [] });
  let records = $state<Schemas["MapOwnershipPage"]>({ total: 0, rows: [] });
  let loading = $state(false);
  let scroller: HTMLElement | undefined = $state();
  let sentinel: HTMLElement | undefined = $state();
  let generation = 0;
  const loaded = $derived(view === "events" ? events.rows.length : records.rows.length);
  const total = $derived(view === "events" ? events.total : records.total);

  async function fetchPage(offset: number, limit: number) {
    if (view === "events") {
      const query = { ...params(), offset, limit } as never;
      return { events: (await api.GET("/studio/api/map/ownerships/events", { params: { query } })).data ?? null };
    }
    const query = { ...params(), offset, limit } as never;
    return { records: (await api.GET("/studio/api/map/ownerships", { params: { query } })).data ?? null };
  }

  /** Обновить уже загруженное (после правки), не сбрасывая прокрутку. */
  async function refresh() {
    const mine = ++generation;
    const got = await fetchPage(0, Math.min(500, Math.max(SIZE, loaded)));
    if (mine !== generation) return;
    if (got.events) events = got.events;
    if (got.records) records = got.records;
    loadCounts();
  }

  async function more() {
    if (loading || loaded >= total) return;
    loading = true;
    const mine = generation;
    const got = await fetchPage(loaded, SIZE);
    loading = false;
    if (mine !== generation) return;
    if (got.events) events = { ...got.events, rows: [...events.rows, ...got.events.rows] };
    if (got.records) {
      const seen = new Set(records.rows.map((r) => r.id));
      records = { total: got.records.total, rows: [...records.rows, ...got.records.rows.filter((r) => !seen.has(r.id))] };
    }
  }

  async function loadCounts() {
    counts = (await api.GET("/studio/api/map/ownerships/problems")).data ?? null;
  }

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    view; q; country; role; after; before; flag; issue; sort;
    clearTimeout(timer);
    timer = setTimeout(() => {
      events = { total: 0, records: 0, rows: [] };
      records = { total: 0, rows: [] };
      open = {};
      chosenIds = [];
      chosenEvents = {};
      scroller?.scrollTo({ top: 0 });
      refresh();
    }, 200);
  });
  // вид сменили: порядок по умолчанию свой у каждого
  $effect(() => { view; sort = "-date"; });

  $effect(() => {
    if (!sentinel || !scroller) return;
    const watcher = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) more(); }, { root: scroller, rootMargin: "0px 0px 600px 0px" });
    watcher.observe(sentinel);
    return () => watcher.disconnect();
  });
  $effect(() => { loaded; queueMicrotask(() => { if (sentinel && scroller && sentinel.getBoundingClientRect().top < scroller.getBoundingClientRect().bottom + 600) more(); }); });

  onMount(async () => {
    countries = (await api.GET("/studio/api/map/countries")).data ?? [];
    loadCounts();
  });

  // ---------- раскрытие события ----------
  const keyOf = (e: { date: string; country: number }) => `${e.date}|${e.country}`;
  let open = $state<Record<string, { rows: Row[]; total: number } | "loading">>({});

  async function toggle(e: Event) {
    const key = keyOf(e);
    if (open[key]) { delete open[key]; return; }
    open[key] = "loading";
    await loadMembers(e, 0);
  }
  async function loadMembers(e: Event, offset: number) {
    const key = keyOf(e);
    const query = { q, flag, problem: issue, country: e.country, role: "to", after: e.date, before: e.date, sort: "province", offset, limit: 100 } as never;
    const got = (await api.GET("/studio/api/map/ownerships", { params: { query } })).data;
    if (!got) { delete open[key]; return; }
    const had = offset && typeof open[key] === "object" ? (open[key] as { rows: Row[] }).rows : [];
    open[key] = { rows: [...had, ...got.rows], total: got.total };
  }

  // ---------- выбор для пачек ----------
  let chosenIds = $state<number[]>([]);
  let chosenEvents = $state<Record<string, number>>({});          // ключ события → сколько в нём записей
  const selectedCount = $derived(Object.values(chosenEvents).reduce((a, b) => a + b, 0) + chosenIds.length);
  const selection = () => ({
    ids: chosenIds,
    events: Object.keys(chosenEvents).map((key) => { const [date, c] = key.split("|"); return { date, country: +c }; }),
  });
  function pickEvent(e: Event) {
    const key = keyOf(e);
    if (chosenEvents[key] !== undefined) delete chosenEvents[key]; else chosenEvents[key] = e.count;
  }
  function pickRow(r: Row) {
    chosenIds = chosenIds.includes(r.id) ? chosenIds.filter((id) => id !== r.id) : [...chosenIds, r.id];
  }
  const allRecords = $derived(records.rows.length > 0 && records.rows.every((r) => chosenIds.includes(r.id)));
  const allEvents = $derived(events.rows.length > 0 && events.rows.every((e) => chosenEvents[keyOf(e)] !== undefined));
  function toggleAll() {
    if (view === "records") chosenIds = allRecords ? [] : records.rows.map((r) => r.id);
    else if (allEvents) chosenEvents = {};
    else chosenEvents = Object.fromEntries(events.rows.map((e) => [keyOf(e), e.count]));
  }
  const clearChosen = () => { chosenIds = []; chosenEvents = {}; };

  // ---------- пачки: диалоги с предпросмотром ----------
  type Bulk = { kind: "date" | "rights" | "delete"; mode: "date" | "shift"; date: string; shift: number; jure: boolean; facto: boolean };
  let bulk = $state<Bulk | null>(null);
  let preview = $state<Schemas["MapBulkOut"] | null>(null);
  let busy = $state(false);

  function bodyOf(b: Bulk, dry: boolean) {
    const base = { ...selection(), dry_run: dry };
    if (b.kind === "delete") return { ...base, action: "delete" };
    if (b.kind === "date") return { ...base, action: "update", ...(b.mode === "date" ? { date: b.date || null } : { shift_days: b.shift }) };
    return { ...base, action: "update", de_jure: b.jure, de_facto: b.facto };
  }
  function openBulk(kind: Bulk["kind"]) {
    bulk = { kind, mode: "shift", date: today(), shift: 1, jure: true, facto: true };
    preview = null;
  }
  let previewTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const b = bulk;
    if (!b) return;
    JSON.stringify(b);
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => {
      if (!bulk) return;
      const { data } = await api.POST("/studio/api/map/ownerships/bulk", { body: bodyOf($state.snapshot(bulk), true) as never });
      preview = data ?? null;
    }, 250);
  });
  const bulkReady = $derived(!!bulk && (bulk.kind !== "date" || (bulk.mode === "date" ? !!bulk.date : bulk.shift !== 0)) && (bulk.kind !== "rights" || bulk.jure || bulk.facto));

  async function applyBulk() {
    if (!bulk) return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/map/ownerships/bulk", { body: bodyOf($state.snapshot(bulk), false) as never });
    busy = false;
    if (error || !data) return toast(problem(error, "Не получилось."), "error");
    toast(bulk.kind === "delete" ? `Удалено записей: ${data.deleted}.` : `Изменено записей: ${data.changed}${data.conflicts ? `, пропущено: ${data.conflicts}` : ""}.`);
    bulk = null;
    clearChosen();
    open = {};
    refresh();
  }

  // ---------- правка одной записи ----------
  type Editing = { id: number | null; province: number; provinceName: string; country: number; date_from: string; de_jure: boolean; de_facto: boolean };
  let editing = $state<Editing | null>(null);
  let find = $state("");
  let found = $state<Schemas["MapProvinceRow"][]>([]);
  let around = $state<Row[]>([]);                                   // записи выбранной провинции: подсказка «до этого было»
  let errors = $state<Record<string, string[]>>({});

  let findTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const text = find.trim();
    clearTimeout(findTimer);
    if (!editing || editing.province) return;
    findTimer = setTimeout(async () => {
      found = text ? (await api.GET("/studio/api/map/provinces", { params: { query: { q: text, limit: 8 } } })).data?.rows ?? [] : [];
    }, 200);
  });
  $effect(() => {
    const id = editing?.province;
    if (!id) { around = []; return; }
    api.GET("/studio/api/map/ownerships", { params: { query: { province: id, sort: "date", limit: 200 } } }).then(({ data }) => { around = data?.rows ?? []; });
  });
  const hint = $derived.by(() => {
    if (!editing || !editing.province || !editing.date_from) return "";
    const others = around.filter((r) => r.id !== editing!.id);
    const prev = [...others].reverse().find((r) => r.date_from < editing!.date_from);
    const next = others.find((r) => r.date_from > editing!.date_from);
    const parts = [prev ? `до этого: ${prev.country_name} с ${showDate(prev.date_from)}` : "до этого владельца не было", next ? `после: ${next.country_name} с ${showDate(next.date_from)}` : ""];
    return parts.filter(Boolean).join(", ");
  });

  function openNew() {
    editing = { id: null, province: 0, provinceName: "", country: +country || countries[0]?.id || 0, date_from: today(), de_jure: true, de_facto: true };
    find = ""; found = []; errors = {};
  }
  function openEdit(row: Row) {
    editing = { id: row.id, province: row.province, provinceName: `${row.province_name} (${row.province_code})`, country: row.country, date_from: row.date_from, de_jure: row.de_jure, de_facto: row.de_facto };
    find = ""; found = []; errors = {};
  }
  async function submit() {
    if (!editing) return;
    errors = {};
    const body = { province: editing.province, country: editing.country, date_from: editing.date_from, de_jure: editing.de_jure, de_facto: editing.de_facto };
    const { data: out, error } = editing.id === null
      ? await api.POST("/studio/api/map/ownerships", { body })
      : await api.PUT("/studio/api/map/ownerships/{ownership_id}", { params: { path: { ownership_id: editing.id } }, body });
    if (error || !out) { errors = fieldErrors(error); return toast(problem(error, "Не сохранилось."), "error"); }
    toast("Запись сохранена.");
    editing = null;
    open = {};
    refresh();
  }
  async function removeOne(row: Row) {
    if (!(await ask(`Удалить запись «${row.province_name} → ${row.country_name}, ${showDate(row.date_from)}»?`, row.previous ? `Провинция вернётся к ${row.previous.country_name}.` : "У провинции больше не будет владельца на эту дату.", "Удалить"))) return;
    const { error } = await api.DELETE("/studio/api/map/ownerships/{ownership_id}", { params: { path: { ownership_id: row.id } } });
    if (error) return toast(problem(error), "error");
    toast("Запись удалена.");
    open = {};
    refresh();
  }

  const sortFor = (key: string) => {
    const desc = `-${key}`;
    sort = sort === desc ? key : sort === key ? desc : desc;
  };
  const arrow = (key: string) => (sort === key ? "↑" : sort === `-${key}` ? "↓" : "");
  const plural = (n: number, one: string, few: string, many: string) => (n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many);

  function fromsText(e: Event): string {
    const parts = e.froms.map((f) => `${f.name}: ${f.count}`);
    if (e.fresh) parts.push(`без владельца: ${e.fresh}`);
    return parts.join("\n");
  }
</script>

<div class="screen">
  <header class="bar">
    <div class="row1">
      <label class="find"><Icon name="search" size={14} /><input placeholder="Провинция, код или страна" bind:value={q} aria-label="Поиск" /></label>
      <FilterChip label="Страна" value={countryName ? `${countryName} (${role === "to" ? "получила" : "отдала"})` : ""}>
        <select class="field" bind:value={country} aria-label="Страна">
          <option value="">любая</option>
          {#each countries as c (c.id)}<option value={String(c.id)}>{c.name} ({c.code})</option>{/each}
        </select>
        <div class="seg" role="radiogroup" aria-label="Роль страны">
          <button role="radio" aria-checked={role === "to"} class:on={role === "to"} onclick={() => (role = "to")}>получила</button>
          <button role="radio" aria-checked={role === "from"} class:on={role === "from"} onclick={() => (role = "from")}>отдала</button>
        </div>
      </FilterChip>
      <FilterChip label="Период" value={after || before ? `${after ? showDate(after) : "…"} — ${before ? showDate(before) : "…"}` : ""}>
        <label class="lbl">С<input class="field" type="date" bind:value={after} /></label>
        <label class="lbl">По<input class="field" type="date" bind:value={before} /></label>
        <button class="link" onclick={() => { after = ""; before = ""; }}>Сбросить период</button>
      </FilterChip>
      <FilterChip label="Права" value={FLAGS[flag] ?? ""}>
        {#each [["", "любые"], ["both", "оба права"], ["jure", "только де-юре"], ["facto", "только де-факто"]] as [key, label] (key)}
          <label class="opt"><input type="radio" name="flag" value={key} bind:group={flag} /> {label}</label>
        {/each}
      </FilterChip>
      <FilterChip label="Проблемы" value={PROBLEMS[issue] ?? ""}>
        <label class="opt"><input type="radio" name="issue" value="" bind:group={issue} /> все записи</label>
        {#each Object.entries(PROBLEMS) as [key, label] (key)}
          {@const n = counts?.[key as "early" | "late" | "dup"] ?? 0}
          <label class="opt" class:dim={!n}><input type="radio" name="issue" value={key} bind:group={issue} /> {label} <span class="n" class:warn={n > 0}>{n}</span></label>
        {/each}
        <p class="muted small">То же показывает вкладка «Проверка».</p>
      </FilterChip>
      {#if problemTotal && !issue}<button class="alert" onclick={() => (issue = counts && counts.early ? "early" : counts && counts.late ? "late" : "dup")} title="Показать записи с проблемами"><Icon name="alert" size={14} />{problemTotal}</button>{/if}
      {#if anyFilter}<button class="link" onclick={reset}>Сбросить фильтры</button>{/if}
    </div>
    <div class="row2">
      <span class="muted">{#if view === "events"}{events.total} {plural(events.total, "событие", "события", "событий")} · {events.records} {plural(events.records, "запись", "записи", "записей")}{:else}{records.total} {plural(records.total, "запись", "записи", "записей")}{/if}</span>
      <span class="spacer"></span>
      <div class="seg wide" role="radiogroup" aria-label="Вид">
        <button role="radio" aria-checked={view === "events"} class:on={view === "events"} onclick={() => setView("events")}>События</button>
        <button role="radio" aria-checked={view === "records"} class:on={view === "records"} onclick={() => setView("records")}>Записи</button>
      </div>
      <button class="btn" onclick={openNew} disabled={!countries.length}><Icon name="plus" size={14} />Запись</button>
    </div>
  </header>

  <div class="scroller" bind:this={scroller}>
    {#if view === "events"}
      <table>
        <thead><tr>
          <th class="c"><input type="checkbox" checked={allEvents} onchange={toggleAll} aria-label="Выбрать все события" /></th>
          <th class="x"></th>
          <th><button class="sort" onclick={() => sortFor("date")}>Дата {arrow("date")}</button></th>
          <th>Кто → кому</th>
          <th class="r"><button class="sort" onclick={() => sortFor("count")}>Провинций {arrow("count")}</button></th>
          <th>Права<Hint text="Де-юре: по праву, признанные границы. Де-факто: реальный контроль. Внутри одного события у провинций права могут быть разные: тогда рядом с меткой стоит, у скольких она есть." /></th>
        </tr></thead>
        {#each events.rows as e (keyOf(e))}
          {@const key = keyOf(e)}
          {@const members = open[key]}
          <tbody class="ev" class:opened={!!members}>
            <tr class="head" onclick={() => toggle(e)}>
              <td class="c" onclick={(ev) => ev.stopPropagation()}><input type="checkbox" checked={chosenEvents[key] !== undefined} onchange={() => pickEvent(e)} aria-label="Выбрать событие" /></td>
              <td class="x"><span class="caret" class:down={!!members}><Icon name="chevron" size={14} /></span></td>
              <td class="date">{showDate(e.date)}</td>
              <td>
                <span class="who" title={fromsText(e)}>
                  {#if e.froms.length === 1 && !e.fresh}<i style="background:{e.froms[0].color || NO_COLOR}"></i>{e.froms[0].name}
                  {:else if !e.froms.length}<span class="muted">нет владельца</span>
                  {:else}<span class="muted">{e.froms.length + (e.fresh ? 1 : 0)} {plural(e.froms.length + (e.fresh ? 1 : 0), "источник", "источника", "источников")}</span>{/if}
                  <span class="muted arrow">→</span><i style="background:{e.color || NO_COLOR}"></i><b>{e.country_name}</b> <code class="muted">{e.country_code}</code>
                </span>
              </td>
              <td class="r num">{e.count}</td>
              <td>
                {#if e.jure}<span class="tag jure">де-юре{e.jure < e.count ? ` ${e.jure}` : ""}</span>{/if}{#if e.facto}<span class="tag facto">де-факто{e.facto < e.count ? ` ${e.facto}` : ""}</span>{/if}
              </td>
            </tr>
            {#if members}
              {#if members === "loading"}
                <tr class="sub"><td colspan="6" class="muted pad">Загрузка…</td></tr>
              {:else}
                {#each members.rows as r (r.id)}
                  <tr class="sub" onclick={() => openEdit(r)}>
                    <td class="c" onclick={(ev) => ev.stopPropagation()}><input type="checkbox" checked={chosenEvents[key] !== undefined || chosenIds.includes(r.id)} disabled={chosenEvents[key] !== undefined} onchange={() => pickRow(r)} aria-label="Выбрать запись" /></td>
                    <td class="x"></td>
                    <td class="muted small">{r.problem ? "⚠" : ""}</td>
                    <td><b>{r.province_name}</b> <code class="muted">{r.province_code}</code>
                      {#if r.previous}<span class="muted"> · было: <i style="background:{r.previous.color || NO_COLOR}"></i>{r.previous.country_name}</span>{/if}
                      {#if r.problem}<span class="badge">{PROBLEMS[r.problem]}</span>{/if}</td>
                    <td class="r"><button class="icon" onclick={(ev) => { ev.stopPropagation(); removeOne(r); }} aria-label="Удалить запись"><Icon name="close" size={14} /></button></td>
                    <td>{#if r.de_jure}<span class="tag jure">де-юре</span>{/if}{#if r.de_facto}<span class="tag facto">де-факто</span>{/if}</td>
                  </tr>
                {/each}
                {#if members.rows.length < members.total}
                  <tr class="sub"><td colspan="2"></td><td colspan="4"><button class="link" onclick={() => loadMembers(e, members.rows.length)}>Показать ещё ({members.total - members.rows.length})</button></td></tr>
                {/if}
              {/if}
            {/if}
          </tbody>
        {:else}
          <tbody><tr><td colspan="6" class="muted empty">{loading ? "Загрузка…" : anyFilter ? "Под эти фильтры ничего не попало." : "Событий нет."}</td></tr></tbody>
        {/each}
      </table>
    {:else}
      <table>
        <thead><tr>
          <th class="c"><input type="checkbox" checked={allRecords} onchange={toggleAll} aria-label="Выбрать все записи" /></th>
          <th><button class="sort" onclick={() => sortFor("date")}>Дата {arrow("date")}</button></th>
          <th><button class="sort" onclick={() => (sort = sort === "province" ? "-date" : "province")}>Провинция {sort === "province" ? "↑" : ""}</button></th>
          <th>Изменение<Hint text="Прежний владелец → новый, а ниже права записи: де-юре (по праву) и де-факто (реальный контроль)." /></th>
        </tr></thead>
        <tbody>
          {#each records.rows as r (r.id)}
            <tr onclick={() => openEdit(r)}>
              <td class="c" onclick={(ev) => ev.stopPropagation()}><input type="checkbox" checked={chosenIds.includes(r.id)} onchange={() => pickRow(r)} aria-label="Выбрать запись" /></td>
              <td class="date">{showDate(r.date_from)}</td>
              <td><b>{r.province_name}</b> <code class="muted">{r.province_code}</code></td>
              <td>
                <span class="change">
                  <span class="line1">
                    {#if r.previous}<i style="background:{r.previous.color || NO_COLOR}"></i>{r.previous.country_name}{:else}<span class="muted">нет владельца</span>{/if}
                    <span class="muted arrow">→</span>
                    <i style="background:{r.color || NO_COLOR}"></i><b>{r.country_name}</b>
                    {#if r.problem}<span class="badge">{PROBLEMS[r.problem]}</span>{/if}
                  </span>
                  <span class="line2">{#if r.de_jure}<span class="tag jure">де-юре</span>{/if}{#if r.de_facto}<span class="tag facto">де-факто</span>{/if}</span>
                </span>
              </td>
            </tr>
          {:else}
            <tr><td colspan="4" class="muted empty">{loading ? "Загрузка…" : anyFilter ? "Под эти фильтры ничего не попало." : "Записей нет."}</td></tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <div class="sentinel" bind:this={sentinel}></div>
    <footer class="pager"><span class="muted">{#if loading}Загрузка…{:else if total > loaded}Показано {loaded} из {total}{:else if total}Показано всё: {total}{/if}</span></footer>
  </div>

  {#if selectedCount}
    <div class="bulkbar" role="toolbar" aria-label="Действия с выбранным">
      <b>Выбрано: {selectedCount} {plural(selectedCount, "запись", "записи", "записей")}</b>
      <span class="spacer"></span>
      <button class="btn" onclick={() => openBulk("date")}>Сменить дату…</button>
      <button class="btn" onclick={() => openBulk("rights")}>Сменить права…</button>
      <button class="btn danger" onclick={() => openBulk("delete")}>Удалить…</button>
      <button class="link" onclick={clearChosen}>Снять выбор</button>
    </div>
  {/if}
</div>

{#if bulk}
  {@const b = bulk}
  <Dialog title={b.kind === "date" ? "Сменить дату" : b.kind === "rights" ? "Сменить права" : "Удалить записи"} confirm={b.kind === "delete" ? "Удалить" : "Применить"} danger={b.kind === "delete"} {busy}
          disabled={!bulkReady || !preview || (b.kind !== "delete" && preview.changed === 0)} onsubmit={applyBulk} onclose={() => (bulk = null)}>
    <p class="muted small">Записей в выборе: {selectedCount}.</p>
    {#if b.kind === "date"}
      <div class="seg wide" role="radiogroup" aria-label="Способ">
        <button type="button" role="radio" aria-checked={b.mode === "shift"} class:on={b.mode === "shift"} onclick={() => (b.mode = "shift")}>Сдвинуть на дни</button>
        <button type="button" role="radio" aria-checked={b.mode === "date"} class:on={b.mode === "date"} onclick={() => (b.mode = "date")}>Новая дата</button>
      </div>
      {#if b.mode === "shift"}
        <label class="lbl">Дней (минус: раньше)<input class="field" type="number" bind:value={b.shift} /></label>
      {:else}
        <label class="lbl">Новая дата<input class="field" type="date" bind:value={b.date} /></label>
      {/if}
    {:else if b.kind === "rights"}
      <label class="opt"><input type="checkbox" bind:checked={b.jure} /> де-юре</label>
      <label class="opt"><input type="checkbox" bind:checked={b.facto} /> де-факто</label>
      {#if !b.jure && !b.facto}<p class="err">Нужно оставить хотя бы одно право.</p>{/if}
    {:else}
      <p class="muted">Провинции вернутся к прежним владельцам по более ранним записям.</p>
    {/if}
    {#if preview}
      <div class="preview" class:bad={preview.conflicts > 0}>
        {#if b.kind === "delete"}Будет удалено записей: <b>{preview.deleted}</b>.
        {:else}Будет изменено: <b>{preview.changed}</b> из {preview.matched}.{#if preview.conflicts} Будет пропущено: <b>{preview.conflicts}</b>.{/if}{/if}
        {#each preview.examples as text}<div class="small">{text}</div>{/each}
      </div>
    {:else}<p class="muted small">Считаю…</p>{/if}
  </Dialog>
{/if}

{#if editing}
  {@const draft = editing}
  <Dialog title={draft.id === null ? "Новая запись владения" : "Запись владения"} confirm="Сохранить" onsubmit={submit} onclose={() => (editing = null)} disabled={!draft.province || !draft.country || !draft.date_from}>
    <div class="who2">
      <span class="label">Провинция</span>
      {#if draft.province}<div class="picked"><b>{draft.provinceName}</b><button type="button" class="btn ghost" onclick={() => { draft.province = 0; draft.provinceName = ""; find = ""; }}>сменить</button></div>
      {:else}
        <input class="field" placeholder="Название или код провинции…" bind:value={find} />
        {#each found as p (p.id)}
          <button type="button" class="pick" onclick={() => { draft.province = p.id; draft.provinceName = `${p.name} (${p.code})`; found = []; }}>{p.name} <code class="muted">{p.code}</code></button>
        {/each}
      {/if}
    </div>
    <label><span class="label">Страна</span>
      <select class="field" bind:value={draft.country}>{#each countries as c (c.id)}<option value={c.id}>{c.name} ({c.code})</option>{/each}</select></label>
    <label><span class="label">С даты</span><input class="field" type="date" bind:value={draft.date_from} /></label>
    {#if hint}<p class="muted small">{hint}</p>{/if}
    <label class="opt"><input type="checkbox" bind:checked={draft.de_jure} /> де-юре</label>
    <label class="opt"><input type="checkbox" bind:checked={draft.de_facto} /> де-факто</label>
    {#each Object.values(errors).flat() as text}<p class="err">{text}</p>{/each}
  </Dialog>
{/if}

<style>
  .screen { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .bar { flex: none; display: flex; flex-direction: column; gap: 10px; padding: 12px 20px; border-bottom: 1px solid var(--line-soft); background: var(--bg); }
  .row1, .row2 { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; }
  .spacer { flex: 1; }
  .find { display: flex; align-items: center; gap: 8px; width: 280px; height: 30px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: var(--panel); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .alert { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border: 1px solid transparent; border-radius: 999px; background: rgba(242, 198, 109, 0.14); color: var(--warn); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
  .link { padding: 0; border: 0; background: none; color: var(--accent); font: inherit; font-size: 12.5px; cursor: pointer; }
  .link:hover { text-decoration: underline; }
  .seg { display: inline-flex; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 4px 12px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .seg.wide button { padding: 5px 16px; }
  .lbl { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: var(--muted); }
  .opt { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .opt.dim { color: var(--faint); }
  .n { margin-left: auto; padding: 0 7px; border-radius: 999px; background: var(--panel-2); color: var(--muted); font-size: 11.5px; }
  .n.warn { background: rgba(242, 198, 109, 0.16); color: var(--warn); }
  .small { font-size: 12px; margin: 0; }

  .scroller { flex: 1; min-height: 0; overflow: auto; }
  table { border-collapse: collapse; width: 100%; }
  thead th { position: sticky; top: 0; z-index: 2; background: var(--bg); text-align: left; padding: 8px 14px; font-weight: 500; color: var(--muted); font-size: 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
  td { padding: 7px 14px; border-bottom: 1px solid var(--line-soft); vertical-align: middle; }
  .c { width: 34px; }
  .x { width: 26px; padding-left: 0; padding-right: 0; }
  .r { text-align: right; }
  .num { font-variant-numeric: tabular-nums; }
  .date { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .sort { padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
  .sort:hover { color: var(--text); }
  tr.head, tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--panel); }
  tbody.opened tr.head { background: var(--panel); }
  tr.sub { background: color-mix(in srgb, var(--panel) 55%, transparent); }
  tr.sub td { padding-top: 5px; padding-bottom: 5px; }
  .caret { display: inline-flex; color: var(--muted); transform: rotate(-90deg); transition: transform 0.12s; }
  .caret.down { transform: none; }
  .who { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  td i { margin-right: 4px; }
  .arrow { margin: 0 4px; }
  .change { display: flex; flex-direction: column; gap: 3px; }
  .line1 { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .line1 i { margin-right: 4px; }
  .line2 { display: flex; gap: 6px; }
  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; border: 1px solid rgba(255, 255, 255, 0.2); }
  code { font-family: var(--mono); font-size: 12px; }
  .tag { padding: 0 8px; margin-right: 6px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
  .tag.jure { background: rgba(122, 162, 255, 0.16); color: var(--accent); }
  .tag.facto { background: rgba(242, 198, 109, 0.16); color: var(--warn); }
  .badge { margin-left: 8px; padding: 0 8px; border-radius: 999px; background: rgba(255, 122, 122, 0.12); color: var(--danger); font-size: 11.5px; }
  .icon { display: inline-grid; place-items: center; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px; background: none; color: var(--muted); cursor: pointer; }
  .icon:hover { background: var(--raise); color: var(--danger); }
  .pad { padding: 10px 14px; }
  .empty { padding: 28px; text-align: center; }
  .sentinel { height: 1px; }
  .pager { display: flex; justify-content: center; padding: 14px; }

  .bulkbar { flex: none; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 20px; border-top: 1px solid var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--panel)); }
  .preview { padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); font-size: 13px; }
  .preview.bad { border-color: var(--warn); }
  .preview .small { color: var(--warn); margin-top: 4px; }
  .who2 { display: flex; flex-direction: column; gap: 4px; }
  .picked { display: flex; align-items: center; justify-content: space-between; }
  .pick { text-align: left; padding: 6px 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); color: var(--text); font: inherit; cursor: pointer; }
  .pick:hover { background: var(--raise); }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
  @media (prefers-reduced-motion: reduce) { .caret { transition: none; } }
</style>
