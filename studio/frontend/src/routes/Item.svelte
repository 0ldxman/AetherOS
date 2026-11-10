<script lang="ts">
  import { guardUnsaved } from "../lib/guard.svelte";
  import { onMount, untrack } from "svelte";
  import { adminUrl, api, problem, type Schemas } from "../lib/api";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import FormatOptions from "../lib/FormatOptions.svelte";
  import DocPreview from "../lib/DocPreview.svelte";
  import Hint from "../lib/Hint.svelte";
  import MarkupHelp from "../lib/MarkupHelp.svelte";
  import { go, takeOrigin } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import ItemWhere from "./item/ItemWhere.svelte";
  import ItemHistory from "./item/ItemHistory.svelte";
  import ItemKeys from "./item/ItemKeys.svelte";
  import ItemProtection from "./item/ItemProtection.svelte";
  import ContentPicker from "./item/ContentPicker.svelte";
  import AppIcon from "./item/AppIcon.svelte";
  import AppVolumes from "./item/AppVolumes.svelte";

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
  let issues = $state<Schemas["Issue"][]>([]);
  let keysMode = $state<"all" | "none">("all");
  const previewTab = $derived<"body" | "infobox">(tab === "meta" ? "infobox" : "body");   // предпросмотр следует за вкладкой редактора
  let fieldErrors = $state<Record<string, string[]>>({});

  const format = $derived(formats.find((found) => found.name === draft.format));
  let source = $state<"text" | "file">("text");                   // у формата «текст или ассет»: что сейчас правится
  const canFile = $derived(format?.content === "text_asset");
  const fileMode = $derived(canFile ? source === "file" : false);
  const textual = $derived(!format || format.content === "text" || format.content === "text_asset");
  const linkable = $derived(format?.content === "link_asset");
  const dirty = $derived(JSON.stringify(draft) !== saved);
  guardUnsaved(() => saved !== "" && dirty, (next) => next.split("?")[0].split("/")[2] === String(id));

  function fill(found: Item) {
    item = found;
    draft = {
      name: found.name, format: found.format, body: found.body, meta: found.meta, url: found.url, world_creator: found.world_creator,
      world_created_at: found.world_created_at ?? null, world_updated_at: found.world_updated_at ?? null,
    };
    saved = JSON.stringify(draft);
    holder = found.holder ?? null;
    source = found.asset ? "file" : "text";
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

  let menu = $state(false);

  // защита и ключи сохраняются своими запросами, но кнопка одна: шапка сохраняет всё несохранённое на странице
  let part = $state<{ isDirty(): boolean; saveNow(): Promise<void> | void } | undefined>();
  const partDirty = $derived((view === "protection" || view === "keys") && !!part?.isDirty());
  const anyDirty = $derived(dirty || partDirty);

  async function saveAll() {
    if (dirty) await save();
    if (dirty) return;                      // не сохранилось (конфликт или ошибка): остальное не трогаем
    if (partDirty) await part?.saveNow();
  }

  onMount(() => {
    api.GET("/studio/api/formats").then(({ data }) => (formats = data ?? []));
    load();
    heartbeat();
    const beat = setInterval(heartbeat, 25_000);
    return () => {
      clearInterval(beat);
      api.DELETE("/studio/api/items/{item_id}/lock", { params: { path: { item_id: id } } });
    };
  });

  const origin = takeOrigin();
  const backLabel = origin.label || "К списку объектов";
  function back() {
    go(origin.path || "/items");
  }

  function when(stamp: string) {
    return new Date(stamp).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
</script>

<svelte:window onclick={() => (menu = false)} onkeydown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "s") { event.preventDefault(); saveAll(); } }} />

