<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  type Scene = Schemas["SceneOut"];

  let { slug }: { slug: string | null } = $props();

  let rows = $state<Schemas["SceneRow"][]>([]);
  let scene = $state<Scene | null>(null);
  let form = $state({ slug: "", title: "", body: "", note: "" });
  let saved = $state("");
  let errors = $state<Record<string, string[]>>({});
  let preview = $state<Schemas["ScenePreview"] | null>(null);
  let slot = $state("");
  let creating = $state(false);
  let draft = $state({ slug: "", title: "" });
  let screen: HTMLElement | undefined = $state();
  let term: { play: (steps: unknown[], opts?: unknown) => Promise<unknown> } | null = null;
  let timer: ReturnType<typeof setTimeout>;

  const current = $derived(slug ?? rows[0]?.slug ?? null);
  const dirty = $derived(JSON.stringify(form) !== saved);

  async function list() {
    rows = (await api.GET("/studio/api/scenes")).data ?? [];
  }

  function fill(data: Scene) {
    scene = data;
    form = { slug: data.slug, title: data.title, body: data.body, note: data.note };
    saved = JSON.stringify(form);
    errors = {};
  }

  async function load(target: string | null) {
    scene = null;
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
    const { error } = await api.DELETE("/studio/api/scenes/{slug}", { params: { path: { slug: scene.slug } } });
    if (error) return toast(problem(error, "Не удалилась."), "error");
    toast("Сцена удалена.");
    await list();
    go("/scenes");
  }

  async function play() {
    if (!screen || !preview) return;
    const aether = (window as unknown as { Aether?: { console: { create: (el: HTMLElement) => typeof term } } }).Aether;
    if (!aether) return toast("Проигрыватель не загружен.", "error");
    term ??= aether.console.create(screen);
    await term!.play([{ op: "clear" }, ...preview.steps]);
  }

  function insert(name: string) {
    form.body += `{${name}}`;
  }

  const slotParams = $derived(scene?.slots.find((item) => item.slot === slot)?.params ?? []);
</script>

