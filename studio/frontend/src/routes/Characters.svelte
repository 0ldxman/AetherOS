<script lang="ts">
  // Персонажи: одно лицо во всех каналах. Слева список с кодами, справа карточка: имя, код, позывной, кто ведёт, каналы, голос и знания.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Hint from "../lib/Hint.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { canAct, canEdit } from "../lib/me.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import Inbox from "./characters/Inbox.svelte";

  let { id, tab = "card" }: { id: number | null; tab?: string } = $props();
  const TABS = [{ key: "card", label: "Карточка" }, { key: "mail", label: "Почта" }, { key: "forum", label: "Форум" }, { key: "air", label: "Эфир" }];
  let counts = $state<Record<string, number>>({});
  let newStation = $state({ name: "", kind: "character" });

  type Form = Schemas["ChIn"];
  const editable = canEdit("characters");
  const STATUS: Record<string, string> = { active: "Активен", silent: "Молчит", missing: "Пропал", dead: "Мёртв" };
  const COLORS = ["var(--accent)", "var(--ok, #3fb950)", "var(--warn, #d29922)", "var(--info, #58a6ff)"];

  let rows = $state<Schemas["ChRow"][]>([]);
  let options = $state<Schemas["ChOptions"] | null>(null);
  let form = $state<Form | null>(null);
  let saved = $state("");
  let errors = $state<Record<string, string>>({});
  let busy = $state(false);
  let loaded = $state(false);
  const dirty = $derived(form !== null && JSON.stringify(form) !== saved);

  const blank = (): Form => ({ name: "", code: "", callsign: "", color: 0, status: "active", about: "", voice: "", knows: "", note: "", owner_id: null, personas: [], stations: [] });
  const fill = (c: Schemas["ChOut"]): Form => ({ name: c.name, code: c.code, callsign: c.callsign, color: c.color, status: c.status, about: c.about, voice: c.voice,
    knows: c.knows, note: c.note, owner_id: c.owner_id ?? null, personas: [...c.personas], stations: [...c.stations] });

  async function loadList() {
    rows = (await api.GET("/studio/api/characters")).data ?? [];
    options = (await api.GET("/studio/api/characters/options")).data ?? null;
    loaded = true;
  }
  async function load() {
    errors = {};
    if (id === null) { form = null; return; }
    if (id === 0) { form = blank(); saved = JSON.stringify(form); return; }
    const { data } = await api.GET("/studio/api/characters/{character_id}", { params: { path: { character_id: id } } });
    if (!data) { toast("Персонаж не найден.", "error"); return; }
    form = fill(data);
    saved = JSON.stringify(form);
    counts = data.inbox;
  }
  async function refreshCounts() {
    if (!id) return;
    const { data } = await api.GET("/studio/api/characters/{character_id}", { params: { path: { character_id: id } } });
    if (data) counts = data.inbox;
  }
  async function addStation() {
    if (!id || !form) return;
    const { data, error } = await api.POST("/studio/api/characters/{character_id}/stations", { params: { path: { character_id: id } }, body: newStation });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string> } | undefined)?.fields ?? {};
      return toast(Object.values(errors)[0] ?? problem(error), "error");
    }
    errors = {};
    newStation = { name: "", kind: "character" };
    form.stations = [...data.stations];
    if (!form.callsign) form.callsign = data.callsign;
    saved = JSON.stringify({ ...JSON.parse(saved), stations: data.stations, callsign: data.callsign });
    await loadList();
    toast("Позывной заведён.");
  }
  onMount(async () => {
    await loadList();
    if (id === null && rows.length) return go(`/characters/${rows[0].id}`);
    await load();
  });

  async function save() {
    if (!form) return;
    busy = true;
    const result = id === 0
      ? await api.POST("/studio/api/characters", { body: form })
      : await api.PUT("/studio/api/characters/{character_id}", { params: { path: { character_id: id! } }, body: form });
    busy = false;
    if (result.error || !result.data) {
      errors = (result.error as { fields?: Record<string, string> } | undefined)?.fields ?? {};
      return toast(Object.values(errors)[0] ?? problem(result.error), "error");
    }
    errors = {};
    form = fill(result.data);
    saved = JSON.stringify(form);
    toast("Сохранено.");
    await loadList();
    if (id === 0) go(`/characters/${result.data.id}`);
  }
  async function remove() {
    if (!form || !id) return;
    if (!(await ask(`Удалить персонажа «${form.name}»?`, "Адреса почты и позывные останутся, но отвяжутся от него. Сообщения на форуме сохранят подпись.", "Удалить персонажа"))) return;
    const { error } = await api.DELETE("/studio/api/characters/{character_id}", { params: { path: { character_id: id } } });
    if (error) return toast(problem(error), "error");
    await loadList();
    go(rows.length ? `/characters/${rows[0].id}` : "/characters");
  }
  function toggle(list: number[], value: number) {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }
  const takenBy = (character: number | null | undefined) => (character && character !== id ? rows.find((r) => r.id === character) : null);
