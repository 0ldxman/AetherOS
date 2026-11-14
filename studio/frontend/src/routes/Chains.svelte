<script lang="ts">
  // Цепочки загадок (engine/chains.py): шаги по порядку, каждый — условие на факты игрока. Воронка: сколько прошли каждый шаг,
  // кто первым, кто стоит на шаге и сколько дней, у каких шагов разрыв (условие требует того, что негде взять).
  import AccessBuilder from "../lib/AccessBuilder.svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Hint from "../lib/Hint.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { canEdit } from "../lib/me.svelte";
  import { toast } from "../lib/toast.svelte";

  let { id }: { id: number | null } = $props();
  type Detail = Schemas["CnDetail"];
  type Form = { slug: string; title: string; note: string; active: boolean; steps: Schemas["CnStep"][] };

  let rows = $state<Schemas["CnRow"][]>([]);
  let chain = $state<Detail | null>(null);
  let form = $state<Form | null>(null);
  let busy = $state(false);
  const editable = canEdit("world");

  async function list() { rows = (await api.GET("/studio/api/world/chains")).data ?? []; }
  async function load(chainId: number | null) {
    chain = null;
    form = null;
    if (chainId === null) return;
    if (Number.isNaN(chainId)) { edit(); return; }          // #/chains/new: новая цепочка
    chain = (await api.GET("/studio/api/world/chains/{chain_id}", { params: { path: { chain_id: chainId } } })).data ?? null;
  }
  $effect(() => { list(); });
  $effect(() => { load(id); });

  function edit() {
    form = chain ? { slug: chain.slug, title: chain.title, note: chain.note, active: chain.active, steps: chain.steps.map((s) => ({ ...s })) }
                 : { slug: "", title: "", note: "", active: true, steps: [{ title: "", condition_text: "", hint: "" }] };
  }
  async function save() {
    if (!form) return;
    busy = true;
    const current: Detail | null = chain;
    const { data: saved, error } = current !== null
      ? await api.PUT("/studio/api/world/chains/{chain_id}", { params: { path: { chain_id: current.id } }, body: form })
      : await api.POST("/studio/api/world/chains", { body: form });
    busy = false;
    if (error || !saved) return toast(problem(error), "error");
    toast("Цепочка сохранена.");
    await list();
    if (current === null) { location.hash = `#/chains/${saved.id}`; return; }
    chain = saved;
    form = null;
  }
  async function remove() {
    if (!chain || !(await ask(`Удалить цепочку «${chain.title}»?`, "Вместе с отметками, кто какой шаг прошёл. Сами загадки не меняются."))) return;
    await api.DELETE("/studio/api/world/chains/{chain_id}", { params: { path: { chain_id: chain.id } } });
    await list();
    location.hash = "#/chains";
  }
  function move(index: number, by: number) {
    if (!form) return;
    const steps = [...form.steps];
    const [step] = steps.splice(index, 1);
    steps.splice(index + by, 0, step);
    form.steps = steps;
  }
  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const when = (iso: string | null | undefined) => { if (!iso) return ""; const d = new Date(iso); return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const days = (value: number) => (value < 1 ? "меньше дня" : `${Math.floor(value)} дн.`);
  const share = (n: number) => (chain && chain.players ? Math.round((n / chain.players) * 100) : 0);
</script>

<ListDetail title="Цепочки">
  {#snippet list()}
    {#each rows as row (row.id)}
      <a class="item" class:on={row.id === id} href="#/chains/{row.id}">
        <b>{row.title}</b><span class="muted small">{row.slug} · шагов {row.steps}{row.active ? "" : " · не следим"}</span>
      </a>
    {:else}
      <p class="muted small pad">Цепочек пока нет.</p>
    {/each}
  {/snippet}
  {#snippet add()}{#if editable}<a class="btn" href="#/chains/new">+ Цепочка</a>{/if}{/snippet}

  {#if form}
    <section class="editor">
      <header class="top"><b class="big">{chain ? "Цепочка" : "Новая цепочка"}</b></header>
      <div class="two">
        <label><span class="label">Название</span><input class="field" bind:value={form.title} placeholder="Ключ BOREAS" /></label>
        <label><span class="label">Имя</span><input class="field mono" bind:value={form.slug} placeholder="boreas" /></label>
      </div>
      <label><span class="label">Заметка автора</span><textarea class="field" rows="2" bind:value={form.note} placeholder="Что задумано, как игроки должны идти"></textarea></label>
      <div class="steps">
        {#each form.steps as step, i (i)}
          <div class="step">
            <div class="num">{i + 1}</div>
            <div class="fields">
              <input class="field" bind:value={step.title} placeholder="Шаг: нашёл записку охраны" aria-label="Название шага" />
              <span class="label">Пройден, когда<Hint text="Условие на факты игрока: ключ (любой его учётки), flag:метка, world:метка. Шаг засчитывается, только если пройдены все до него." /></span>
              <AccessBuilder bind:value={step.condition_text} />
              <input class="field" bind:value={step.hint} placeholder="Где игрок это берёт (для авторов)" aria-label="Подсказка" />
            </div>
            <div class="tools">
              <button class="x" disabled={i === 0} onclick={() => move(i, -1)} aria-label="Выше">↑</button>
              <button class="x" disabled={i === form.steps.length - 1} onclick={() => move(i, 1)} aria-label="Ниже">↓</button>
              <button class="x" onclick={() => (form!.steps = form!.steps.filter((_, j) => j !== i))} aria-label="Убрать шаг">✕</button>
            </div>
          </div>
        {/each}
        <button class="btn ghost small" onclick={() => form!.steps.push({ title: "", condition_text: "", hint: "" })}>+ Шаг</button>
      </div>
      <label class="check"><input type="checkbox" bind:checked={form.active} /> Следить: отмечать, кто какой шаг прошёл</label>
      <div class="actions">
        <button class="btn primary" disabled={busy || !form.title.trim() || !form.slug.trim()} onclick={save}>Сохранить</button>
        <button class="btn ghost" onclick={() => { form = null; if (!chain) location.hash = "#/chains"; }}>Отмена</button>
      </div>
    </section>
  {:else if id === null}
    <p class="muted empty">Цепочка — шаги загадки по порядку. Движок сам видит, кто до какого шага дошёл, где застрял и кто прошёл шаг первым.</p>
  {:else if !chain}
    <p class="muted empty">Загрузка…</p>
  {:else}
    <section class="editor">
      <header class="top">
        <div><b class="big">{chain.title}</b><p class="muted small">{chain.slug} · игроков {chain.players} · прошли целиком {chain.finished.length}{chain.active ? "" : " · не следим"}</p></div>
        <span class="spacer"></span>
        {#if editable}<button class="btn" onclick={edit}>Изменить</button><button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
      </header>
      {#if chain.note}<p class="note">{chain.note}</p>{/if}
      {#each chain.steps as step, i (step.id)}
        {@const row = chain.funnel[i]}
        <div class="block">
          <div class="shead">
            <span class="num">{i + 1}</span><b>{step.title}</b>
            {#each row.breaks as name (name)}<a class="break" href="#/links">разрыв: {name}</a>{/each}
            <span class="spacer"></span>
            <span class="count">{row.reached} из {chain.players}</span>
          </div>
          <div class="bar"><span style:width={`${share(row.reached)}%`}></span></div>
          <div class="meta"><span class="mono">{step.condition_text}</span>{#if step.hint}<span class="muted"> · {step.hint}</span>{/if}</div>
          {#if row.first_player}<div class="small">первым <b>{row.first_player}</b> {when(row.first_at)}</div>{/if}
          {#if row.waiting.length}
            <div class="waiting"><span class="muted small">стоят на этом шаге:</span>
              {#each row.waiting as w (w.player_id)}<a class="who" class:long={w.days >= 3} href="#/players/{w.player_id}">{w.player} · {days(w.days)}</a>{/each}
            </div>
          {/if}
        </div>
      {:else}
        <p class="muted">Шагов нет.</p>
      {/each}
      {#if chain.finished.length}<div class="block"><b>Прошли целиком</b><div class="waiting">{#each chain.finished as name (name)}<span class="who">{name}</span>{/each}</div></div>{/if}
    </section>
  {/if}
</ListDetail>

<style>
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; max-width: 900px; }
  .top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .big { font-size: 18px; }
  .spacer { flex: 1; }
  .empty { padding: 20px; max-width: 520px; }
  .note { margin: 0; white-space: pre-wrap; font-size: 13px; }
  .block { display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .shead { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .num { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--accent-soft); font-size: 12px; flex: none; }
  .count { font-size: 12px; color: var(--muted); }
  .bar { height: 6px; border-radius: 3px; background: var(--line-soft); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
  .meta { font-size: 12.5px; overflow-wrap: anywhere; }
  .small { font-size: 12px; }
  .waiting { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .who { padding: 1px 8px; border-radius: 999px; background: var(--bg); border: 1px solid var(--line-soft); font-size: 12px; color: var(--text); text-decoration: none; }
  .who.long { border-color: var(--warn); color: var(--warn); }
  .break { padding: 1px 7px; border-radius: 999px; font-size: 11.5px; background: color-mix(in srgb, var(--danger) 18%, transparent); color: var(--danger); text-decoration: none; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  label { display: flex; flex-direction: column; gap: 4px; }
  .label { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
  .steps { display: flex; flex-direction: column; gap: 8px; }
  .step { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; padding: 10px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .fields { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .tools { display: flex; flex-direction: column; gap: 2px; }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; }
  .x:disabled { opacity: 0.3; cursor: default; }
  .check { flex-direction: row; align-items: center; gap: 8px; font-size: 13px; }
  .check input { width: auto; }
  .actions { display: flex; gap: 8px; }
</style>
