<script lang="ts">
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { onMount } from "svelte";
  import DraftState from "../lib/DraftState.svelte";
  import { SharedForm } from "../lib/shared.svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import Icon from "../lib/Icon.svelte";
  import Insert from "./scenes/Insert.svelte";
  import Reference from "./scenes/Reference.svelte";
  import Stage from "./scenes/Stage.svelte";

  type Scene = Schemas["SceneOut"];

  let { slug }: { slug: string | null } = $props();

  let rows = $state<Schemas["SceneRow"][]>([]);
  let scene = $state<Scene | null>(null);
  let form = $state({ slug: "", title: "", body: "", note: "" });
  let saved = $state("");
  let base = $state<typeof form | null>(null);              // сохранённое: им наполняется общий черновик
  let errors = $state<Record<string, string[]>>({});
  let preview = $state<Schemas["ScenePreview"] | null>(null);
  let slot = $state("");
  let creating = $state(false);
  let draft = $state({ slug: "", title: "" });
  let editor: { insertSnippet(template: string): void; insertText(text: string): void; goto(line: number): void } | undefined = $state();
  let timer: ReturnType<typeof setTimeout>;

  const current = $derived(slug ?? rows[0]?.slug ?? null);
  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);   // пока ничего не загружено, правок нет; черновик на сервере

  async function list() {
    rows = (await api.GET("/studio/api/scenes")).data ?? [];
  }

  function fill(data: Scene) {
    scene = data;
    form = { slug: data.slug, title: data.title, body: data.body, note: data.note };
    saved = JSON.stringify(form);
    base = JSON.parse(saved);
    errors = {};
  }

  // общий черновик сцены; кто-то сохранил: перечитать сохранённое, черновик не трогается
  const share = new SharedForm({
    room: () => `scenes/${current}`,
    texts: ["title", "body", "note"],
    draft: () => form,
    base: () => base,
    onRemoteSave: async () => {
      if (!current) return;
      const { data } = await api.GET("/studio/api/scenes/{slug}", { params: { path: { slug: current } } });
      if (!data) return;
      scene = data;
      saved = JSON.stringify({ slug: data.slug, title: data.title, body: data.body, note: data.note });
      base = JSON.parse(saved);
      list();
    },
  });

  async function load(target: string | null) {
    scene = null;
    base = null;
    if (target === null) return;
    const { data } = await api.GET("/studio/api/scenes/{slug}", { params: { path: { slug: target } } });
    if (data) fill(data);
  }

  onMount(list);
  $effect(() => { load(current); });

  // ошибки и шаги пересчитываются, пока пишешь
  $effect(() => {
    form.body;
    slot;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!scene) return;
      preview = (await api.POST("/studio/api/scenes/preview", { body: { body: form.body, slot } })).data ?? null;
    }, 300);
    return () => clearTimeout(timer);
  });

  async function save() {
    if (!scene) return;
    const { data, error } = await api.PUT("/studio/api/scenes/{slug}", { params: { path: { slug: scene.slug } }, body: form });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    const renamed = data.slug !== scene.slug;
    fill(data);
    share.markSaved();
    toast("Сцена сохранена.");
    await list();
    if (renamed) go(`/scenes/${data.slug}`);
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/scenes", { body: { slug: draft.slug, title: draft.title, body: "", note: "" } });
    if (error || !data) return toast(problem(error, "Сцена не создалась."), "error");
    creating = false;
    draft = { slug: "", title: "" };
    await list();
    go(`/scenes/${data.slug}`);
  }

  async function drop() {
    if (!scene) return;
    const used = scene.bindings.map((item) => `${item.system} · ${item.label}`);
    if (!(await ask(`Удалить сцену «${scene.title || scene.slug}»?`, used.length ? `Она назначена на события: ${used.join(", ")}. Привязки пропадут.` : "Она ни к какому событию не привязана."))) return;
    const { error } = await api.DELETE("/studio/api/scenes/{slug}", { params: { path: { slug: scene.slug } } });
    if (error) return toast(problem(error, "Не удалилась."), "error");
    toast("Сцена удалена.");
    await list();
    go("/scenes");
  }

  // подстановки выбранного события; «все»: любые, что есть хотя бы у одного
  const params = $derived(slot ? (scene?.slots.find((item) => item.slot === slot)?.params ?? []) : [...new Set(scene?.slots.flatMap((item) => item.params) ?? [])]);
  const problems = $derived(preview?.errors ?? []);
  const firstProblem = $derived(problems.length ? Math.min(...problems.map((item) => item.line)) : 0);
</script>

