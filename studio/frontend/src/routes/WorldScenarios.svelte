<script lang="ts">
  // Вкладка «Сценарии» мира: короткие карточки сценариев. Карточка открывает страницу сценария (поток, пульт, журнал).
  // На карточке только то, что нужно без открытия: состояние, ошибки, выключатель, правка и сброс.
  import { onMount } from "svelte";
  import { poll } from "../lib/poll";
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

  const editable = canEdit("world");
  const BIG = 8;                                            // с такого числа сценариев появляется поиск

  let cards = $state<Card[]>([]);
  let loaded = $state(false);
  let failed = $state(false);
  let query = $state("");
  let said = $state("");                                    // для чтеца с экрана: что только что произошло
  let dialog = $state(false);
  let draft = $state({ title: "", slug: "" });
  let slugTouched = $state(false);

  const shown = $derived(cards.filter((c) => !query.trim() || `${c.title} ${c.slug}`.toLowerCase().includes(query.trim().toLowerCase())));
  const totals = $derived({ on: cards.filter((c) => c.active).length, errors: cards.reduce((sum, c) => sum + c.errors, 0) });

  const status = (c: Card) => (!c.active ? { key: "off", text: "Выключен" } : c.running ? { key: "run", text: "Идёт" } : { key: "on", text: "Включён" });
  const errors = (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "ошибка" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "ошибки" : "ошибок"}`;

  async function load() {
    const { data } = await api.GET("/studio/api/world/graphs/panel");
    failed = !data;
    if (data) cards = data;
    loaded = true;
  }

  onMount(() => {
    load();
    return poll(load, 5000);
  });

  async function setActive(card: Card, active: boolean) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/active", { params: { path: { graph_id: card.id } }, body: { active } });
    if (error) toast(problem(error), "error");
    else said = `«${card.title}»: ${active ? "включён" : "выключен"}`;
    await load();
  }

  async function reset(card: Card) {
    const sure = await ask(`Сбросить «${card.title}»?`, "Потоки, ветки, переменные, группы и счёт «По очереди» сотрутся, старты начнутся заново. Что сценарий уже сделал в мире (письма, экраны, теги) и журнал останутся.", "Сбросить");
    if (!sure) return;
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/reset", { params: { path: { graph_id: card.id } } });
    if (error) return toast(problem(error), "error");
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

  const openDialog = () => { draft = { title: "", slug: "" }; slugTouched = false; dialog = true; };
</script>

<PageHead title="Сценарии">
  {#snippet sub()}У каждого сценария одно прохождение на весь мир. Откройте карточку: поток, пульт, журнал.{/snippet}
  {#if cards.length > BIG}
    <label class="find"><Icon name="search" size={14} /><input placeholder="Найти сценарий" bind:value={query} aria-label="Найти сценарий" /></label>
  {/if}
  {#if editable}<button class="btn primary" onclick={openDialog}>+ Сценарий</button>{/if}
</PageHead>

{#if loaded && cards.length}
  <p class="summary muted">Включено {totals.on} из {cards.length}{#if totals.errors} · <span class="bad">{errors(totals.errors)} в сценариях</span>{/if}</p>
{/if}

<p class="sr" aria-live="polite" role="status">{said}</p>

{#if !loaded}
  <p class="muted pad">Загрузка…</p>
{:else if failed}
  <p class="pad">Не удалось загрузить сценарии. <button class="btn" onclick={load}>Повторить</button></p>
{:else if !cards.length}
  <div class="pad empty">
    <p class="muted">Сценариев пока нет. Сценарий — это поведение мира, собранное из нод: что случилось, чего ждать, что сделать.</p>
    {#if editable}<button class="btn primary" onclick={openDialog}>Создать первый сценарий</button>{/if}
  </div>
{:else if !shown.length}
  <div class="pad empty">
    <p class="muted">Ничего не нашлось по «{query}».</p>
    <button class="btn" onclick={() => (query = "")}>Показать все</button>
  </div>
{:else}
  <ul class="cards">
    {#each shown as card (card.id)}
      {@const st = status(card)}
      <li class="card" class:off={!card.active}>
        <div class="top">
          <span class="state {st.key}"><i aria-hidden="true"></i>{st.text}</span>
          {#if card.errors}<span class="errors" title="Ошибки проверки: откройте сценарий в редакторе"><Icon name="alert" size={13} />{errors(card.errors)}</span>{/if}
        </div>
        <h2><a class="title" href="#/world/scenario/{card.id}">{card.title}</a></h2>
        <p class="slug mono muted">{card.slug}</p>
        {#if card.active && card.here.length}<p class="here small muted" title={card.here.join(" · ")}>Сейчас: {card.here.join(" · ")}</p>{/if}
        <footer>
          {#if editable}
            <Switch checked={card.active} label={card.active ? "Вкл" : "Выкл"} onchange={(next) => setActive(card, next)} />
          {/if}
          <span class="spacer"></span>
          <a class="btn ghost" href="#/graphs/{card.id}" aria-label="Редактировать «{card.title}»" title="Открыть в редакторе"><Icon name="pencil" size={14} /></a>
          {#if editable}<button class="btn ghost danger" onclick={() => reset(card)} aria-label="Сбросить «{card.title}»" title="Сбросить сценарий"><Icon name="redo" size={14} /></button>{/if}
        </footer>
      </li>
    {/each}
  </ul>
{/if}

{#if dialog}
  <Dialog title="Новый сценарий" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)}>
    <label class="stack"><span class="label">Название</span><input class="field" bind:value={draft.title} oninput={() => { if (!slugTouched) draft.slug = slugify(draft.title); }} placeholder="Взлом архива" /></label>
    <label class="stack"><span class="label">Имя</span><input class="field mono" bind:value={draft.slug} oninput={() => (slugTouched = true)} placeholder="archive-breach" /></label>
  </Dialog>
{/if}

<style>
  .summary { margin: 0; padding: 10px 32px 0; font-size: 12.5px; }
  .bad { color: var(--danger); }
  .small { font-size: 12px; }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

  .find { display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; height: 32px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel); color: var(--muted); }
  .find input { border: 0; background: transparent; color: var(--text); outline: none; width: 150px; font: inherit; }
  .find:focus-within { border-color: var(--accent); }

  .cards { list-style: none; margin: 0; padding: 14px 32px 32px; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 270px), 1fr)); gap: 12px; }
  .card { position: relative; display: flex; flex-direction: column; gap: 4px; padding: 14px 14px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); transition: border-color 0.12s, background 0.12s; }
  .card:hover { border-color: var(--line); background: var(--panel-2); }
  .card:focus-within { border-color: var(--accent); }
  .card.off .title { color: var(--muted); }
  .top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 20px; }
  .state { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
  .state i { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); }
  .state.on i { background: var(--ok); }
  .state.run { color: var(--text); }
  .state.run i { background: var(--ok); box-shadow: 0 0 0 3px rgba(95, 208, 160, 0.2); }
  .errors { display: inline-flex; align-items: center; gap: 4px; padding: 0 8px; border-radius: 999px; font-size: 11.5px; line-height: 19px; color: var(--danger); background: var(--danger-soft); border: 1px solid rgba(255, 122, 122, 0.35); }
  h2 { margin: 6px 0 0; font-size: 15px; font-weight: 600; line-height: 1.3; }
  .title { color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
  .title::after { content: ""; position: absolute; inset: 0; border-radius: var(--radius); }          /* вся карточка — ссылка */
  .title:focus-visible { outline: none; }
  .card:has(.title:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
  .slug { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .here { margin: 2px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  footer { position: relative; z-index: 1; display: flex; align-items: center; gap: 4px; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--line-soft); }
  .spacer { flex: 1; }
  footer .btn { padding: 0 8px; }

  .pad { padding: 24px 32px; }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; max-width: 560px; }
  .stack { display: flex; flex-direction: column; gap: 4px; }
  .mono { font-family: var(--mono); font-size: 12px; }

  @media (max-width: 720px) {
    .summary, .cards { padding-left: 16px; padding-right: 16px; }
  }
</style>
