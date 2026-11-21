<script lang="ts">
  // Вкладка «Сценарии» мира: у каждого сценария карточка с выключателем, этапами, пультом («Управление») и переменными.
  // Тут же вход в редактор и создание сценария.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Icon from "../lib/Icon.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import Switch from "../lib/Switch.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { canEdit } from "../lib/me.svelte";
  import { slugify } from "../lib/slug";
  import { toast } from "../lib/toast.svelte";

  type Card = Schemas["PnCard"];
  type Control = Schemas["PnControl"];

  const editable = canEdit("world");
  const BIG = 8;                                            // с такого числа сценариев появляется поиск

  // небольшие удобства, живущие в браузере: развёрнутые карточки и игрок для проверки
  const read = <T,>(store: Storage, name: string, fallback: T): T => {
    try { const raw = store.getItem(name); return raw === null ? fallback : (JSON.parse(raw) as T); } catch { return fallback; }
  };
  const write = (store: Storage, name: string, value: unknown) => {
    try { store.setItem(name, JSON.stringify(value)); } catch { /* приватный режим: просто не запомнится */ }
  };

  let cards = $state<Card[]>([]);
  let loaded = $state(false);
  let failed = $state(false);
  let players = $state<{ id: number; username: string }[]>([]);
  let player = $state(read(sessionStorage, "studio.world.player", ""));      // от чьего имени запускаются кнопки (проверка); пусто — от мира
  let open = $state<Record<string, boolean>>(read(localStorage, "studio.world.open", {}));
  let drafts = $state<Record<string, unknown>>({});         // правка, ещё не отправленная: опрос её не затирает
  let query = $state("");
  let said = $state("");                                    // для чтеца с экрана: что только что произошло
  let dialog = $state(false);
  let draft = $state({ title: "", slug: "" });
  let slugTouched = $state(false);

  const playerName = $derived(players.find((p) => String(p.id) === player)?.username ?? "");
  const isOpen = (card: Card) => (String(card.id) in open ? open[String(card.id)] : card.active);
  const key = (card: Card, control: Control) => `${card.id}:${control.node}`;
  const shown = (card: Card, control: Control) => (key(card, control) in drafts ? drafts[key(card, control)] : control.value);
  const text = (value: unknown) => (typeof value === "string" ? value : value === null || value === undefined ? "" : JSON.stringify(value));
  const label = (c: Control) => (c.kind === "manual" ? c.name || "Кнопка" : c.name || "без названия");

  // порядок: включённые выше, из них те, где что-то требует внимания; дальше по названию
  const attention = (card: Card) => card.errors > 0 || card.waiting > 0;
  const shownCards = $derived(
    cards
      .filter((c) => !query.trim() || `${c.title} ${c.slug}`.toLowerCase().includes(query.trim().toLowerCase()))
      .toSorted((a, b) => Number(b.active) - Number(a.active) || Number(attention(b)) - Number(attention(a)) || a.title.localeCompare(b.title, "ru")),
  );
  const totals = $derived({
    on: cards.filter((c) => c.active).length,
    running: cards.reduce((sum, c) => sum + c.running, 0),
    waiting: cards.reduce((sum, c) => sum + c.waiting, 0),
    errors: cards.reduce((sum, c) => sum + c.errors, 0),
  });

  async function load() {
    const { data } = await api.GET("/studio/api/world/graphs/panel");
    failed = !data;
    if (data) cards = data;
    loaded = true;
  }

  onMount(() => {
    load();
    api.GET("/studio/api/players").then(({ data }) => { players = (data ?? []).filter((r) => !r.staff).map((r) => ({ id: r.id, username: r.username })); });
    const tick = () => { if (!document.hidden) load(); };                     // скрытая вкладка браузера не опрашивает
    const timer = setInterval(tick, 5000);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
  });
  $effect(() => write(sessionStorage, "studio.world.player", player));

  function toggle(card: Card) {
    open[String(card.id)] = !isOpen(card);
    write(localStorage, "studio.world.open", open);
  }

  async function send(card: Card, control: Control, value: unknown, done: string) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/control", { params: { path: { graph_id: card.id } }, body: { node: control.node, player: player ? +player : null, value } });
    delete drafts[key(card, control)];
    if (error) {
      toast(problem(error), "error");
      said = `${label(control)}: не получилось`;
    } else {
      said = `${label(control)}: ${done}`;
      if (control.kind === "manual") toast(`«${label(control)}»: запущено.`);
    }
    await load();
  }

  async function setActive(card: Card, active: boolean) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/active", { params: { path: { graph_id: card.id } }, body: { active } });
    if (error) toast(problem(error), "error");
    else said = `«${card.title}»: ${active ? "включён" : "выключен"}`;
    await load();
  }

  async function reset(card: Card) {
    const sure = await ask(`Сбросить «${card.title}»?`, "Потоки, ветки, переменные, группы и счёт «По очереди» сотрутся, старты начнутся заново. Что сценарий уже сделал в мире (письма, экраны, теги), останется.", "Сбросить");
    if (!sure) return;
    const { data, error } = await api.POST("/studio/api/world/graphs/{graph_id}/reset", { params: { path: { graph_id: card.id } } });
    if (error || !data) return toast(problem(error), "error");
    toast(`«${card.title}» начат заново.`);
    said = `«${card.title}» начат заново`;
    await load();
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/world/graphs", { body: { title: draft.title, slug: draft.slug, note: "", active: false, doc: { nodes: [], wires: [] } } });
    if (error || !data) return toast(problem(error), "error");
    dialog = false;
    location.hash = `#/graphs/${data.id}`;
  }

  const top = (card: Card) => Math.max(1, ...card.stages.map((s) => s.hits));
  const blocked = (card: Card) => !editable || !card.active;
