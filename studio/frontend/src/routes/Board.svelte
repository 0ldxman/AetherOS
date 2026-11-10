<script lang="ts">
  // Доски команды: холст Excalidraw на общем документе комнаты boards/<id>. Элементы сливаются по одному (у каждого своя
  // версия), курсоры участников видны на холсте. Карточка сущности: прямоугольник со ссылкой на машину, объект, учётку…
  import { onMount } from "svelte";
  import * as Y from "yjs";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { claim, colorOf, presence, roomAwareness, roomDoc } from "../lib/collab.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  let { id }: { id: number | null } = $props();

  type Element = { id: string; version: number; versionNonce: number; index?: string; isDeleted?: boolean; [key: string]: unknown };
  type Api = {
    getSceneElementsIncludingDeleted(): readonly Element[];
    getAppState(): { scrollX: number; scrollY: number; zoom: { value: number }; width: number; height: number };
    getFiles(): Record<string, unknown>;
    updateScene(scene: Record<string, unknown>): void;
    addFiles(files: unknown[]): void;
    scrollToContent(target?: unknown, options?: unknown): void;
  };
  type Lib = typeof import("../lib/board/excalidraw");

  let boards = $state<Schemas["BdRow"][]>([]);
  let host = $state<HTMLDivElement | undefined>();
  let loading = $state(true);
  let failed = $state(false);
  let dialog = $state<null | "new" | "entity" | "rename">(null);
  let title = $state("");
  let query = $state("");
  let found = $state<Schemas["BdEntity"][]>([]);
  let listOpen = $state(true);

  const board = $derived(boards.find((row) => row.id === id) ?? null);
  const room = $derived(id ? `boards/${id}` : "");

  let lib: Lib | null = null;
  let excalidraw: Api | null = null;
  let unmount: (() => void) | null = null;
  let stop: (() => void) | null = null;
  let applying = false;                                 // сцена обновляется из документа: её onChange не пишем обратно

  async function list() {
    boards = (await api.GET("/studio/api/boards")).data ?? [];
    if (id === null && boards.length) go(`/boards/${(boards.find((row) => row.main) ?? boards[0]).id}`);
  }
  onMount(list);
  $effect(() => { if (room) return claim(room); });

  // холст: Excalidraw монтируется, когда документ комнаты готов
  onMount(() => () => { stop?.(); unmount?.(); });
  $effect(() => {
    presence.epoch;
    const ready = presence.synced && presence.room === room && !!host;
    if (!ready) return;
    const doc = roomDoc();
    if (!doc) return;
    start(doc);
  });

  async function start(doc: Y.Doc) {
    stop?.();
    unmount?.();
    excalidraw = null;
    loading = true;
    try {
      (window as unknown as { EXCALIDRAW_ASSET_PATH: string }).EXCALIDRAW_ASSET_PATH = window.STUDIO.assets;
      lib = lib ?? (await import("../lib/board/excalidraw"));
    } catch {
      failed = true;
      return;
    }
    const elements = doc.getMap<Element>("elements");
    const files = doc.getMap<Record<string, unknown>>("files");
    const awareness = roomAwareness();
    const sorted = () => [...elements.values()].sort((a, b) => ((a.index ?? "") < (b.index ?? "") ? -1 : (a.index ?? "") > (b.index ?? "") ? 1 : 0));

    const apply = () => {
      if (!excalidraw || !lib) return;
      const local = excalidraw.getSceneElementsIncludingDeleted();
      const merged = lib.reconcileElements(local as never, sorted() as never, excalidraw.getAppState() as never);
      applying = true;
      excalidraw.updateScene({ elements: merged, captureUpdate: lib.CaptureUpdateAction.NEVER });
      const known = excalidraw.getFiles();
      const fresh = [...files.values()].filter((file) => !known[file.id as string]);
      if (fresh.length) excalidraw.addFiles(fresh);
      applying = false;
    };
    const onElements = (_event: unknown, transaction: Y.Transaction) => { if (!transaction.local) apply(); };
    elements.observe(onElements);
    files.observe(onElements);

    // свои правки в документ: только элементы, у которых версия выросла
    const onChange = (scene: readonly Element[], _state: unknown, sceneFiles: Record<string, Record<string, unknown>>) => {
      if (applying) return;
      doc.transact(() => {
        for (const element of scene) {
          const stored = elements.get(element.id);
          if (!stored || stored.version < element.version || (stored.version === element.version && stored.versionNonce !== element.versionNonce)) {
            elements.set(element.id, JSON.parse(JSON.stringify(element)));
          }
        }
        for (const [key, file] of Object.entries(sceneFiles ?? {})) if (!files.has(key)) files.set(key, file);
      });
    };

    // курсоры: свой отправляется в присутствие, чужие рисуются Excalidraw
    let lastPointer = 0;
    const onPointer = (payload: { pointer: { x: number; y: number; tool: string }; button: string }) => {
      const now = Date.now();
      if (now - lastPointer < 50) return;
      lastPointer = now;
      awareness?.setLocalStateField("pointer", { ...payload.pointer, button: payload.button });
    };
    const drawPeers = () => {
      if (!excalidraw || !awareness) return;
      const collaborators = new Map<string, unknown>();
      awareness.getStates().forEach((state, client) => {
        if (client === doc.clientID || !state.user || !state.pointer) return;
        const color = state.user.color ?? colorOf(state.user.name);
        collaborators.set(String(client), {
          username: state.user.name, color: { background: color, stroke: color },
          pointer: { x: state.pointer.x, y: state.pointer.y, tool: state.pointer.tool ?? "pointer" }, button: state.pointer.button ?? "up",
        });
      });
      excalidraw.updateScene({ collaborators });
    };
    awareness?.on("change", drawPeers);

    const onLink = (element: { link?: string | null }, event: CustomEvent<{ nativeEvent: MouseEvent }>) => {
      const link = element.link ?? "";
      if (link.startsWith("#/")) {
        event.preventDefault();
        go(link.slice(1));
      }
    };

    // начальная сцена передаётся при запуске: Excalidraw после запуска ставит её сам, поздний updateScene она бы затёрла
    unmount = lib.mountBoard(host!, {
      initialData: { elements: sorted().filter((element) => !element.isDeleted), files: Object.fromEntries([...files.entries()]), scrollToContent: true },
      excalidrawAPI: (value: Api) => {
        excalidraw = value;
        loading = false;
        setTimeout(apply, 300);                         // то, что успело прийти, пока холст запускался
      },
      onChange,
      onPointerUpdate: onPointer,
      onLinkOpen: onLink,
    });
    stop = () => {
      elements.unobserve(onElements);
      files.unobserve(onElements);
      awareness?.off("change", drawPeers);
      awareness?.setLocalStateField("pointer", null);
    };
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/boards", { body: { title } });
    if (error || !data) return toast(problem(error, "Доска не создалась."), "error");
    dialog = null;
    title = "";
    await list();
    go(`/boards/${data.id}`);
  }

  async function rename() {
    if (!board) return;
    const { error } = await api.PUT("/studio/api/boards/{board_id}", { params: { path: { board_id: board.id } }, body: { title } });
    if (error) return toast(problem(error), "error");
    dialog = null;
    await list();
  }

  async function remove(row: Schemas["BdRow"]) {
    if (!(await ask(`Удалить доску «${row.title}»?`, "Всё нарисованное на ней пропадёт у всех.", "Удалить доску"))) return;
    const { error } = await api.DELETE("/studio/api/boards/{board_id}", { params: { path: { board_id: row.id } } });
    if (error) return toast(problem(error), "error");
    await list();
    if (row.id === id) go("/boards");
  }

  let timer: ReturnType<typeof setTimeout>;
  function search() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      found = (await api.GET("/studio/api/boards/entities", { params: { query: { q: query.trim() } } })).data ?? [];
    }, 200);
  }

  // карточка сущности посреди видимой части холста: прямоугольник с подписью и ссылкой
  function addCard(entity: Schemas["BdEntity"]) {
    if (!excalidraw || !lib) return;
    const state = excalidraw.getAppState();
    const zoom = state.zoom.value;
    const x = -state.scrollX + state.width / 2 / zoom - 120;
    const y = -state.scrollY + state.height / 2 / zoom - 32;
    const card = lib.convertToExcalidrawElements([{
      // тёмная тема Excalidraw инвертирует цвета: здесь светлая палитра, на холсте она станет тёмной
      type: "rectangle", x, y, width: 240, height: 64, backgroundColor: "#e7edff", strokeColor: "#3b5bdb", fillStyle: "solid",
      roundness: { type: 3 }, link: entity.link, label: { text: `${entity.kind}\n${entity.label}`, fontSize: 16, strokeColor: "#1e1e2e" },
    }] as never);
    excalidraw.updateScene({ elements: [...excalidraw.getSceneElementsIncludingDeleted(), ...card], captureUpdate: lib.CaptureUpdateAction.IMMEDIATELY });
    dialog = null;
    query = "";
    found = [];
  }
