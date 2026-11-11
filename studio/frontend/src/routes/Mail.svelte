<script lang="ts">
  // Почта: персонажи мира с адресами и их сценарии переписки. Персонаж правится здесь, сценарий открывается картой шагов.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import DraftState from "../lib/DraftState.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { canAct, canEdit } from "../lib/me.svelte";
  import { go } from "../lib/router.svelte";
  import { SharedForm } from "../lib/shared.svelte";
  import { slugify } from "../lib/slug";
  import { toast } from "../lib/toast.svelte";

  let { id }: { id: number | null } = $props();

  type Form = { address: string; name: string; signature: string; note: string };
  let personas = $state<Schemas["MlPersona"][]>([]);
  let loaded = $state(false);
  let form = $state<Form>({ address: "", name: "", signature: "", note: "" });
  let base = $state<Form | null>(null);
  let saved = $state("");
  let busy = $state(false);
  let dialog = $state<"" | "persona" | "talk">("");
  let draft = $state({ address: "", name: "", title: "", slug: "" });
  let slugTouched = false;

  const editable = canEdit("mail");
  const persona = $derived(personas.find((p) => p.id === id) ?? null);
  const dirty = $derived(saved !== "" && JSON.stringify(form) !== saved);
  guardUnsaved(() => dirty && !share.ready);

  const valuesOf = (p: Schemas["MlPersona"]): Form => ({ address: p.address, name: p.name, signature: p.signature, note: p.note });

  async function load(keepDraft = false) {
    personas = (await api.GET("/studio/api/mail")).data ?? [];
    loaded = true;
    if (id === null && personas.length) return go(`/mail/personas/${personas[0].id}`);
    const p = personas.find((x) => x.id === id);
    if (p) {
      base = valuesOf(p);
      if (!keepDraft) form = valuesOf(p);
      saved = JSON.stringify(valuesOf(p));
    }
  }
  onMount(() => load());

  const share = new SharedForm({ room: () => (id ? `mail/personas/${id}` : ""), texts: ["note", "signature"], draft: () => form, base: () => base, onRemoteSave: () => load(true) });

  async function save() {
    if (!id) return;
    busy = true;
    const { data, error } = await api.PUT("/studio/api/mail/personas/{persona_id}", { params: { path: { persona_id: id } }, body: $state.snapshot(form) });
    busy = false;
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    share.markSaved();
    await load();
    toast("Персонаж сохранён.");
  }

  async function remove() {
    if (!persona) return;
    const n = persona.conversations.length;
    if (!(await ask(`Удалить персонажа ${persona.address}?`, n ? `Вместе с ним удалятся сценарии (${n}).` : "Письма на его адрес будут возвращаться от MAILER-DAEMON.", "Удалить персонажа"))) return;
    const { error } = await api.DELETE("/studio/api/mail/personas/{persona_id}", { params: { path: { persona_id: persona.id } } });
    if (error) return toast(problem(error), "error");
    toast("Персонаж удалён.");
    go("/mail");
    await load();
  }

  async function createPersona() {
    const { data, error } = await api.POST("/studio/api/mail/personas", { body: { address: draft.address, name: draft.name, signature: "", note: "" } });
    if (error || !data) return toast(problem(error, "Не создалось."), "error");
    dialog = "";
    go(`/mail/personas/${data.id}`);
  }

  async function createTalk() {
    if (!persona) return;
    const { data, error } = await api.POST("/studio/api/mail/conversations", { body: { persona: persona.id, title: draft.title, slug: draft.slug } });
    if (error || !data) return toast(problem(error, "Не создалось."), "error");
    dialog = "";
    go(`/mail/${data.id}`);
  }

  function openTalkDialog() {
    draft = { ...draft, title: "", slug: "" };
    slugTouched = false;
    dialog = "talk";
  }
</script>

