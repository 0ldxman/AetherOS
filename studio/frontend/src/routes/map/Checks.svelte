<script lang="ts">
  // Проверка данных карты: что выглядит неправильно. Слева проверки с находками, справа выбранная целиком, каждая находка ведёт
  // к месту, где её чинят. Экран ничего не меняет.
  import { onMount, tick } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import Icon from "../../lib/Icon.svelte";

  type Item = Schemas["MapCheckItem"];
  const PAGE = 50;

  let checks = $state<Schemas["MapCheck"][] | null>(null);
  let busy = $state(false);
  let checkedAt = $state("");
  let level = $state<"" | "error" | "warning" | "info">("");
  let code = $state("");
  let query = $state("");
  let rows = $state<Item[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let more: HTMLElement | undefined = $state();

  const LEVEL: Record<string, { label: string; icon: string; hint: string }> = {
    error: { label: "Ошибки", icon: "alert", hint: "Данные противоречат друг другу: исправить в первую очередь" },
    warning: { label: "Стоит проверить", icon: "alert", hint: "Возможно, так и задумано, но чаще это недоделка" },
    info: { label: "К сведению", icon: "circle", hint: "Не ошибка: заметка о неиспользуемых данных" },
  };
  const HINT: Record<string, { what: string; fix: string }> = {
    "no-owner": { what: "Такие провинции на карте серые: у них нет ни одной записи владения.", fix: "Отдайте их стране на вкладке «Территории» или удалите провинцию, если она не нужна." },
    "outside-life": { what: "Запись стоит на дату, когда страны ещё нет или уже нет.", fix: "Поправьте дату записи или годы жизни страны." },
    "same-day": { what: "Две страны владеют одной провинцией с одной даты: на карте победит случайная.", fix: "Откройте провинцию и удалите лишнюю запись." },
    "dead-owner": { what: "Страна закончилась, а провинция так и осталась за ней.", fix: "Передайте провинцию наследнику с даты окончания." },
    "idle-country": { what: "Страна нигде не используется.", fix: "Удалите её или отдайте ей провинции." },
    "no-label": { what: "У страны есть земли, но на карте нет её названия.", fix: "Добавьте подпись на вкладке «Подписи» или в карточке страны." },
  };

  const counts = $derived(Object.fromEntries((["error", "warning", "info"] as const).map((key) => [key, (checks ?? []).filter((c) => c.level === key).reduce((sum, c) => sum + c.count, 0)])));
  const shown = $derived((checks ?? []).filter((c) => !level || c.level === level));
  const current = $derived(shown.find((c) => c.code === code) ?? null);

  async function run() {
    busy = true;
    checks = (await api.GET("/studio/api/map/checks")).data ?? [];
    busy = false;
    checkedAt = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    if (!shown.some((c) => c.code === code)) code = shown[0]?.code ?? "";
    await fetchRows(true);
  }
  onMount(run);

  // при смене фильтра уровня выбор переходит на первую видимую проверку
  $effect(() => { level; if (checks && !shown.some((c) => c.code === code)) code = shown[0]?.code ?? ""; });

  async function fetchRows(reset: boolean) {
    if (!code) { rows = []; total = 0; return; }
    if (loading) return;
    loading = true;
    const asked = code, text = query;
    const { data } = await api.GET("/studio/api/map/checks/{code}", { params: { path: { code: asked }, query: { q: text, offset: reset ? 0 : rows.length, limit: PAGE } } });
    loading = false;
    if (asked !== code || text !== query) return fetchRows(true);
    rows = reset ? data?.rows ?? [] : [...rows, ...(data?.rows ?? [])];
    total = data?.total ?? 0;
    await tick();
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { code; query; if (!checks) return; clearTimeout(timer); timer = setTimeout(() => fetchRows(true), 150); });

  // список подгружается при прокрутке до его конца
  $effect(() => {
    if (!more) return;
    const watcher = new IntersectionObserver((entries) => { if (entries[0]?.isIntersecting && rows.length < total) fetchRows(false); }, { rootMargin: "200px" });
    watcher.observe(more);
    return () => watcher.disconnect();
  });
</script>

<div class="screen">
  <header class="head">
    <h2>Проверка данных</h2>
    <p class="muted grow">Поиск противоречий в провинциях, странах и владениях. Ничего не меняет.</p>
    {#if checkedAt}<span class="muted small">Проверено в {checkedAt}</span>{/if}
    <button class="btn" onclick={run} disabled={busy}><Icon name="redo" size={14} />{busy ? "Проверяю…" : "Проверить снова"}</button>
  </header>

  {#if checks === null}
    <p class="muted pad">Загрузка…</p>
  {:else if !checks.length}
    <div class="allok"><Icon name="check" size={22} /><div><b>Всё в порядке</b><p class="muted">Замечаний нет: у каждой провинции есть владелец, записи лежат в годах жизни стран.</p></div></div>
  {:else}
    <div class="tiles" role="group" aria-label="Фильтр по уровню">
      {#each ["error", "warning", "info"] as const as key (key)}
        <button class="tile {key}" class:on={level === key} class:zero={!counts[key]} aria-pressed={level === key} title={LEVEL[key].hint} onclick={() => (level = level === key ? "" : key)}>
          <span class="n">{counts[key]}</span><span class="t"><Icon name={LEVEL[key].icon} size={14} />{LEVEL[key].label}</span>
        </button>
      {/each}
    </div>

    <div class="cols">
      <nav class="list" aria-label="Проверки">
        {#each shown as check (check.code)}
          <button class="item {check.level}" class:on={check.code === code} aria-current={check.code === code} onclick={() => (code = check.code)}>
            <span class="mark" aria-label={LEVEL[check.level].label}><Icon name={LEVEL[check.level].icon} size={14} /></span>
            <span class="name">{check.title}</span><span class="cnt">{check.count}</span>
          </button>
        {:else}
          <p class="muted small pad">На этом уровне замечаний нет.</p>
        {/each}
      </nav>

      <section class="detail" aria-live="polite">
        {#if current}
          <div class="dhead">
            <h3>{current.title}</h3>
            <span class="badge {current.level}"><Icon name={LEVEL[current.level].icon} size={12} />{LEVEL[current.level].label}</span>
          </div>
          {#if HINT[current.code]}
            <div class="how"><p><b>Что это.</b> {HINT[current.code].what}</p><p><b>Как чинить.</b> {HINT[current.code].fix}</p></div>
          {/if}
          <label class="find"><Icon name="search" size={14} /><input placeholder="Найти среди находок" bind:value={query} aria-label="Поиск среди находок" /></label>
          <ul class="rows">
            {#each rows as item (item.kind + item.id + item.label)}
              <li>
                <span class="lab">{item.label}</span>
                {#if item.province_id}<a class="go" href="#/map/provinces/{item.province_id}">К провинции<Icon name="link" size={12} /></a>{/if}
                {#if item.country_id}<a class="go" href="#/map/countries/{item.country_id}">К стране<Icon name="link" size={12} /></a>{/if}
              </li>
            {:else}
              <li class="muted small pad">{loading ? "Загрузка…" : "Ничего не нашлось."}</li>
            {/each}
            <li bind:this={more} class="sentinel" aria-hidden="true"></li>
          </ul>
          <p class="muted small foot">Показано {rows.length} из {total}</p>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .screen { display: flex; flex-direction: column; gap: 12px; padding: 18px 24px; height: 100%; min-height: 0; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex: none; }
  h2 { margin: 0; font-size: 18px; }
  p { margin: 0; }
  .grow { flex: 1; }
  .pad { padding: 8px; }
  .small { font-size: 12px; }
  .allok { display: flex; gap: 12px; align-items: center; padding: 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); max-width: 560px; color: var(--ok); }
  .allok b { color: var(--text); }

  .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; flex: none; max-width: 720px; }
  .tile { display: flex; align-items: baseline; gap: 10px; padding: 10px 14px; border: 1px solid var(--line-soft); border-left-width: 3px; border-radius: var(--radius); background: var(--panel); color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .tile:hover { background: var(--panel-2); }
  .tile.on { border-color: var(--accent); background: var(--accent-soft); }
  .tile.error { border-left-color: var(--danger); }
  .tile.warning { border-left-color: var(--warn); }
  .tile.info { border-left-color: var(--line); }
  .tile.zero { opacity: 0.6; }
  .n { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .t { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 13px; }
  .tile:focus-visible, .item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

  .cols { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 14px; flex: 1; min-height: 0; }
  .list { display: flex; flex-direction: column; gap: 2px; overflow: auto; min-height: 0; }
  .item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .item:hover { background: var(--panel-2); }
  .item.on { background: var(--accent-soft); }
  .mark { display: inline-flex; flex: none; }
  .item.error .mark { color: var(--danger); }
  .item.warning .mark { color: var(--warn); }
  .item.info .mark { color: var(--muted); }
  .name { flex: 1; min-width: 0; }
  .cnt { flex: none; padding: 0 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }

  .detail { display: flex; flex-direction: column; gap: 10px; min-height: 0; padding: 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .dhead { display: flex; align-items: center; gap: 10px; flex: none; }
  h3 { margin: 0; font-size: 15px; }
  .badge { display: inline-flex; align-items: center; gap: 5px; padding: 1px 8px; border-radius: 999px; background: var(--raise); font-size: 12px; color: var(--muted); }
  .badge.error { color: var(--danger); }
  .badge.warning { color: var(--warn); }
  .how { display: flex; flex-direction: column; gap: 4px; flex: none; font-size: 13px; }
  .how b { color: var(--muted); font-weight: 600; }
  .find { flex: none; display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); max-width: 360px; }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .rows { list-style: none; margin: 0; padding: 0; flex: 1; min-height: 80px; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .rows li { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-bottom: 1px solid var(--line-soft); }
  .rows li.sentinel { height: 1px; padding: 0; border: 0; }
  .lab { flex: 1; min-width: 0; font-family: var(--mono); font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; }
  .go { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 2px 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); color: var(--text); font-size: 12.5px; }
  .go:hover { border-color: var(--accent); text-decoration: none; background: var(--panel-2); }
  .foot { flex: none; }
  @media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }
</style>