</script>

<div class="board" class:closed={!listOpen}>
  <aside class="list" aria-label="Доски">
    <header class="head">
      <b>Доски</b>
      <span class="spacer"></span>
      <button class="btn ghost tiny" onclick={() => (listOpen = !listOpen)} aria-expanded={listOpen} title={listOpen ? "Свернуть список" : "Показать список досок"}>{listOpen ? "‹" : "›"}</button>
    </header>
    {#if listOpen}
      {#each boards as row (row.id)}
        <div class="row" class:on={row.id === id}>
          <a href="#/boards/{row.id}">{row.title}{#if row.main}<span class="tag">основная</span>{/if}</a>
          {#if row.deletable}<button class="x" onclick={() => remove(row)} aria-label="Удалить доску {row.title}" title="Удалить доску">✕</button>{/if}
        </div>
      {/each}
      <button class="btn ghost add" onclick={() => { title = ""; dialog = "new"; }}>+ Доска</button>
    {/if}
  </aside>

  <section class="canvas-wrap">
    <header class="bar">
      <b class="name">{board?.title ?? "Доска"}</b>
      {#if board}<button class="link" onclick={() => { title = board!.title; dialog = "rename"; }}>переименовать</button>{/if}
      <span class="spacer"></span>
      <button class="btn" disabled={loading} onclick={() => { dialog = "entity"; query = ""; found = []; }}>+ Карточка сущности</button>
    </header>
    <div class="canvas" bind:this={host}></div>
    {#if failed}
      <p class="muted over">Холст не загрузился. Обновите страницу.</p>
    {:else if loading}
      <p class="muted over">{presence.synced ? "Загрузка холста…" : "Подключение к доске…"}</p>
    {/if}
  </section>
</div>

{#if dialog === "new" || dialog === "rename"}
  <Dialog title={dialog === "new" ? "Новая доска" : "Переименовать доску"} confirm={dialog === "new" ? "Создать" : "Сохранить"} disabled={!title.trim()}
          onsubmit={dialog === "new" ? create : rename} onclose={() => (dialog = null)}>
    <label><span class="label">Название</span><input class="field" bind:value={title} placeholder="Загадка порта" /></label>
  </Dialog>
{/if}

{#if dialog === "entity"}
  <Dialog title="Карточка сущности" confirm="Готово" onsubmit={() => (dialog = null)} onclose={() => (dialog = null)}>
    <label><span class="label">Что положить на доску</span><input class="field" bind:value={query} oninput={search} placeholder="Машина, объект, учётка, игрок, ОС, сцена, диск" /></label>
    <div class="found">
      {#each found as entity (entity.link)}
        <button type="button" class="pick" onclick={() => addCard(entity)}><span class="muted">{entity.kind}</span> <b>{entity.label}</b></button>
      {:else}
        <p class="muted small">{query.trim() ? "Ничего не нашлось." : "Начните вводить название."}</p>
      {/each}
    </div>
  </Dialog>
{/if}

<style>
  .board { display: grid; grid-template-columns: 220px 1fr; height: 100vh; }
  .board.closed { grid-template-columns: 44px 1fr; }
  .list { display: flex; flex-direction: column; gap: 2px; padding: 12px 8px; border-right: 1px solid var(--line-soft); overflow-y: auto; }
  .head { display: flex; align-items: center; gap: 6px; padding: 0 4px 8px; }
  .closed .head b { display: none; }
  .spacer { flex: 1; }
  .tiny { padding: 2px 8px; }
  .row { display: flex; align-items: center; gap: 4px; border-radius: var(--radius-s); }
  .row a { flex: 1; min-width: 0; padding: 7px 10px; color: var(--text); overflow-wrap: anywhere; }
  .row a:hover { text-decoration: none; }
  .row:hover, .row.on { background: var(--accent-soft); }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 4px 8px; }
  .x:hover { color: var(--danger); }
  .tag { margin-left: 6px; padding: 0 6px; border-radius: 999px; background: var(--panel-2); font-size: 11px; color: var(--muted); }
  .add { margin-top: 6px; }
  .canvas-wrap { position: relative; display: flex; flex-direction: column; min-width: 0; }
  .bar { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--line-soft); }
  .name { font-size: 15px; }
  .link { border: 0; background: none; color: var(--muted); cursor: pointer; font: inherit; font-size: 12px; text-decoration: underline; text-underline-offset: 2px; padding: 0; }
  .canvas { flex: 1; min-height: 0; }
  .over { position: absolute; top: 60px; left: 0; right: 0; text-align: center; pointer-events: none; }
  .found { display: flex; flex-direction: column; gap: 4px; max-height: 300px; overflow-y: auto; }
  .pick { display: flex; gap: 8px; align-items: baseline; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--text); cursor: pointer; text-align: left; font: inherit; }
  .pick:hover { background: var(--panel-2); }
  .small { font-size: 12px; margin: 0; }
</style>