</script>

<PageHead title="Сценарии">
  {#snippet sub()}Включить, сбросить, посмотреть этапы и управлять пультом.{/snippet}
  {#if cards.length > BIG}
    <label class="find"><Icon name="search" size={14} /><input placeholder="Найти сценарий" bind:value={query} aria-label="Найти сценарий" /></label>
  {/if}
  {#if players.length}
    <label class="as"><span class="muted small">Тест от имени</span>
      <select class="field" bind:value={player} aria-label="Запускать кнопки от имени игрока (для проверки)">
        <option value="">мира (без игрока)</option>
        {#each players as p (p.id)}<option value={String(p.id)}>{p.username}</option>{/each}
      </select>
    </label>
  {/if}
  {#if editable}<button class="btn primary" onclick={() => { draft = { title: "", slug: "" }; slugTouched = false; dialog = true; }}>+ Сценарий</button>{/if}
</PageHead>

{#if loaded && cards.length}
  <div class="summary" role="group" aria-label="Сводка">
    <span class="chip">Включено {totals.on} из {cards.length}</span>
    <span class="chip">потоков идёт {totals.running}</span>
    <span class="chip" class:note={totals.waiting > 0}>ждут игроков {totals.waiting}</span>
    {#if totals.errors}<span class="chip bad">ошибок в сценариях {totals.errors}</span>{/if}
    {#if player}
      <span class="chip warn">Кнопки запускаются от имени {playerName || "игрока"}
        <button class="x" onclick={() => (player = "")} aria-label="Снять: запускать от имени мира"><Icon name="close" size={12} /></button>
      </span>
    {/if}
  </div>
{/if}

<p class="sr" aria-live="polite" role="status">{said}</p>

{#if !loaded}
  <p class="muted pad">Загрузка…</p>
{:else if failed}
  <p class="pad">Не удалось загрузить сценарии. <button class="btn" onclick={load}>Повторить</button></p>
{:else if !cards.length}
  <div class="pad empty">
    <p class="muted">Сценариев пока нет. Сценарий — это поведение мира, собранное из нод: что случилось, чего ждать, что сделать.</p>
    {#if editable}<button class="btn primary" onclick={() => { draft = { title: "", slug: "" }; slugTouched = false; dialog = true; }}>Создать первый сценарий</button>{/if}
  </div>
{:else if !shownCards.length}
  <div class="pad empty">
    <p class="muted">Ничего не нашлось по «{query}».</p>
    <button class="btn" onclick={() => (query = "")}>Показать все</button>
  </div>
{:else}
  <div class="cards">
    {#each shownCards as card (card.id)}
      <section class="card" class:off={!card.active} aria-labelledby="t{card.id}">
        <header>
          <button class="fold" aria-expanded={isOpen(card)} aria-controls="b{card.id}" onclick={() => toggle(card)}>
            <Icon name="chevron" size={14} /><span class="title" id="t{card.id}">{card.title}</span>
          </button>
          <span class="muted mono small slug">{card.slug}</span>
          {#if card.errors}<span class="chip bad" title="Ошибки проверки: откройте сценарий в редакторе">ошибок {card.errors}</span>{/if}
          {#if card.waiting}<span class="chip note">ждут {card.waiting}</span>{/if}
          {#if card.running}<span class="chip">потоков {card.running}</span>{/if}
          <span class="spacer"></span>
          {#if editable}
            <Switch checked={card.active} label="Включён" onchange={(next) => setActive(card, next)} />
          {:else}
            <span class="muted small">{card.active ? "Включён" : "Выключен"}</span>
          {/if}
          <a class="btn ghost" href="#/graphs/{card.id}" aria-label="Редактировать сценарий «{card.title}»"><Icon name="pencil" size={14} />Редактировать</a>
          {#if editable}<button class="btn ghost danger" onclick={() => reset(card)} aria-label="Сбросить сценарий «{card.title}»">Сбросить</button>{/if}
        </header>

        {#if isOpen(card)}
          <div class="body" id="b{card.id}">
            {#if card.stages.length}
              <div class="block">
                <h2>Этапы</h2>
                <ul class="stages">
                  {#each card.stages as stage (stage.node)}
                    <li>
                      <span class="name" title={stage.title}>{stage.title}</span>
                      <span class="bar" aria-hidden="true"><i style="width: {Math.round((stage.hits / top(card)) * 100)}%"></i></span>
                      <span class="muted small nums">прошли {stage.hits} · игроков {stage.players}{#if stage.waiting} · <b class="wait">ждут {stage.waiting}</b>{/if}</span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}

            {#if card.controls.length}
              <div class="block">
                <h2>Пульт</h2>
                <div class="controls">
                  {#each card.controls as c (c.node)}
                    <div class="control">
                      <span class="name" title={label(c)}>{c.kind === "manual" ? "Кнопка" : label(c)}</span>
                      {#if c.kind === "manual"}
                        <button class="btn" disabled={blocked(card)} onclick={() => send(card, c, null, "запущено")}>{c.name || "Запустить"}</button>
                      {:else if c.kind === "ctl_switch"}
                        <Switch checked={!!shown(card, c)} label={shown(card, c) ? "включено" : "выключено"} onchange={(next) => { if (!blocked(card) && c.name) send(card, c, next, next ? "включено" : "выключено"); }} />
                      {:else if c.kind === "ctl_choice"}
                        <select class="field" disabled={blocked(card)} value={text(shown(card, c))} aria-label={label(c)} onchange={(e) => send(card, c, e.currentTarget.value, e.currentTarget.value)}>
                          <option value="" disabled>— не выбрано —</option>
                          {#each c.options as o (o)}<option value={o}>{o}</option>{/each}
                        </select>
                      {:else if c.kind === "ctl_number"}
                        <span class="slide">
                          <input class="range" type="range" min={c.min ?? 0} max={c.max ?? 100} step={c.step ?? 1} disabled={blocked(card)} aria-label={label(c)}
                                 value={Number(shown(card, c) ?? c.min ?? 0)}
                                 oninput={(e) => (drafts[key(card, c)] = +e.currentTarget.value)} onchange={(e) => send(card, c, +e.currentTarget.value, String(+e.currentTarget.value))} />
                          <output class="num">{Number(shown(card, c) ?? c.min ?? 0)}</output>
                        </span>
                      {:else}
                        <span class="slide">
                          <input class="field" type="text" disabled={blocked(card)} value={text(shown(card, c))} aria-label={label(c)}
                                 oninput={(e) => (drafts[key(card, c)] = e.currentTarget.value)}
                                 onkeydown={(e) => e.key === "Enter" && send(card, c, e.currentTarget.value, "задано")} />
                          <button class="btn" disabled={blocked(card) || !(key(card, c) in drafts)} onclick={() => send(card, c, drafts[key(card, c)], "задано")}>Задать</button>
                        </span>
                      {/if}
                    </div>
                  {/each}
                </div>
                {#if !editable}<p class="muted small">У вас только просмотр: пульт недоступен.</p>
                {:else if !card.active}<p class="muted small">Сценарий выключен, пульт не работает. Включите его выключателем выше.</p>{/if}
              </div>
            {/if}

            {#if Object.keys(card.variables).length}
              <details class="block">
                <summary>Переменные сценария ({Object.keys(card.variables).length})</summary>
                <div class="vars">
                  {#each Object.entries(card.variables) as [name, value] (name)}
                    <span class="mono" title={name}>{name}</span><span class="mono muted" title={text(value)}>{text(value)}</span>
                  {/each}
                </div>
              </details>
            {/if}

            {#if !card.stages.length && !card.controls.length && !Object.keys(card.variables).length}
              <p class="muted small">В сценарии пока нет этапов и управления. В редакторе добавьте ноды «Этап» и «Управление» (Shift+A).</p>
            {/if}
          </div>
        {/if}
      </section>
    {/each}
  </div>
{/if}

{#if dialog}
  <Dialog title="Новый сценарий" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)}>
    <label class="stack"><span class="label">Название</span><input class="field" bind:value={draft.title} oninput={() => { if (!slugTouched) draft.slug = slugify(draft.title); }} placeholder="Взлом архива" /></label>
    <label class="stack"><span class="label">Имя</span><input class="field mono" bind:value={draft.slug} oninput={() => (slugTouched = true)} placeholder="archive-breach" /></label>
  </Dialog>
{/if}

<style>
  .summary { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 32px 4px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border: 1px solid var(--line-soft); border-radius: 999px; font-size: 12px; color: var(--muted); background: var(--panel); }
  .chip.note { color: var(--text); border-color: var(--line); }
  .chip.bad { color: var(--danger); background: var(--danger-soft); border-color: rgba(255, 122, 122, 0.35); }
  .chip.warn { color: var(--warn); background: rgba(242, 198, 109, 0.12); border-color: rgba(242, 198, 109, 0.4); }
  .chip .x { display: inline-flex; padding: 2px; border: 0; background: transparent; color: inherit; cursor: pointer; border-radius: 50%; }
  .chip .x:hover { background: rgba(242, 198, 109, 0.2); }
  .chip .x:focus-visible { outline: 2px solid var(--accent); }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

  .find { display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; height: 32px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel); color: var(--muted); }
  .find input { border: 0; background: transparent; color: var(--text); outline: none; width: 150px; font: inherit; }
  .find:focus-within { border-color: var(--accent); }
  .as { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }

  .cards { display: flex; flex-direction: column; gap: 10px; padding: 12px 32px 32px; }
  .card { border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .card.off > header .title { color: var(--muted); }
  header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px 12px; }
  .fold { display: inline-flex; align-items: center; gap: 8px; padding: 4px 6px; margin-left: -6px; border: 0; background: transparent; color: var(--text); cursor: pointer; border-radius: var(--radius-s); font: inherit; min-height: 32px; }
  .fold:hover { background: var(--panel-2); }
  .fold:focus-visible { outline: 2px solid var(--accent); }
  .fold :global(svg) { flex: none; transition: transform 0.12s; transform: rotate(-90deg); color: var(--muted); }
  .fold[aria-expanded="true"] :global(svg) { transform: rotate(0); }
  .title { font-size: 15px; font-weight: 600; }
  .slug { overflow: hidden; text-overflow: ellipsis; }
  .spacer { flex: 1; }

  .body { display: flex; flex-direction: column; gap: 16px; padding: 4px 16px 16px 34px; }
  h2 { margin: 0 0 6px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .block { display: flex; flex-direction: column; gap: 6px; }
  .stages { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .stages li { display: grid; grid-template-columns: minmax(120px, 220px) minmax(60px, 1fr) minmax(0, auto); align-items: center; gap: 12px; }
  .name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { height: 6px; border-radius: 3px; background: var(--panel-2); overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--accent); }
  .nums { font-variant-numeric: tabular-nums; }
  .wait { color: var(--warn); font-weight: 600; }

  .controls { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); gap: 8px; }
  .control { display: grid; grid-template-columns: minmax(70px, 130px) minmax(0, 1fr); align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); }
  .control .field { min-width: 0; width: 100%; }
  .slide { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .range { flex: 1; min-width: 0; }
  .num { min-width: 34px; text-align: right; font-variant-numeric: tabular-nums; }
  summary { cursor: pointer; font-size: 12px; color: var(--muted); padding: 2px 0; }
  summary:focus-visible { outline: 2px solid var(--accent); }
  .vars { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 16px; padding-top: 8px; font-size: 12px; max-height: 260px; overflow: auto; }
  .vars span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mono { font-family: var(--mono); }
  .pad { padding: 24px 32px; }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; max-width: 560px; }
  .stack { display: flex; flex-direction: column; gap: 4px; }

  @media (max-width: 720px) {
    .summary, .cards { padding-left: 16px; padding-right: 16px; }
    .body { padding-left: 16px; }
    .stages li { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  }
  @media (prefers-reduced-motion: reduce) { .fold :global(svg) { transition: none; } }
</style>