<ListDetail title="Сцены">
  {#snippet list()}
    {#each rows as row (row.slug)}
      <a class="item" class:on={row.slug === current} href="#/scenes/{row.slug}">
        <b class="mono">{row.slug}</b>
        <span class="muted small">{row.title || "без названия"}{row.bindings ? ` · событий ${row.bindings}` : ""}</span>
      </a>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn add" onclick={() => (creating = true)}>+ Сцена</button>
  {/snippet}

  {#if scene}
    <section class="editor">
      <header class="top">
        <input class="field title" placeholder="название" bind:value={form.title} aria-label="Название сцены" />
        <input class="field mono slug" bind:value={form.slug} class:bad={errors.slug} aria-label="Идентификатор сцены" />
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={drop}>Удалить</button>
        <DraftState {share} {dirty} saved="" />
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
      </header>
      {#if errors.slug}<p class="warn small">{errors.slug.join(" ")}</p>{/if}

      <div class="work">
        <div class="left">
          <div class="toolbar">
            <Insert {params} samples={scene.samples} onsnippet={(template) => editor?.insertSnippet(template)} ontext={(text) => editor?.insertText(text)} />
            <span class="spacer"></span>
            {#if problems.length}
              <button class="problems bad" onclick={() => editor?.goto(firstProblem)} title="Ошибок: {problems.length}. Перейти к первой"><Icon name="alert" size={14} />{problems.length}</button>
            {:else if preview}
              <span class="problems ok" title="Ошибок нет"><Icon name="check" size={16} /></span>
            {/if}
          </div>
          <div class="code" class:bad={problems.length || errors.body}>
            {#key share.texts.body}<CodeEditor bind:this={editor} bind:value={form.body} shared={share.texts.body ?? null} field="Текст сцены" scene={{ problems, params }} onsave={save} />{/key}
          </div>
          {#each problems.slice(0, 4) as error}<p class="warn small"><button class="line" onclick={() => editor?.goto(error.line)}>Строка {error.line}</button>{error.text}</p>{/each}
          {#if problems.length > 4}<p class="muted small">…и ещё {problems.length - 4}: они подчёркнуты в тексте.</p>{/if}
          {#if errors.body && !problems.length}<p class="warn small">{errors.body.join(" ")}</p>{/if}
        </div>

        <aside class="right">
          {#key scene.slug}<Stage steps={preview?.steps ?? null} slots={scene.slots} bind:slot failed={problems.length > 0} />{/key}
          <Reference {params} samples={scene.samples} bindings={scene.bindings} onsnippet={(template) => editor?.insertSnippet(template)} ontext={(text) => editor?.insertText(text)} />
        </aside>
      </div>
    </section>
  {:else}
    {#if rows.length}
      <p class="muted empty">Загрузка…</p>
    {:else}
      <div class="empty">
        <p class="muted">Сцен пока нет. Сцена — короткий сценарий, который проигрывается на экране игрока.</p>
        <button class="btn primary" onclick={() => (creating = true)}>+ Сцена</button>
      </div>
    {/if}
  {/if}
</ListDetail>

{#if creating}
  <Dialog title="Новая сцена" confirm="Создать" onsubmit={create} onclose={() => (creating = false)}>
    <input class="field mono" placeholder="идентификатор сцены (латиницей)" bind:value={draft.slug} />
    <input class="field" placeholder="название" bind:value={draft.title} />
  </Dialog>
{/if}

<style>
  .small { font-size: 12px; margin: 0; }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 24px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 8px; }
  .top :global(.draft) { flex-wrap: nowrap; white-space: nowrap; }
  .title, .slug { min-width: 0; flex: 1 1 160px; }
  .title { max-width: 320px; }
  .slug { max-width: 200px; }
  .spacer { flex: 1; }
  .work { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 16px; align-items: start; }
  .left { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .toolbar { display: flex; align-items: center; gap: 8px; }
  .problems { white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font: inherit; font-size: 12.5px; border: 0; background: none; }
  .problems.ok { color: var(--ok); }
  .problems.bad { color: var(--warn); background: rgba(242, 198, 109, 0.12); cursor: pointer; }
  .code { height: calc(100vh - 230px); min-height: 420px; border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; background: var(--bg); }
  .code:focus-within { border-color: var(--accent); }
  .code.bad { border-color: color-mix(in srgb, var(--warn) 55%, var(--line-soft)); }
  .right { position: sticky; top: 12px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .warn { margin: 0; color: var(--warn); }
  .line { margin-right: 8px; padding: 0; border: 0; background: none; color: inherit; font: inherit; font-weight: 600; text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
  .bad { border-color: var(--danger); }
  .empty { padding: 24px; }
  @media (max-width: 1100px) { .work { grid-template-columns: 1fr; } .right { position: static; } }
</style>