{#if !item}
  <p class="muted loading">Загрузка…</p>
{:else}
  <div class="item">
    <header class="head">
      <button class="btn ghost" onclick={back} aria-label={backLabel} title={backLabel}>←</button>
      <input class="title" bind:value={draft.name} aria-label="Название" class:bad={fieldErrors.name} />
      <span class="chip" title={draft.format ? "Формат объекта" : "Формат не выбран: объект показывается как обычный текст. Выбрать можно на вкладке «Содержимое», «Свойства»."}>{draft.format || "без формата"}</span>
      <span class="status muted">
        {#if anyDirty}<span class="dot"></span>Не сохранено{:else}Сохранено {when(item.updated_at)}{item.updated_by ? ` · ${item.updated_by}` : ""}{/if}
      </span>
      {#if item.view_url}
        <div class="openbtn">
          <a class="open" href="{item.view_url}&as=all" target="_blank" rel="noopener" title="Как увидит игрок (сохранённая версия)">Открыть в новой вкладке</a>
          <button class="caret" aria-label="Выбрать ключи" onclick={(event) => { event.stopPropagation(); menu = !menu; }}>▾</button>
          {#if menu}
            <div class="menu">
              <a href="{item.view_url}&as=all" target="_blank" rel="noopener">С ключами</a>
              <a href="{item.view_url}&as=none" target="_blank" rel="noopener">Без ключей</a>
            </div>
          {/if}
        </div>
      {/if}
      <a class="legacy" href={adminUrl(`filesystem/item/${item.id}/change/`)} title="Старая админка: на время переезда">старая админка</a>
      <button class="btn primary" disabled={!anyDirty || saving} onclick={saveAll}>{saving ? "Сохраняю…" : "Сохранить"}</button>
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
      <a class:on={view === "content"} href="#/items/{id}">Содержимое{#if dirty && view !== "content"}<span class="unsaved" title="В тексте есть несохранённые правки"></span>{/if}</a>
      <a class:on={view === "where"} href="#/items/{id}/where" title="Диски и папки, где этот объект лежит. Один объект может лежать в нескольких местах: правка видна во всех. В счёт входят и архивы, в которые объект включён.">Где лежит <span class="count">{item.placements.length + item.in_archives}</span></a>
      <a class:on={view === "protection"} href="#/items/{id}/protection" title="Как игрок получает содержимое: условие по ключам и слои защиты (пароль, маскировка). Для обычной открытой статьи не нужно.">Защита
        {#if item.protected}<span class="count lock" title="Есть условие или слои">●</span>{/if}{#if partDirty && view === "protection"}<span class="unsaved" title="Есть несохранённые правки"></span>{/if}</a>
      <a class:on={view === "keys"} href="#/items/{id}/keys" title="Игровая механика: ключи, спрятанные в файле, и подписи для проверки подлинности. Для обычной статьи не нужно.">Ключи и подписи{#if partDirty && view === "keys"}<span class="unsaved" title="Есть несохранённые правки"></span>{/if}</a>
      <a class:on={view === "history"} href="#/items/{id}/history" title="Прежние версии текста: можно сравнить и восстановить.">История</a>
    </nav>

    {#if view === "where"}
      <ItemWhere {item} />
    {:else if view === "protection"}
      <ItemProtection bind:this={part} {item} onsaved={load} />
    {:else if view === "keys"}
      <ItemKeys bind:this={part} {item} />
    {:else if view === "history"}
      <ItemHistory {item} {dirty} onrestore={load} />
    {:else}
    <div class="split">
      <section class="pane">
        <nav class="tabs">
          <button class:on={tab === "body"} onclick={() => (tab = "body")}>Текст</button>
          <button class:on={tab === "meta"} title="Врезка: карточка с краткими данными рядом со статьёй" onclick={() => (tab = "meta")}>Врезка</button>
          <button class:on={tab === "props"} onclick={() => (tab = "props")}>Свойства</button>
        </nav>
        <div class="pane-body">
          {#if tab === "body"}
            {#if canFile}
              <div class="srcswitch" role="tablist" aria-label="Откуда содержимое">
                <button role="tab" aria-selected={source === "text"} class:on={source === "text"} onclick={() => (source = "text")}>Текст</button>
                <button role="tab" aria-selected={source === "file"} class:on={source === "file"} onclick={() => (source = "file")}>Файл из хранилища</button>
              </div>
            {/if}
            {#if textual && !fileMode}
              {#if draft.format === "app"}
                <div class="stack">
                  <AppIcon bind:body={draft.body} />
                  <AppVolumes bind:body={draft.body} />
                  <div class="grow"><CodeEditor bind:value={draft.body} markup={false} onsave={() => save()} /></div>
                </div>
              {:else}
                <CodeEditor bind:value={draft.body} markup={format?.markup ?? false} onsave={() => save()} />
              {/if}
            {:else}
              {#if format && format.content !== "none"}
                <ContentPicker {item} {format} onchange={load} />
              {:else}
                <div class="note muted">У формата нет содержимого.</div>
              {/if}
            {/if}
          {:else if tab === "meta"}
            <CodeEditor bind:value={draft.meta} markup onsave={() => save()} />
          {:else}
            <div class="props">
              <label><span class="label">Формат</span>
                <select class="field" bind:value={draft.format}>
                  <option value="">без формата</option>
                  <FormatOptions {formats} />
                </select>
              </label>
              <p class="muted small hint">Расширение берётся из формата. Места, где файл называется по-старому, переименуются сами; свои имена остаются.</p>
              {#if linkable}
                <label><span class="label">Ссылка</span><input class="field" bind:value={draft.url} placeholder="https://…" /></label>
              {/if}
              <label><span class="label">Автор (в мире)<Hint text="Автор внутри вымышленного мира, не пользователь студии. Игрок увидит его в свойствах файла." /></span><input class="field" bind:value={draft.world_creator} /></label>
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
        {#if textual && format?.markup && tab !== "props"}<MarkupHelp />{/if}
      </section>

      <section class="pane preview">
        <nav class="tabs">
          <span class="ptitle">Предпросмотр: {fileMode && item.file_url ? "файл" : previewTab === "infobox" ? "врезка" : "документ"}</span>
          <select class="keys" bind:value={keysMode} title="С какими ключами смотреть">
            <option value="all">со всеми ключами</option>
            <option value="none">без ключей</option>
          </select>
          <Hint text="Часть текста может быть скрыта от игрока, пока у него нет нужного ключа. «Со всеми ключами» показывает всё, «без ключей» то, что увидит игрок, у которого ключей ещё нет." />
        </nav>
        {#if previewTab === "infobox" && !draft.meta.trim()}<p class="muted emptynote">Врезка пуста. Это карточка с краткими данными рядом со статьёй: заполните её в редакторе слева.</p>{/if}
        {#if (fileMode || !textual) && item.file_url}
          {#key item.version}<iframe class="fileview" src="{item.file_url}?v={encodeURIComponent(item.version)}" title="Просмотр файла"></iframe>{/key}
        {:else}
          <DocPreview format={draft.format} title={draft.name} body={draft.body} meta={draft.meta} only={previewTab} {keysMode} bind:issues />
        {/if}
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
  .openbtn { position: relative; display: flex; align-items: stretch; height: 30px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); }
  .openbtn:hover { border-color: #343947; }
  .openbtn .open, .openbtn .caret { display: flex; align-items: center; border: 0; background: none; color: var(--muted); cursor: pointer; text-decoration: none; white-space: nowrap; }
  .openbtn .open { padding: 0 10px 0 12px; border-radius: var(--radius-s) 0 0 var(--radius-s); }
  .openbtn .caret { padding: 0 8px; font-size: 11px; border-left: 1px solid var(--line-soft); border-radius: 0 var(--radius-s) var(--radius-s) 0; }
  .openbtn .open:hover, .openbtn .caret:hover { background: var(--raise); color: var(--text); }
  .menu { position: absolute; top: 100%; right: -1px; z-index: 10; margin-top: 4px; min-width: 150px; padding: 4px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
  .menu a { display: block; padding: 6px 10px; border-radius: var(--radius-s); color: var(--text); text-decoration: none; }
  .menu a:hover { background: var(--panel); }
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
  .unsaved { display: inline-block; width: 7px; height: 7px; margin-left: 6px; border-radius: 50%; background: var(--warn); vertical-align: middle; }
  .legacy { color: var(--faint); font-size: 12px; }
  .legacy:hover { color: var(--muted); }
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
  .count.lock { background: rgba(242, 198, 109, 0.18); color: var(--warn); font-size: 9px; }
  .count { padding: 0 6px; border-radius: 999px; background: var(--raise); font-size: 11px; color: var(--muted); }
  .split { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px 16px 16px; }
  .pane { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; background: var(--panel); }
  .tabs { display: flex; align-items: center; gap: 2px; padding: 6px; border-bottom: 1px solid var(--line-soft); }
  .tabs button { border: 0; background: none; padding: 5px 10px; border-radius: var(--radius-s); color: var(--muted); cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { background: var(--panel-2); color: var(--text); }
  .emptynote { margin: 0; padding: 12px 14px; }
  .ptitle { padding: 5px 10px; color: var(--muted); }
  .keys { margin-left: auto; height: 26px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); padding: 0 6px; }
  .pane-body { flex: 1; min-height: 0; }
  .srcswitch { display: flex; gap: 4px; padding: 8px 14px 0; }
  .srcswitch button { padding: 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--muted); cursor: pointer; }
  .srcswitch button.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .fileview { flex: 1; min-height: 0; width: 100%; border: 0; background: #fff; }
  .stack { display: flex; flex-direction: column; height: 100%; }
  .grow { flex: 1; min-height: 0; }
  .note { padding: 16px; }
  .props { display: flex; flex-direction: column; gap: 14px; padding: 16px; overflow: auto; height: 100%; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .where { display: block; padding: 2px 0; }
  .small { font-size: 12px; }
  .hint { margin: -6px 0 0; }
  .issues { margin: 0; padding: 8px 12px; list-style: none; max-height: 140px; overflow: auto; border-top: 1px solid var(--line-soft); font-size: 12.5px; }
  .issues li { padding: 2px 0; }
  .issues li.error { color: var(--danger); }
  .issues li.warning { color: var(--warn); }
</style>
