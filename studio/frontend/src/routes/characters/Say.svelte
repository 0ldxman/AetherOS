<script lang="ts">
  // Персонаж пишет первым: письмо одному игроку, группе по условию или всем; новая тема на форуме; передача в эфир.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import ActionsEditor from "../../lib/ActionsEditor.svelte";
  import type { Act } from "../../lib/engine.svelte";
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import { canEdit } from "../../lib/me.svelte";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  let { character, code, stations, mail }: { character: number; code: string; stations: { id: number; label: string }[]; mail: string[] } = $props();

  const editable = canEdit("characters");
  const DELAYS = [{ v: 0, l: "сразу" }, { v: 5, l: "через 5 мин" }, { v: 20, l: "через 20 мин" }, { v: 60, l: "через час" }, { v: 180, l: "через 3 часа" }, { v: 720, l: "через 12 часов" }, { v: 1440, l: "через сутки" }];

  let channel = $state("mail");
  let audience = $state("player");
  let q = $state("");
  let players = $state<Schemas["ChPlayerPick"][]>([]);
  let sections = $state<Schemas["ChSection"][]>([]);
  let draft = $state({ text: "", subject: "", account: null as number | null, condition: "", section: null as number | null, title: "", freq: "14.230",
                       station: null as number | null, delay: 0, actions: [] as Act[] });
  let busy = $state(false);
  let errors = $state<Record<string, string>>({});

  onMount(async () => {
    sections = (await api.GET("/studio/api/characters/options/sections")).data ?? [];
    if (stations.length) draft.station = stations[0].id;
  });
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    void q; clearTimeout(timer);
    timer = setTimeout(async () => { players = (await api.GET("/studio/api/characters/options/players", { params: { query: { q } } })).data ?? []; }, 200);
  });

  const ready = $derived(!!draft.text.trim() && (channel === "mail" ? !!draft.subject.trim() && (audience !== "player" || !!draft.account) && (audience !== "group" || !!draft.condition.trim())
    : channel === "forum" ? !!draft.section && !!draft.title.trim() : !!draft.freq.trim()));

  async function send() {
    busy = true;
    const actions = draft.actions;
    const { data, error } = await api.POST("/studio/api/characters/{character_id}/say", { params: { path: { character_id: character } }, body: {
      channel, text: draft.text, subject: draft.subject, audience, account: draft.account, condition: draft.condition, section: draft.section,
      title: draft.title, freq: draft.freq, station: draft.station, delay: draft.delay, actions } });
    busy = false;
    if (error || !data) {
      errors = (error as { fields?: Record<string, string> } | undefined)?.fields ?? {};
      return toast(Object.values(errors)[0] ?? problem(error), "error");
    }
    errors = {};
    toast(data.status === "pending" ? `Уйдёт ${when(data.send_at)}.` : data.status === "sent" ? "Отправлено." : `Не ушло: ${data.error}`, data.status === "failed" ? "error" : undefined);
    draft.text = "";
    draft.title = "";
  }
</script>

<section class="say">
  <div class="seg" role="radiogroup" aria-label="Канал">
    {#each [["mail", "Письмо"], ["forum", "Тема на форуме"], ["air", "Передача в эфир"]] as [value, label] (value)}
      <label class:on={channel === value}><input type="radio" bind:group={channel} {value} />{label}</label>
    {/each}
  </div>

  {#if channel === "mail"}
    {#if !mail.length}<p class="error small">У {code} нет почтового адреса: отметьте его на карточке.</p>{:else}<p class="muted small">С адреса {mail[0]}</p>{/if}
    <div class="seg small-seg" role="radiogroup" aria-label="Кому">
      {#each [["player", "Одному игроку"], ["group", "Группе по условию"], ["all", "Всем игрокам"]] as [value, label] (value)}
        <label class:on={audience === value}><input type="radio" bind:group={audience} {value} />{label}</label>
      {/each}
    </div>
    {#if audience === "player"}
      <div class="pick">
        <input class="field" bind:value={q} placeholder="найти игрока по логину" aria-label="Игрок" />
        <select class="field" bind:value={draft.account} aria-label="Учётка">
          <option value={null}>— учётка —</option>
          {#each players as p (p.username)}<optgroup label={p.username}>{#each p.accounts as a (a.id)}<option value={a.id}>{a.label} ({a.mail})</option>{/each}</optgroup>{/each}
        </select>
      </div>
    {:else if audience === "group"}
      <div class="row"><span class="label">Кому: условие по ключам и меткам мира</span><AccessBuilder bind:value={draft.condition} bad={!!errors.condition} />
        {#if errors.condition}<span class="error small">{errors.condition}</span>{/if}</div>
      <p class="muted small">Письмо придёт каждому, у кого условие выполнено, при следующем открытии почты (и позже, когда выполнится).</p>
    {:else}
      <p class="muted small">Письмо придёт каждому игроку при следующем открытии почты, в том числе тем, кто придёт в игру позже.</p>
    {/if}
    <input class="field" bind:value={draft.subject} placeholder="тема письма" aria-label="Тема" />
  {:else if channel === "forum"}
    <select class="field" bind:value={draft.section} aria-label="Раздел"><option value={null}>— раздел —</option>{#each sections as s (s.id)}<option value={s.id}>{s.label}</option>{/each}</select>
    <input class="field" bind:value={draft.title} placeholder="заголовок темы" maxlength="160" aria-label="Заголовок" />
  {:else}
    {#if !stations.length}<p class="error small">У {code} нет позывного: заведите его на карточке.</p>{/if}
    <div class="pick">
      <input class="field mono" bind:value={draft.freq} placeholder="14.230" aria-label="Частота" />
      {#if stations.length > 1}<select class="field" bind:value={draft.station} aria-label="Позывной">{#each stations as s (s.id)}<option value={s.id}>{s.label}</option>{/each}</select>{/if}
    </div>
  {/if}

  <textarea class="field" rows="6" bind:value={draft.text} placeholder="что скажет персонаж"></textarea>
  <div class="acts">
    <ActionsEditor bind:actions={draft.actions} provides={["world", "user"]} addLabel="+ действие при отправке" />
  </div>
  {#if editable}
    <div class="send">
      <select class="field" bind:value={draft.delay} aria-label="Когда">{#each DELAYS as d (d.v)}<option value={d.v}>{d.l}</option>{/each}</select>
      <button class="btn primary" disabled={busy || !ready} onclick={send}>{draft.delay ? "Запланировать" : "Отправить"}</button>
      <span class="muted small">Задержка в игровых минутах. Всё сказанное видно во вкладке «Журнал».</span>
    </div>
  {/if}
</section>

<style>
  .say { display: flex; flex-direction: column; gap: 10px; max-width: 720px; }
  .seg { display: flex; flex-wrap: wrap; gap: 4px; }
  .seg label { display: inline-flex; align-items: center; padding: 4px 12px; border: 1px solid var(--line-soft); border-radius: 999px; color: var(--muted); cursor: pointer; font-size: 13px; }
  .seg label.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .seg input { position: absolute; opacity: 0; pointer-events: none; }
  .seg label:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .pick { display: flex; gap: 8px; }
  .pick .field { flex: 1; min-width: 0; }
  .row { display: flex; flex-direction: column; gap: 4px; }
  .acts { display: flex; flex-direction: column; gap: 6px; }
  .send { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .send .field { width: auto; }
  .small { font-size: 12px; margin: 0; }
  .mono { font-family: var(--mono); }
</style>