<div class="split">
  <aside class="list">
    <h1>Сцены</h1>
    {#each rows as row (row.slug)}
      <a class="item" class:on={row.slug === current} href="#/scenes/{row.slug}">
        <b class="mono">{row.slug}</b>
        <span class="muted small">{row.title || "без названия"}{row.bindings ? ` · событий ${row.bindings}` : ""}</span>
      </a>
    {/each}
    <button class="btn add" onclick={() => (creating = true)}>+ Сцена</button>
  </aside>

  {#if scene}
    <section class="editor">
      <header class="top">
        <input class="field title" placeholder="название" bind:value={form.title} />
        <input class="field mono slug" bind:value={form.slug} class:bad={errors.slug} />
        <span class="spacer"></span>
        <button class="btn" onclick={play} disabled={!preview?.steps.length}>▶ Играть</button>
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
        <button class="btn ghost danger" onclick={drop}>Удалить</button>
      </header>
      {#if errors.slug}<p class="warn small">{errors.slug.join(" ")}</p>{/if}

      <div class="slotbar">
        <span class="muted small">Подстановки события:</span>
        <select class="field" bind:value={slot}>
          <option value="">все</option>
          {#each scene.slots as item}<option value={item.slot}>{item.label}</option>{/each}
        </select>
        {#each slotParams as name}<button class="chip mono" onclick={() => insert(name)}>{"{"}{name}{"}"}</button>{/each}
      </div>

      <textarea class="field mono body" rows="22" wrap="off" spellcheck="false" bind:value={form.body} class:bad={errors.body}></textarea>
      {#each preview?.errors ?? [] as error}<p class="warn small">Строка {error.line}: {error.text}</p>{/each}
      {#if errors.body && !(preview?.errors.length)}<p class="warn small">{errors.body.join(" ")}</p>{/if}

      <div class="screen" bind:this={screen}></div>

      <details class="help">
        <summary>Шпаргалка по языку сцен</summary>
        <pre class="mono small"># текст                комментарий (\# в начале: сама строка)
строка текста         вывод: цвета &lt;success&gt;…&lt;/success&gt;, {"{host}"}, &lt;rand&gt;1-9&lt;/rand&gt;, &lt;since&gt;2027-10-29&lt;/since&gt;, &lt;table&gt;
~ текст               тусклая строка         \@ или \~ в начале: сама строка
&lt;count to=64000 unit=K ms=600-1100/&gt;   число растёт в строке
&lt;cursor/&gt;                      курсор после приглашения (&amp;gt; &lt;cursor/&gt;&lt;type&gt;…&lt;/type&gt;)
&lt;type human typo&gt;текст&lt;/type&gt;      печатается побуквенно
&lt;mark имя&gt;текст&lt;/mark&gt;            пометка для @glitch
@task метка | OK | 200-450        look=unit|kernel note= done= style= at= width=20
@unit имя | описание | OK | мс     служба aeinit
@bar метка | мс                    width=24
@count метка | до | единица | мс   result=OK note=
@log сек | тег | сообщение
@glitch имя | новый текст          frames=14
@countdown Старт через {"{n}"}с | секунд
@wait 450   @read   @clear   @cut   @flash   @blank 2
@include слаг                      вставить другую сцену
@rows width=12   (строки с отступом: подпись | значение | стиль | пояснение)
@bars width=14   (строки с отступом: подпись | мс | результат | стоп%)
@burst gap=8-45  (строки с отступом: обычные строки вывода)</pre>
      </details>

      <div class="used">
        <h3>Где играет</h3>
        {#each scene.bindings as item}
          <span class="chip"><a href="#/systems/{item.system}/overview">{item.system}</a> · {item.label}</span>
        {:else}
          <span class="muted small">Ни к какому событию не привязана: назначьте её в «Операционные системы → Обзор → Сцены».</span>
        {/each}
      </div>
    </section>
  {:else}
    <p class="muted empty">{rows.length ? "Загрузка…" : "Сцен пока нет."}</p>
  {/if}
</div>

{#if creating}
  <Dialog title="Новая сцена" confirm="Создать" onsubmit={create} onclose={() => (creating = false)}>
    <input class="field mono" placeholder="слаг (латиницей)" bind:value={draft.slug} />
    <input class="field" placeholder="название" bind:value={draft.title} />
  </Dialog>
{/if}

<style>
  .split { display: grid; grid-template-columns: 260px 1fr; min-height: 100%; }
  .list { display: flex; flex-direction: column; gap: 2px; padding: 20px 8px; border-right: 1px solid var(--line-soft); }
  h1 { margin: 0 10px 12px; font-size: 18px; }
  .item { display: flex; flex-direction: column; padding: 8px 10px; border-radius: var(--radius-s); color: var(--text); }
  .item:hover { background: var(--panel); text-decoration: none; }
  .item.on { background: var(--accent-soft); }
  .small { font-size: 12px; margin: 0; }
  .add { margin: 8px 4px 0; justify-content: center; }
  .editor { display: flex; flex-direction: column; gap: 10px; padding: 16px 20px 32px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 8px; }
  .title { max-width: 320px; }
  .slug { max-width: 200px; }
  .spacer { flex: 1; }
  .slotbar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .slotbar select { width: auto; }
  .chip { cursor: pointer; }
  .body { white-space: pre; overflow: auto; min-height: 30em; }
  .bad { border-color: var(--danger); }
  .warn { color: var(--warn); margin: 0; }
  .screen {
    --term-fg: #cccccc; --term-dim: #767676; --term-ok: #16c60c; --term-warn: #f9f1a5; --term-error: #e74856; --term-info: #61d6d6; --bg: #0b0d10;
    min-height: 220px; max-height: 420px; overflow: auto; padding: 10px 12px; background: #0b0d10; color: #cccccc; border-radius: var(--radius-s);
    font: 14px/1.25 ui-monospace, "DejaVu Sans Mono", monospace; white-space: pre-wrap;
  }
  .help pre { margin: 8px 0 0; padding: 10px 12px; background: var(--panel); border-radius: var(--radius-s); overflow: auto; }
  .used { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .used h3 { margin: 0 8px 0 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .empty { padding: 24px; }
</style>
