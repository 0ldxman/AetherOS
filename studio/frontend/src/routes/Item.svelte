<script lang="ts">
  import { onMount } from "svelte";
  import { adminUrl, api, problem, type Schemas } from "../lib/api";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import ItemWhere from "./item/ItemWhere.svelte";
  import ItemHistory from "./item/ItemHistory.svelte";

  type Item = Schemas["ItemOut"];

  let { id, view = "content" }: { id: number; view?: string } = $props();


  let item = $state<Item | null>(null);
  let draft = $state({ name: "", format: "", body: "", meta: "", url: "", world_creator: "",
    world_created_at: null as string | null, world_updated_at: null as string | null });
  let saved = $state("");
  let formats = $state<Schemas["Format"][]>([]);
  let tab = $state<"body" | "meta" | "props">("body");
  let saving = $state(false);
  let conflict = $state<Schemas["Conflict"] | null>(null);
  let holder = $state<Schemas["Holder"] | null>(null);
  let preview = $state<Schemas["PreviewOut"] | null>(null);
  let keysMode = $state<"all" | "none">("all");
  let previewTab = $state<"body" | "infobox">("body");
  let fieldErrors = $state<Record<string, string[]>>({});

  const format = $derived(formats.find((found) => found.name === draft.format));
  const textual = $derived(!format || format.content === "text" || format.content === "text_asset");
  const linkable = $derived(format?.content === "link_asset");
  const dirty = $derived(JSON.stringify(draft) !== saved);
  const issues = $derived(preview ? [...(preview.issues.body ?? []), ...(preview.issues.infobox ?? [])] : []);

  function fill(found: Item) {
    item = found;
    draft = {
      name: found.name, format: found.format, body: found.body, meta: found.meta, url: found.url, world_creator: found.world_creator,
      world_created_at: found.world_created_at ?? null, world_updated_at: found.world_updated_at ?? null,
    };
    saved = JSON.stringify(draft);
    holder = found.holder ?? null;
  }

  async function load() {
    const { data, error } = await api.GET("/studio/api/items/{item_id}", { params: { path: { item_id: id } } });
    if (error || !data) return toast("Объект не найден.", "error");
    fill(data);
  }

  async function save(force = false) {
    if (!item || saving) return;
    saving = true;
    fieldErrors = {};
    const { data, error, response } = await api.PUT("/studio/api/items/{item_id}", {
      params: { path: { item_id: id } }, body: { ...draft, version: item.version, force },
    });
    saving = false;
    if (response.status === 409) {
      conflict = error as Schemas["Conflict"];
      return;
    }
    if (error || !data) {
      fieldErrors = ((error as { fields?: Record<string, string[]> })?.fields) ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    conflict = null;
    fill(data);
    toast("Сохранено.");
  }

  async function reload() {
    conflict = null;
    await load();
  }

  // занятие: пока страница открыта, объект помечен как «правит такой-то»; другой автор видит это сразу
  async function heartbeat() {
    const { data, response } = await api.POST("/studio/api/items/{item_id}/lock", { params: { path: { item_id: id } } });
    holder = response.status === 423 ? (data as unknown as Schemas["Holder"]) : null;
  }

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const snapshot = { format: draft.format, title: draft.name, body: draft.body, meta: draft.meta, mode: keysMode };
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const { data } = await api.POST("/studio/api/items/preview", {
        body: { format: snapshot.format, title: snapshot.title, body: snapshot.body, meta: snapshot.meta, keys: { mode: snapshot.mode, slugs: [] } },
      });
      if (data) preview = data;
    }, 350);
  });

  onMount(() => {
    api.GET("/studio/api/formats").then(({ data }) => (formats = data ?? []));
    load();
    heartbeat();
    const beat = setInterval(heartbeat, 25_000);
    const leave = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", leave);
    return () => {
      clearInterval(beat);
      window.removeEventListener("beforeunload", leave);
      api.DELETE("/studio/api/items/{item_id}/lock", { params: { path: { item_id: id } } });
    };
  });

  function back() {
    go("/items");
  }

  function when(stamp: string) {
    return new Date(stamp).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
</script>

<svelte:window onkeydown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "s") { event.preventDefault(); save(); } }} />