<ListDetail title="Почта">
  {#snippet list()}
    {#each personas as p (p.id)}
      <a class="item" class:on={p.id === id} href={`#/mail/personas/${p.id}`}>
        <span>{p.name || p.address}</span>
        <span class="muted small">{p.name ? p.address : ""}{p.conversations.length ? `${p.name ? " · " : ""}сценариев ${p.conversations.length}` : ""}</span>
      </a>
    {:else}
      {#if loaded}<p class="muted small pad-s">Персонажей пока нет.</p>{/if}
    {/each}
  {/snippet}
  {#snippet add()}
    {#if editable}<button class="btn" onclick={() => { draft = { ...draft, address: "", name: "" }; dialog = "persona"; }}>+ Персонаж</button>{/if}
  {/snippet}

  {#if !loaded}
    <p class="muted pad">Загрузка…</p>
  {:else if !persona}
    <div class="pad empty">
      <h2>Почта мира</h2>
      <p class="muted">Персонаж это адрес, которому игрок пишет, и сценарии переписки: шаги с письмами персонажа и вариантами ответа игрока.
        Начните с персонажа.</p>
    </div>
  {:else}
    <section class="detail">
      <header class="head">
        <h2>{persona.name || persona.address}</h2>
        <span class="spacer"></span>
        <DraftState {share} {dirty} />
        {#if canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
        <button class="btn primary" disabled={!dirty || busy || !editable} onclick={save}>Сохранить</button>
      </header>

      <div class="grid">
        <label><span class="label">Адрес</span><input class="field mono" bind:value={form.address} disabled={!editable} /></label>
        <label><span class="label">Имя в письмах</span><input class="field" bind:value={form.name} disabled={!editable} placeholder="Harbor security" /></label>
        <label class="wide"><span class="label">Подпись</span><textarea class="field" rows="2" bind:value={form.signature} disabled={!editable}></textarea></label>
        <label class="wide"><span class="label">Заметка автора</span><textarea class="field" rows="3" bind:value={form.note} disabled={!editable} placeholder="Кто это, как игрок узнаёт адрес"></textarea></label>
      </div>

      <div class="talks">
        <div class="talks-head"><h3>Сценарии переписки</h3>{#if editable}<button class="btn" onclick={openTalkDialog}>+ Сценарий</button>{/if}</div>
        {#each persona.conversations as c (c.id)}
          <a class="talk" href={`#/mail/${c.id}`}>
            <b>{c.title}</b>
            <span class="muted mono small">mail {c.slug}</span>
            <span class="muted small">шагов {c.steps}</span>
          </a>
        {:else}
          <p class="muted small">Сценариев нет: на письма игрока персонаж не отвечает.</p>
        {/each}
      </div>
    </section>
  {/if}
</ListDetail>

{#if dialog === "persona"}
  <Dialog title="Новый персонаж" confirm="Создать" onsubmit={createPersona} onclose={() => (dialog = "")}>
    <label><span class="label">Адрес</span><input class="field mono" bind:value={draft.address} placeholder="guard@aether-core" /></label>
    <label><span class="label">Имя (необязательно)</span><input class="field" bind:value={draft.name} /></label>
  </Dialog>
{:else if dialog === "talk"}
  <Dialog title="Новый сценарий" confirm="Создать" onsubmit={createTalk} onclose={() => (dialog = "")}>
    <label><span class="label">Название</span><input class="field" bind:value={draft.title} oninput={() => { if (!slugTouched) draft.slug = slugify(draft.title); }} placeholder="Доступ к докам" /></label>
    <label><span class="label">Идентификатор для хука mail</span><input class="field mono" bind:value={draft.slug} oninput={() => (slugTouched = true)} placeholder="harbor-door" /></label>
  </Dialog>
{/if}

<style>
  .pad { padding: 20px 32px; }
  .pad-s { padding: 4px 10px; }
  .empty { max-width: 560px; }
  .detail { display: flex; flex-direction: column; gap: 18px; padding: 20px 32px 40px; max-width: 860px; }
  .head { display: flex; align-items: center; gap: 10px; }
  h2 { margin: 0; font-size: 20px; }
  h3 { margin: 0; font-size: 14px; }
  .spacer { flex: 1; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .wide { grid-column: 1 / -1; }
  label { display: flex; flex-direction: column; gap: 4px; }
  textarea { resize: vertical; font: inherit; }
  .mono { font-family: var(--mono); }
  .small { font-size: 12px; margin: 0; }
  .talks { display: flex; flex-direction: column; gap: 8px; }
  .talks-head { display: flex; align-items: center; justify-content: space-between; }
  .talk { display: grid; grid-template-columns: 1fr auto auto; gap: 14px; align-items: baseline; padding: 10px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); color: var(--text); }
  .talk:hover { background: var(--panel); text-decoration: none; border-color: var(--line); }
</style>