</script>

<ListDetail title="Персонажи">
  {#snippet list()}
    {#each rows as row (row.id)}
      <a class="item" class:on={row.id === id} href={`#/characters/${row.id}`}>
        <span class="line"><span class="code" style:--c={COLORS[row.color]}>{row.code}</span><span class="name">{row.name}</span></span>
        <span class="muted small">{[...row.mail, ...row.air].join(" · ") || "без каналов"}{row.status !== "active" ? ` · ${STATUS[row.status].toLowerCase()}` : ""}</span>
      </a>
    {:else}
      {#if loaded}<p class="muted small pad-s">Персонажей пока нет.</p>{/if}
    {/each}
  {/snippet}
  {#snippet add()}
    {#if editable}<button class="btn" onclick={() => go("/characters/0")}>+ Персонаж</button>{/if}
  {/snippet}

  {#if id === null}
    <div class="pad"><h2>Персонажи</h2><p class="muted">Персонаж — одно лицо мира во всех каналах: почтовый адрес, позывной в эфире, подпись на форуме. Карточка нужна, чтобы разные авторы говорили за него одним голосом.</p></div>
  {:else if !form}
    <p class="muted pad">Загрузка…</p>
  {:else}
    <section class="editor">
      <header class="head">
        <span class="code big" style:--c={COLORS[form.color]}>{form.code || "???"}</span>
        <input class="title" bind:value={form.name} placeholder="Имя персонажа" aria-label="Имя" disabled={!editable || (!!id && tab !== "card")} />
        <span class="spacer"></span>
        {#if !id || tab === "card"}
          {#if id && canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
          <button class="btn primary" disabled={!dirty || busy || !editable || !form.name.trim()} onclick={save}>{id === 0 ? "Создать" : "Сохранить"}</button>
        {/if}
      </header>
      {#if errors.name}<p class="error small">{errors.name}</p>{/if}
      {#if id}
        <nav class="tabs" aria-label="Разделы персонажа">
          {#each TABS as t (t.key)}
            <a class="tab" class:on={tab === t.key} href={`#/characters/${id}${t.key === "card" ? "" : "/" + t.key}`}>{t.label}{#if t.key !== "card" && counts[t.key]}<span class="count">{counts[t.key]}</span>{/if}</a>
          {/each}
        </nav>
      {/if}
      {#if id && tab !== "card"}
        {#key tab}<Inbox character={id} channel={tab} onchange={refreshCounts} />{/key}
      {:else}

      <div class="grid">
        <label class="row"><span class="label">Код<Hint text="Три знака: бейдж отправителя на форуме и в ленте кукловода. Пусто при создании: из имени." /></span>
          <input class="field mono" bind:value={form.code} maxlength="3" placeholder="авто" disabled={!editable} />{#if errors.code}<span class="error small">{errors.code}</span>{/if}</label>
        <label class="row"><span class="label">Позывной<Hint text="Подпись в эфире и на форуме, например OPERATOR-7. Пусто: имя." /></span>
          <input class="field mono" bind:value={form.callsign} maxlength="16" disabled={!editable} />{#if errors.callsign}<span class="error small">{errors.callsign}</span>{/if}</label>
        <div class="row"><span class="label">Цвет кода</span>
          <div class="swatches">{#each COLORS as color, n (n)}<button type="button" class="swatch" class:on={form.color === n} style:--c={color} aria-label={`Цвет ${n + 1}`} onclick={() => (form!.color = n)} disabled={!editable}></button>{/each}</div></div>
        <label class="row"><span class="label">Статус</span>
          <select class="field" bind:value={form.status} disabled={!editable}>{#each Object.entries(STATUS) as [value, label] (value)}<option {value}>{label}</option>{/each}</select></label>
        <label class="row"><span class="label">Ведёт<Hint text="Автор, которому идут входящие персонажа в панели кукловода. Пусто: всем авторам." /></span>
          <select class="field" bind:value={form.owner_id} disabled={!editable}><option value={null}>— все авторы —</option>{#each options?.authors ?? [] as a (a.id)}<option value={a.id}>{a.username}</option>{/each}</select>
          {#if errors.owner_id}<span class="error small">{errors.owner_id}</span>{/if}</label>
      </div>

      <div class="channels">
        <div class="row"><span class="label">Почтовые адреса<Hint text="Адреса персонажей почты: письма на них и ответы по сценариям идут от этого лица." /></span>
          <div class="checks">
            {#each options?.personas ?? [] as p (p.id)}
              {@const other = takenBy(p.character)}
              <label class="check"><input type="checkbox" checked={form.personas.includes(p.id)} onchange={() => (form!.personas = toggle(form!.personas, p.id))} disabled={!editable} />
                <span class="mono">{p.label}</span>{#if other}<span class="muted small">сейчас у {other.code}</span>{/if}</label>
            {:else}<span class="muted small">Адресов нет: их заводят в разделе «Почта».</span>{/each}
          </div></div>
        <div class="row"><span class="label">Позывные в эфире<Hint text="Станции эфира: передачи от них идут от этого лица." /></span>
          <div class="checks">
            {#each options?.stations ?? [] as s (s.id)}
              {@const other = takenBy(s.character)}
              <label class="check"><input type="checkbox" checked={form.stations.includes(s.id)} onchange={() => (form!.stations = toggle(form!.stations, s.id))} disabled={!editable} />
                <span class="mono">{s.label}</span>{#if other}<span class="muted small">сейчас у {other.code}</span>{/if}</label>
            {:else}<span class="muted small">Позывных пока нет.</span>{/each}
          </div>
          {#if editable && id}
            <form class="newstation" onsubmit={(e) => { e.preventDefault(); addStation(); }}>
              <input class="field mono" placeholder="НОВЫЙ ПОЗЫВНОЙ" bind:value={newStation.name} maxlength="12" aria-label="Новый позывной" />
              <select class="field" bind:value={newStation.kind} aria-label="Вид"><option value="character">говорит сам</option><option value="station">станция, маяк</option></select>
              <button class="btn" disabled={!newStation.name.trim()}>Завести</button>
            </form>
            {#if errors.station}<span class="error small">{errors.station}</span>{/if}
          {:else if id === 0}<span class="muted small">Позывной можно завести после создания персонажа.</span>{/if}
        </div>
      </div>

      <label class="row"><span class="label">Кто это</span><textarea class="field" rows="3" bind:value={form.about} disabled={!editable}></textarea></label>
      <label class="row"><span class="label">Как говорит<Hint text="Манера, длина фраз, слова-паразиты, чего он никогда не скажет." /></span><textarea class="field" rows="3" bind:value={form.voice} disabled={!editable}></textarea></label>
      <label class="row"><span class="label">Что знает и чего не знает<Hint text="Чтобы автор не проговорился: что персонажу известно на текущем акте." /></span><textarea class="field" rows="3" bind:value={form.knows} disabled={!editable}></textarea></label>
      <label class="row"><span class="label">Заметка</span><textarea class="field" rows="2" bind:value={form.note} disabled={!editable}></textarea></label>
      {/if}
    </section>
  {/if}
</ListDetail>

<style>
  .pad { padding: 20px 32px; max-width: 560px; }
  .pad-s { padding: 4px 10px; }
  .small { font-size: 12px; }
  .line { display: flex; align-items: baseline; gap: 8px; }
  .name { font-weight: 600; }
  .code { padding: 0 5px; border: 1px solid var(--c); border-radius: var(--radius-s); color: var(--c); font-family: var(--mono); font-size: 11px; font-weight: 700; letter-spacing: 0.08em; }
  .code.big { padding: 2px 8px; font-size: 14px; }
  .editor { display: flex; flex-direction: column; gap: 14px; max-width: 1000px; padding: 18px 28px 40px; }
  .head { display: flex; align-items: center; gap: 10px; }
  .title { flex: 1; min-width: 0; padding: 6px 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; font-size: 18px; font-weight: 600; }
  .title:hover, .title:focus { border-color: var(--line-soft); background: var(--bg); outline: none; }
  .spacer { flex: 1; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px 16px; }
  .row { display: flex; flex-direction: column; gap: 4px; margin: 0; }
  .channels { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .checks { display: flex; flex-direction: column; gap: 4px; max-height: 180px; overflow: auto; }
  .check { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
  .swatches { display: flex; gap: 6px; padding-top: 4px; }
  .swatch { width: 22px; height: 22px; border: 2px solid transparent; border-radius: var(--radius-s); background: var(--c); cursor: pointer; }
  .swatch.on { border-color: var(--text); }
  .mono { font-family: var(--mono); }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line-soft); }
  .tab { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-bottom: 2px solid transparent; color: var(--muted); text-decoration: none; }
  .tab.on { border-bottom-color: var(--accent); color: var(--text); }
  .count { min-width: 18px; padding: 0 6px; border-radius: 999px; background: var(--accent); color: var(--bg); font-size: 11px; font-weight: 700; text-align: center; }
  .newstation { display: flex; gap: 6px; margin-top: 6px; }
  .newstation .field { min-width: 0; }
</style>
