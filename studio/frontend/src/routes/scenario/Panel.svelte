<script lang="ts">
  // «Пульт»: плитки управления сценарием. Порядок, ширину и заголовки-разделители автор настраивает сам (режим «Настроить»):
  // плитки переставляются перетаскиванием за ручку или стрелками с клавиатуры. Раскладка хранится у сценария и общая для всех админов.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Icon from "../../lib/Icon.svelte";
  import Switch from "../../lib/Switch.svelte";
  import { toast } from "../../lib/toast.svelte";

  type Tile = Schemas["PnTile"];
  type Control = Schemas["PnControl"];
  let { id, tiles, variables, active, editable, reload }: { id: number; tiles: Tile[]; variables: Record<string, unknown>; active: boolean; editable: boolean; reload: () => Promise<void> } = $props();

  const WIDTHS = [{ w: 3, label: "¼" }, { w: 4, label: "⅓" }, { w: 6, label: "½" }, { w: 12, label: "Вся" }];
  const KINDS: Record<string, string> = { manual: "Кнопка", ctl_switch: "Переключатель", ctl_text: "Текст", ctl_choice: "Выбор", ctl_number: "Число" };

  let local = $state<Tile[]>([]);                         // то, что показано; в режиме настройки не затирается опросом
  let arranging = $state(false);
  let drafts = $state<Record<string, unknown>>({});          // правка, ещё не отправленная
  let players = $state<{ id: number; username: string }[]>([]);
  let player = $state(read(sessionStorage, "studio.world.player", ""));      // от чьего имени запускаются кнопки (проверка); пусто — от мира
  let said = $state("");
  let drag = $state<string | null>(null);
  let saveTimer: ReturnType<typeof setTimeout> | undefined;

  function read<T>(store: Storage, name: string, fallback: T): T {
    try { const raw = store.getItem(name); return raw === null ? fallback : (JSON.parse(raw) as T); } catch { return fallback; }
  }
  $effect(() => { try { sessionStorage.setItem("studio.world.player", JSON.stringify(player)); } catch { /* приватный режим */ } });
  $effect(() => { if (!arranging && !drag) local = tiles; });
  onMount(() => {
    api.GET("/studio/api/players").then(({ data }) => { players = (data ?? []).filter((r) => !r.staff).map((r) => ({ id: r.id, username: r.username })); });
    return () => clearTimeout(saveTimer);
  });

  const playerName = $derived(players.find((p) => String(p.id) === player)?.username ?? "");
  const blocked = $derived(!editable || !active || arranging);
  const label = (c: Control) => c.name || (c.kind === "manual" ? "Запустить" : "без названия");
  const text = (value: unknown) => (typeof value === "string" ? value : value === null || value === undefined ? "" : JSON.stringify(value));
  const key = (c: Control) => c.node;
  const shown = (c: Control) => (key(c) in drafts ? drafts[key(c)] : c.value);
  const names = (t: Tile) => (t.control ? label(t.control) : t.title);
  const varList = $derived(Object.entries(variables));

  async function send(c: Control, value: unknown, done: string) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/control", { params: { path: { graph_id: id } }, body: { node: c.node, player: player ? +player : null, value } });
    delete drafts[key(c)];
    if (error) {
      toast(problem(error), "error");
      said = `${label(c)}: не получилось`;
    } else {
      said = `${label(c)}: ${done}`;
      if (c.kind === "manual") toast(`«${label(c)}»: запущено.`);
    }
    await reload();
  }

  // ---------- раскладка ----------
  async function save(now = false) {
    clearTimeout(saveTimer);
    const run = async () => {
      const body = { tiles: local.map((t) => (t.control ? { node: t.key, title: "", w: t.w } : { node: "", title: t.title, w: 12 })) };
      const { error } = await api.PUT("/studio/api/world/graphs/{graph_id}/layout", { params: { path: { graph_id: id } }, body });
      if (error) { toast(problem(error), "error"); await reload(); }
    };
    if (now) await run(); else saveTimer = setTimeout(run, 350);
  }

  function place(tileKey: string, targetKey: string, after: boolean) {
    const item = local.find((t) => t.key === tileKey);
    if (!item || tileKey === targetKey) return;
    const rest = local.filter((t) => t.key !== tileKey);
    const at = rest.findIndex((t) => t.key === targetKey);
    if (at < 0) return;
    const next = [...rest.slice(0, at + (after ? 1 : 0)), item, ...rest.slice(at + (after ? 1 : 0))];
    if (next.every((t, i) => t.key === local[i].key)) return;
    local = next;
  }

  function startDrag(event: PointerEvent, tile: Tile) {
    if (event.button !== 0) return;
    event.preventDefault();
    drag = tile.key;
    const move = (e: PointerEvent) => {
      const el = document.elementsFromPoint(e.clientX, e.clientY).find((n): n is HTMLElement => n instanceof HTMLElement && !!n.dataset.tile && n.dataset.tile !== drag);
      if (!el) return;
      const box = el.getBoundingClientRect();
      const full = box.width > (el.parentElement?.getBoundingClientRect().width ?? 0) * 0.9;
      place(tile.key, el.dataset.tile!, full ? e.clientY > box.top + box.height / 2 : e.clientX > box.left + box.width / 2);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      drag = null;
      save(true);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  }

  function nudge(event: KeyboardEvent, tile: Tile) {
    const back = event.key === "ArrowUp" || event.key === "ArrowLeft";
    if (!back && event.key !== "ArrowDown" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const at = local.findIndex((t) => t.key === tile.key);
    const to = back ? at - 1 : at + 1;
    if (to < 0 || to >= local.length) return;
    place(tile.key, local[to].key, !back);
    said = `«${names(tile)}»: место ${to + 1} из ${local.length}`;
    save();
  }

  function resize(tile: Tile, w: number) {
    local = local.map((t) => (t.key === tile.key ? { ...t, w } : t));
    said = `«${names(tile)}»: ширина ${WIDTHS.find((x) => x.w === w)?.label}`;
    save();
  }

  function addTitle() {
    local = [...local, { key: `title:new${Date.now()}`, w: 12, title: "Раздел", control: null }];
    save(true);
  }

  function rename(tile: Tile, title: string) {
    local = local.map((t) => (t.key === tile.key ? { ...t, title } : t));
    save();
  }

  function drop(tile: Tile) {
    local = local.filter((t) => t.key !== tile.key);
    said = `Заголовок «${tile.title}» удалён`;
    save(true);
  }

  async function done() {
    arranging = false;
    await save(true);
    await reload();
  }
</script>

<div class="bar">
  {#if players.length}
    <label class="as"><span class="muted small">Нажимать от имени</span>
      <select class="field" bind:value={player} aria-label="Запускать кнопки от имени игрока (для проверки)">
        <option value="">мира (без игрока)</option>
        {#each players as p (p.id)}<option value={String(p.id)}>{p.username}</option>{/each}
      </select>
    </label>
  {/if}
  {#if player}<span class="chip warn">Проверка от имени {playerName || "игрока"} <button class="x" onclick={() => (player = "")} aria-label="Снять: нажимать от имени мира"><Icon name="close" size={12} /></button></span>{/if}
  <span class="spacer"></span>
  {#if editable && local.length}
    {#if arranging}
      <button class="btn" onclick={addTitle}><Icon name="plus" size={14} />Заголовок</button>
      <button class="btn primary" onclick={done}>Готово</button>
    {:else}
      <button class="btn" onclick={() => (arranging = true)}><Icon name="updown" size={14} />Настроить пульт</button>
    {/if}
  {/if}
</div>

<p class="sr" aria-live="polite" role="status">{said}</p>

{#if arranging}
  <p class="hint muted small">Тяните ручку <Icon name="grip" size={12} /> или нажимайте на ней стрелки, чтобы переставить. Ширина — справа в плитке. Изменения сохраняются сразу.</p>
{:else if !local.length}
  <div class="pad"><p class="muted">В сценарии нет нод «Управление». Добавьте в редакторе кнопку, переключатель, текст, выбор или число (Shift+A → Управление): они появятся здесь пультом.</p></div>
{:else if !editable}
  <p class="hint muted small">У вас только просмотр: пульт недоступен.</p>
{:else if !active}
  <p class="hint muted small">Сценарий выключен, пульт не работает. Включите его выключателем вверху страницы.</p>
{/if}

{#if local.length}
  <ul class="grid" class:arranging>
    {#each local as t (t.key)}
      {@const c = t.control}
      <li class="tile" class:head={!c} class:lift={drag === t.key} style="--w:{t.w}" data-tile={t.key}>
        {#if arranging}
          <div class="tools">
            <button class="grip" aria-label="Переместить «{names(t)}»: стрелки меняют место" title="Перетащить" onpointerdown={(e) => startDrag(e, t)} onkeydown={(e) => nudge(e, t)}><Icon name="grip" size={14} /></button>
            {#if c}
              <span class="sizes" role="group" aria-label="Ширина плитки «{names(t)}»">
                {#each WIDTHS as s (s.w)}<button class="size" class:on={t.w === s.w} aria-pressed={t.w === s.w} onclick={() => resize(t, s.w)}>{s.label}</button>{/each}
              </span>
            {:else}
              <button class="btn ghost danger" onclick={() => drop(t)} aria-label="Удалить заголовок «{t.title}»"><Icon name="trash" size={13} /></button>
            {/if}
          </div>
        {/if}

        {#if !c}
          {#if arranging}
            <input class="field name" value={t.title} maxlength="60" aria-label="Название раздела" oninput={(e) => rename(t, e.currentTarget.value)} />
          {:else}
            <h3>{t.title}</h3>
          {/if}
        {:else}
          <div class="head-row"><span class="name" title={label(c)}>{label(c)}</span><span class="kind">{KINDS[c.kind]}</span></div>
          <div class="ctl">
            {#if c.kind === "manual"}
              <button class="btn" disabled={blocked} onclick={() => send(c, null, "запущено")}><Icon name="zap" size={14} />Запустить</button>
            {:else if c.kind === "ctl_switch"}
              <Switch checked={!!shown(c)} label={shown(c) ? "включено" : "выключено"} onchange={(next) => { if (!blocked && c.name) send(c, next, next ? "включено" : "выключено"); }} />
            {:else if c.kind === "ctl_choice"}
              <select class="field" disabled={blocked} value={text(shown(c))} aria-label={label(c)} onchange={(e) => send(c, e.currentTarget.value, e.currentTarget.value)}>
                <option value="" disabled>— не выбрано —</option>
                {#each c.options as o (o)}<option value={o}>{o}</option>{/each}
              </select>
            {:else if c.kind === "ctl_number"}
              <span class="slide">
                <input class="range" type="range" min={c.min ?? 0} max={c.max ?? 100} step={c.step ?? 1} disabled={blocked} aria-label={label(c)} value={Number(shown(c) ?? c.min ?? 0)}
                       oninput={(e) => (drafts[key(c)] = +e.currentTarget.value)} onchange={(e) => send(c, +e.currentTarget.value, String(+e.currentTarget.value))} />
                <output class="num">{Number(shown(c) ?? c.min ?? 0)}</output>
              </span>
            {:else}
              <span class="slide">
                <input class="field" type="text" disabled={blocked} value={text(shown(c))} aria-label={label(c)}
                       oninput={(e) => (drafts[key(c)] = e.currentTarget.value)} onkeydown={(e) => e.key === "Enter" && send(c, e.currentTarget.value, "задано")} />
                <button class="btn" disabled={blocked || !(key(c) in drafts)} onclick={() => send(c, drafts[key(c)], "задано")}>Задать</button>
              </span>
            {/if}
          </div>
        {/if}
      </li>
    {/each}
  </ul>
{/if}

{#if varList.length}
  <section class="vars" aria-label="Переменные сценария">
    <h2>Переменные сценария <span class="muted">{varList.length}</span></h2>
    <dl>
      {#each varList as [name, value] (name)}
        <dt class="mono" title={name}>{name}</dt><dd class="mono" title={text(value)}>{text(value)}</dd>
      {/each}
    </dl>
  </section>
{/if}

<style>
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 14px 32px 0; }
  .spacer { flex: 1; }
  .as { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }
  .chip.warn { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; font-size: 12px; color: var(--warn); background: rgba(242, 198, 109, 0.12); border: 1px solid rgba(242, 198, 109, 0.4); }
  .chip .x { display: inline-flex; padding: 2px; border: 0; background: transparent; color: inherit; cursor: pointer; border-radius: 50%; }
  .chip .x:hover { background: rgba(242, 198, 109, 0.2); }
  .hint { margin: 10px 32px 0; }
  .small { font-size: 12px; }
  .pad { padding: 14px 32px; max-width: 640px; }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

  .grid { list-style: none; margin: 0; padding: 14px 32px 8px; display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 10px; }
  .tile { grid-column: span var(--w); display: flex; flex-direction: column; gap: 8px; min-width: 0; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .tile.head { background: transparent; border: 0; border-bottom: 1px solid var(--line-soft); border-radius: 0; padding: 14px 2px 4px; }
  .tile.head h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .arranging .tile { border-style: dashed; border-color: var(--line); }
  .arranging .tile.head { border-bottom-style: dashed; }
  .tile.lift { opacity: 0.55; border-color: var(--accent); }
  .head-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; min-width: 0; }
  .name { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kind { flex: none; font-size: 11px; color: var(--muted); }
  .ctl { display: flex; align-items: center; min-width: 0; }
  .ctl .field { min-width: 0; width: 100%; }
  .slide { display: flex; align-items: center; gap: 8px; min-width: 0; width: 100%; }
  .range { flex: 1; min-width: 0; }
  .num { min-width: 34px; text-align: right; font-variant-numeric: tabular-nums; }
  .name.field { font-weight: 600; }

  .tools { display: flex; align-items: center; gap: 8px; }
  .grip { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 30px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); color: var(--muted); cursor: grab; touch-action: none; }
  .grip:hover { color: var(--text); background: var(--raise); }
  .grip:active { cursor: grabbing; }
  .sizes { display: inline-flex; margin-left: auto; border: 1px solid var(--line); border-radius: var(--radius-s); overflow: hidden; }
  .size { min-width: 34px; height: 28px; padding: 0 6px; border: 0; border-right: 1px solid var(--line); background: var(--panel-2); color: var(--muted); cursor: pointer; font-size: 12px; }
  .size:last-child { border-right: 0; }
  .size:hover { color: var(--text); background: var(--raise); }
  .size.on { background: var(--accent-soft); color: var(--accent); }

  .vars { margin: 8px 32px 32px; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .vars h2 { margin: 0 0 8px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .vars dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 16px; margin: 0; max-height: 260px; overflow: auto; font-size: 12px; }
  .vars dt, .vars dd { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .vars dd { color: var(--muted); }
  .mono { font-family: var(--mono); }

  @media (max-width: 720px) {
    .bar, .hint { padding-left: 16px; padding-right: 16px; margin-left: 0; margin-right: 0; }
    .grid { padding-left: 16px; padding-right: 16px; }
    .tile { grid-column: span 12; }
    .vars { margin-left: 16px; margin-right: 16px; }
  }
</style>