{#if !item}
  <p class="muted loading">Загрузка…</p>
{:else}
  <div class="item">
    <header class="head">
      <button class="btn ghost" onclick={back}>←</button>
      <input class="title" bind:value={draft.name} aria-label="Название" class:bad={fieldErrors.name} />
      <span class="chip">{draft.format || "без формата"}</span>
      <span class="status muted">
        {#if dirty}<span class="dot"></span>Не сохранено{:else}Сохранено {when(item.updated_at)}{item.updated_by ? ` · ${item.updated_by}` : ""}{/if}
      </span>
      <a class="btn ghost" href={adminUrl(`filesystem/item/${item.id}/change/`)}>В старой админке</a>
      <button class="btn primary" disabled={!dirty || saving} onclick={() => save()}>{saving ? "Сохраняю…" : "Сохранить"}</button>
    </header>

    {#if fieldErrors.name}<p class="error-line">{fieldErrors.name.join(" ")}</p>{/if}

    {#if conflict}
      <div class="banner danger">
        <span>{conflict.detail} {conflict.by ? `Сохранил ${conflict.by}` : ""} в {when(conflict.at)}.</span>
        <button class="btn" onclick={reload}>Открыть их версию</button>
        <button class="btn danger" onclick={() => save(true)}>Сохранить моё поверх</button>
      </div>
    {:else if holder}
      <div class="banner warn">Сейчас этот объект правит <b>{holder.user}</b> (с {when(holder.since)}). Сохранить можно, но правки могут разойтись.</div>
    {/if}

    <nav class="pagetabs">
      <a class:on={view === "content"} href="#/items/{id}">Содержимое</a>
      <a class:on={view === "where"} href="#/items/{id}/where">Где лежит <span class="count">{item.placements.length}</span></a>
      <a class:on={view === "history"} href="#/items/{id}/history">История</a>
    </nav>

    {#if view === "where"}
      <ItemWhere {item} />
    {:else if view === "history"}
      <ItemHistory {item} {dirty} onrestore={load} />
    {:else}
    <div class="split">
      <section class="pane">
        <nav class="tabs">
          <button class:on={tab === "body"} onclick={() => (tab = "body")}>Текст</button>
          <button class:on={tab === "meta"} onclick={() => (tab = "meta")}>Врезка</button>
          <button class:on={tab === "props"} onclick={() => (tab = "props")}>Свойства</button>
        </nav>
        <div class="pane-body">
          {#if tab === "body"}
            {#if textual}
              <CodeEditor bind:value={draft.body} markup={format?.markup ?? false} onsave={() => save()} />
            {:else}
              <div class="note muted">
                {#if item.asset}Содержимое: ассет «{item.asset}».{:else if item.scene}Содержимое: сцена карты «{item.scene}».{:else if item.message}Содержимое: письмо «{item.message}».{:else}У формата нет текста.{/if}
                Выбор ассета, сцены и письма пока в старой админке.
              </div>
            {/if}
          {:else if tab === "meta"}
            <CodeEditor bind:value={draft.meta} markup onsave={() => save()} />
          {:else}
            <div class="props">
              <label><span class="label">Формат</span>
                <select class="field" bind:value={draft.format}>
                  <option value="">без формата</option>
                  {#each formats as found}<option value={found.name}>{found.name} — {found.title}</option>{/each}
                </select>
              </label>
              {#if linkable}
                <label><span class="label">Ссылка</span><input class="field" bind:value={draft.url} placeholder="https://…" /></label>
              {/if}
              <label><span class="label">Автор (в мире)</span><input class="field" bind:value={draft.world_creator} /></label>
              <div class="pair">
                <label><span class="label">Создан (в мире)</span><input class="field" type="date" bind:value={draft.world_created_at} /></label>
                <label><span class="label">Изменён (в мире)</span><input class="field" type="date" bind:value={draft.world_updated_at} /></label>
              </div>
              <div>
                <span class="label">Где лежит</span>
                {#each item.placements as where}
                  <a class="where mono" href="#/volumes/{where.volume}">{where.volume_name}:/{where.path}</a>
                {:else}
                  <span class="muted">нигде (объект без размещений)</span>
                {/each}
              </div>
              <div class="muted small">Слаг <span class="mono">{item.slug}</span> · создан {when(item.created_at)}</div>
            </div>
          {/if}
        </div>
      </section>

      <section class="pane preview">
        <nav class="tabs">
          <button class:on={previewTab === "body"} onclick={() => (previewTab = "body")}>Документ</button>
          <button class:on={previewTab === "infobox"} onclick={() => (previewTab = "infobox")}>Врезка</button>
          <select class="keys" bind:value={keysMode} title="С какими ключами смотреть">
            <option value="all">со всеми ключами</option>
            <option value="none">без ключей</option>
          </select>
        </nav>
        <iframe title="Предпросмотр" srcdoc={preview ? (previewTab === "body" ? preview.body : preview.infobox) : ""}></iframe>
        {#if issues.length}
          <ul class="issues">
            {#each issues as issue}
              <li class={issue.level}><span class="mono">стр. {issue.line}</span> {issue.message}</li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
    {/if}
  </div>
{/if}

<style>
  .loading { padding: 32px; }
  .item { display: flex; flex-direction: column; height: 100%; }
  .head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--line-soft); }
  .title {
    field-sizing: content; min-width: 120px; max-width: 520px; height: 34px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--radius-s);
    background: transparent; font-size: 17px; font-weight: 600; outline: none;
  }
  .title:hover { border-color: var(--line); }
  .title:focus { border-color: var(--accent); background: var(--bg); }
  .title.bad { border-color: var(--danger); }
  .status { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 12.5px; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  .error-line { margin: 6px 16px 0; color: var(--danger); }
  .banner { display: flex; align-items: center; gap: 10px; margin: 10px 16px 0; padding: 9px 12px; border-radius: var(--radius); }
  .banner.danger { background: var(--danger-soft); border: 1px solid rgba(255, 122, 122, 0.3); }
  .banner.danger span { flex: 1; }
  .banner.warn { background: rgba(242, 198, 109, 0.1); border: 1px solid rgba(242, 198, 109, 0.3); }
  .pagetabs { display: flex; gap: 2px; padding: 0 16px; border-bottom: 1px solid var(--line-soft); }
  .pagetabs a { display: flex; gap: 6px; align-items: center; padding: 8px 12px; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .pagetabs a:hover { color: var(--text); text-decoration: none; }
  .pagetabs a.on { color: var(--text); border-bottom-color: var(--accent); }
  .count { padding: 0 6px; border-radius: 999px; background: var(--raise); font-size: 11px; color: var(--muted); }
  .split { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px 16px 16px; }
  .pane { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; background: var(--panel); }
  .tabs { display: flex; align-items: center; gap: 2px; padding: 6px; border-bottom: 1px solid var(--line-soft); }
  .tabs button { border: 0; background: none; padding: 5px 10px; border-radius: var(--radius-s); color: var(--muted); cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { background: var(--panel-2); color: var(--text); }
  .keys { margin-left: auto; height: 26px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); padding: 0 6px; }
  .pane-body { flex: 1; min-height: 0; }
  .note { padding: 16px; }
  .props { display: flex; flex-direction: column; gap: 14px; padding: 16px; overflow: auto; height: 100%; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .where { display: block; padding: 2px 0; }
  .small { font-size: 12px; }
  iframe { flex: 1; width: 100%; border: 0; background: #fff; }
  .issues { margin: 0; padding: 8px 12px; list-style: none; max-height: 140px; overflow: auto; border-top: 1px solid var(--line-soft); font-size: 12.5px; }
  .issues li { padding: 2px 0; }
  .issues li.error { color: var(--danger); }
  .issues li.warning { color: var(--warn); }
</style>
