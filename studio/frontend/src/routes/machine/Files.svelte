<script lang="ts">
  // Файлы машины: её файловая система целиком (все диски вместе). Любая правка ложится в диск отличий этой машины,
  // общие диски не меняются. Пометки показывают, откуда файл: общий, изменён здесь, добавлен здесь, скрыт.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import FileIcon from "../../lib/FileIcon.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { comeFrom, go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import ContextMenu, { type MenuItem } from "../volume/ContextMenu.svelte";
  import PlacementProtection from "../item/PlacementProtection.svelte";
  import FileDetails from "./FileDetails.svelte";

  type Row = Schemas["MachineFileRow"];
  let { machine }: { machine: Schemas["Overview"] } = $props();

  const key = () => `studio.files.${machine.id}`;
  let rows = $state<Row[]>([]);
  let overlayDisk = $state<number | null>(null);
  let changed = $state(0);
  let loading = $state(true);
  let cwd = $state(read());
  let query = $state("");
  let onlyChanged = $state(false);
  let open_ = $state<Record<string, boolean>>({ "/": true });
  let menu = $state<null | { x: number; y: number; items: MenuItem[] }>(null);
  let creating = $state(false);
  let dialog = $state<null | { kind: "folder" | "file" | "rename" | "move" | "copy" | "rights"; rows: Row[] }>(null);
  let field = $state({ name: "", dest: "/", owner: "", group: "", mode: "" });
  let busy = $state(false);
  let sel = $state<Set<string>>(new Set());
  let anchor = $state<string | null>(null);
  let dragging = $state<string[]>([]);
  let dropTo = $state<string | null>(null);
  let protect = $state<null | { item: number; placed: Schemas["Placed"] }>(null);

  function read(): string {
    try { return sessionStorage.getItem(key()) || "/"; } catch { return "/"; }
  }
  $effect(() => { try { sessionStorage.setItem(key(), cwd); } catch { /* вкладка без хранилища */ } });

  async function load() {
    const { data } = await api.GET("/studio/api/machines/{machine_id}/files", { params: { path: { machine_id: machine.id } } });
    if (data) { rows = data.rows; overlayDisk = data.overlay ?? null; changed = data.changed; }
    loading = false;
    if (cwd !== "/" && !rows.some((r) => r.path === cwd && r.kind === "dir")) cwd = "/";
    sel = new Set([...sel].filter((path) => rows.some((r) => r.path === path)));
  }
  onMount(load);

  const parentOf = (path: string) => path.slice(0, path.lastIndexOf("/")) || "/";
  const dirs = $derived(rows.filter((r) => r.kind === "dir"));
  const listing = $derived.by(() => {
    const q = query.trim().toLowerCase();
    let found: Row[];
    if (q || onlyChanged) {
      found = rows.filter((r) => (!q || r.path.toLowerCase().includes(q)) && (!onlyChanged || ["override", "added", "deleted"].includes(r.mark)));
    } else {
      found = rows.filter((r) => parentOf(r.path) === cwd);
    }
    return [...found].sort((a, b) => (a.kind === "dir" ? 0 : 1) - (b.kind === "dir" ? 0 : 1) || a.path.localeCompare(b.path, "ru"));
  });
  const flat = $derived(!!query.trim() || onlyChanged);
  const picked = $derived(listing.filter((r) => sel.has(r.path)));
  const crumbs = $derived.by(() => {
    const parts = cwd.split("/").filter(Boolean);
    return [{ name: "/", path: "/" }, ...parts.map((name, i) => ({ name, path: "/" + parts.slice(0, i + 1).join("/") }))];
  });

  function goDir(path: string) {
    cwd = path;
    query = "";
    onlyChanged = false;
    sel = new Set();
    anchor = null;
  }

  const MARK: Record<string, { text: string; tone: string; hint: string }> = {
    override: { text: "изменён здесь", tone: "ovr", hint: "Копия этого файла лежит в диске отличий машины: общий файл не тронут." },
    added: { text: "добавлен здесь", tone: "add", hint: "Файла нет на общих дисках: он лежит только на этой машине." },
    deleted: { text: "скрыт", tone: "del", hint: "Файл общего диска скрыт на этой машине. Его можно вернуть." },
  };
  const iconKind = (row: Row) => (row.kind === "dir" ? "folder" : row.item ? "object" : "file");
  const isOwn = (row: Row) => row.mark === "added" || (row.kind === "dir" && row.private);

  async function post<T = unknown>(path: string, body: Record<string, unknown>): Promise<{ data?: T; error?: string }> {
    const { data, error } = await api.POST(`/studio/api/machines/{machine_id}/files/${path}` as "/studio/api/machines/{machine_id}/files/open",
      { params: { path: { machine_id: machine.id } }, body: body as { path: string } });
    if (error || !data) return { error: problem(error, "Не получилось.") };
    return { data: data as T };
  }
  async function call<T = unknown>(path: string, body: Record<string, unknown>, done: string): Promise<T | null> {
    busy = true;
    const result = await post<T>(path, body);
    busy = false;
    if (result.error) { toast(result.error, "error"); return null; }
    if (done) toast(done);
    await load();
    return result.data ?? null;
  }
  /** Одно действие над несколькими путями; в конце один пересчёт и один итог. Возвращает, сколько получилось. */
  async function many(paths: string[], action: string, extra: Record<string, unknown> = {}): Promise<number> {
    busy = true;
    let ok = 0;
    let failed = "";
    for (const path of paths) {
      const result = await post(action, { path, ...extra });
      if (result.error) failed ||= `«${path.split("/").pop()}»: ${result.error}`;
      else ok++;
    }
    busy = false;
    await load();
    if (failed) toast(paths.length > 1 ? `Не все (${ok} из ${paths.length}). ${failed}` : failed, "error");
    return ok;
  }

  async function openRow(row: Row) {
    if (row.kind === "dir") return goDir(row.path);
    if (row.kind === "deleted") return;
    const opened = await call<Schemas["MachineFileOpen"]>("open", { path: row.path }, "");
    if (!opened) return;
    comeFrom(`/machines/${machine.id}/files`, "К файлам машины");
    if (opened.kind === "item" && opened.item) go(`/items/${opened.item}`);
    else if (opened.volume && opened.placement) go(`/volumes/${opened.volume}/text/${opened.placement}`);
  }

  function ask_(kind: NonNullable<typeof dialog>["kind"], list: Row[] = []) {
    const row = list[0];
    field = { name: row && list.length === 1 ? row.name : "", dest: row ? parentOf(row.path) : cwd, owner: row?.owner ?? "", group: row?.group ?? "", mode: row?.mode ?? "" };
    dialog = { kind, rows: list };
  }

  async function submit() {
    if (!dialog) return;
    const { kind, rows: list } = dialog;
    const row = list[0];
    const name = field.name.trim();
    let ok: unknown = null;
    if (kind === "folder") ok = await call("folder", { parent: cwd, name }, "Папка создана.");
    else if (kind === "file") {
      const made = await call<Schemas["MachineFileOpen"]>("file", { parent: cwd, name }, "");
      ok = made;
      if (made?.volume && made.placement) { dialog = null; comeFrom(`/machines/${machine.id}/files`, "К файлам машины"); return go(`/volumes/${made.volume}/text/${made.placement}`); }
    }
    else if (kind === "rename" && row) ok = await call("rename", { path: row.path, name }, "Переименовано.");
    else if (kind === "move") ok = await moveTo(list.map((r) => r.path), field.dest);
    else if (kind === "copy") {
      const count = await many(list.map((r) => r.path), "copy", { dest: field.dest });
      ok = count > 0;
      if (count) toast(count === 1 ? "Копия создана." : `Скопировано: ${count}.`);
    }
    else if (kind === "rights") {
      const count = await many(list.map((r) => r.path), "rights", { owner: field.owner, group: field.group, mode: field.mode });
      ok = count > 0;
      if (count) toast("Права сохранены.");
    }
    if (ok) dialog = null;
  }

  async function moveTo(paths: string[], dest: string): Promise<boolean> {
    const count = await many(paths, "move", { dest });
    if (count) toast(count === 1 ? "Перенесено." : `Перенесено: ${count}.`);
    return count > 0;
  }

  /** Скрыть общее (с отменой) или удалить своё (после вопроса). */
  async function hide(list: Row[]) {
    const mine = list.filter(isOwn);
    if (mine.length) {
      const one = list.length === 1;
      const text = one ? "Файл есть только на этой машине: он удалится совсем." : `Из выбранного ${mine.length} лежит только на этой машине: оно удалится совсем, остальное скроется.`;
      if (!(await ask(one ? `Удалить «${list[0].name}»?` : `Убрать ${list.length} с этой машины?`, text, one ? "Удалить" : "Убрать"))) return;
    }
    const count = await many(list.map((r) => r.path), "delete");
    if (!count) return;
    const shared = list.filter((r) => !isOwn(r)).map((r) => r.path);
    sel = new Set();
    const text = mine.length === list.length ? (count === 1 ? "Удалено." : `Удалено: ${count}.`) : count === 1 ? "Скрыто на этой машине." : `Убрано с машины: ${count}.`;
    toast(text, "ok", shared.length ? { label: "Отменить", run: () => undoHide(shared) } : undefined);
  }
  async function undoHide(paths: string[]) {
    const count = await many(paths, "restore");
    if (count) toast("Возвращено.");
  }
  async function reset(list: Row[]) {
    const one = list.length === 1;
    if (!(await ask(one ? `Сбросить правки «${list[0].name}»?` : `Сбросить правки: ${list.length}?`, "Копии на этой машине удалятся, вернутся файлы общих дисков.", "Сбросить"))) return;
    const count = await many(list.map((r) => r.path), "reset");
    if (count) toast(one ? "Правки сброшены." : `Сброшено: ${count}.`);
  }

  async function protectRow(row: Row) {
    const target = await call<Schemas["MachineFileProtect"]>("protect", { path: row.path }, "");
    if (target) protect = { item: target.item, placed: { placement: target.placement, volume_name: target.volume_name, path: target.path.replace(/^\//, "") } as unknown as Schemas["Placed"] };
  }

  function menuFor(row: Row): MenuItem[] {
    if (!sel.has(row.path)) { sel = new Set([row.path]); anchor = row.path; }
    const list = rows.filter((r) => sel.has(r.path));
    if (list.length > 1) {
      if (list.every((r) => r.kind === "deleted")) return [{ label: `Вернуть: ${list.length}`, run: async () => { sel = new Set(); await undoHide(list.map((r) => r.path)); } }];
      const live = list.filter((r) => r.kind !== "deleted");
      const items: MenuItem[] = [{ label: `Переместить (${live.length})…`, run: () => ask_("move", live) }];
      if (live.every((r) => r.kind !== "dir")) items.push({ label: `Копировать (${live.length})…`, run: () => ask_("copy", live) });
      items.push({ label: "Права…", run: () => ask_("rights", live) }, "sep");
      const overridden = live.filter((r) => r.mark === "override");
      if (overridden.length) items.push({ label: `Сбросить к общему (${overridden.length})`, run: () => reset(overridden) });
      items.push({ label: live.every(isOwn) ? `Удалить (${live.length})…` : `Убрать с машины (${live.length})…`, danger: true, run: () => hide(live) });
      return items;
    }
    if (row.kind === "deleted") return [{ label: "Вернуть", run: () => undoHide([row.path]) }];
    const items: MenuItem[] = [{ label: row.kind === "dir" ? "Открыть папку" : "Открыть и править", run: () => openRow(row) }, "sep"];
    items.push({ label: "Переименовать…", run: () => ask_("rename", [row]) });
    items.push({ label: "Переместить…", run: () => ask_("move", [row]) });
    if (row.kind !== "dir") items.push({ label: "Копировать…", run: () => ask_("copy", [row]) });
    items.push({ label: "Права…", run: () => ask_("rights", [row]) });
    if (row.item) items.push({ label: "Защита на машине…", hint: "Своё условие и свои слои только для этой машины", run: () => protectRow(row) });
    items.push("sep");
    if (row.mark === "override") items.push({ label: "Сбросить к общему", hint: "Убрать копию, вернуть файл общего диска", run: () => reset([row]) });
    items.push({ label: isOwn(row) ? "Удалить…" : "Скрыть на машине", danger: true, run: () => hide([row]) });
    return items;
  }
  function showMenu(event: MouseEvent, row: Row) {
    event.preventDefault();
    menu = { x: event.clientX, y: event.clientY, items: menuFor(row) };
  }
  function menuButton(event: MouseEvent, row: Row) {
    event.stopPropagation();
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    menu = { x: box.left, y: box.bottom + 2, items: menuFor(row) };
  }

  function pick(event: MouseEvent, row: Row) {
    const next = new Set(event.ctrlKey || event.metaKey ? sel : []);
    if (event.shiftKey && anchor) {
      const paths = listing.map((r) => r.path);
      const [from, to] = [paths.indexOf(anchor), paths.indexOf(row.path)].sort((a, b) => a - b);
      if (from >= 0) paths.slice(from, to + 1).forEach((path) => next.add(path));
    } else {
      if ((event.ctrlKey || event.metaKey) && next.has(row.path)) next.delete(row.path);
      else next.add(row.path);
      anchor = row.path;
    }
    sel = next;
  }
  function onKey(event: KeyboardEvent, row: Row) {
    if (event.key === "Enter") openRow(row);
    else if (event.key === " ") { event.preventDefault(); pick(event as unknown as MouseEvent, row); }
    else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      event.preventDefault();
      const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
      menu = { x: box.left + 40, y: box.bottom, items: menuFor(row) };
    }
  }
  function listKey(event: KeyboardEvent) {
    const typing = (event.target as HTMLElement)?.closest("input, textarea, select");
    if (typing) return;
    if (event.key === "a" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); sel = new Set(listing.map((r) => r.path)); }
    else if (event.key === "Escape") sel = new Set();
    else if (event.key === "Delete" && picked.length && !dialog) { const live = picked.filter((r) => r.kind !== "deleted"); if (live.length) hide(live); }
    else if (event.key === "F2" && picked.length === 1 && picked[0].kind !== "deleted") ask_("rename", picked);
  }

  // перетаскивание: на папку в таблице, в дереве или в хлебных крошках
  function startDrag(event: DragEvent, row: Row) {
    if (row.kind === "deleted") return event.preventDefault();
    if (!sel.has(row.path)) { sel = new Set([row.path]); anchor = row.path; }
    dragging = rows.filter((r) => sel.has(r.path) && r.kind !== "deleted").map((r) => r.path);
    event.dataTransfer?.setData("text/plain", dragging.join("\n"));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
    const ghost = document.createElement("div");
    ghost.textContent = dragging.length > 1 ? `Перенести: ${dragging.length}` : `Перенести «${row.name}»`;
    ghost.style.cssText = "position:fixed;top:-100px;padding:4px 10px;background:#243044;color:#fff;border-radius:6px;font:13px sans-serif";
    document.body.append(ghost);
    event.dataTransfer?.setDragImage(ghost, 0, 0);
    setTimeout(() => ghost.remove());
  }
  function endDrag() { dragging = []; dropTo = null; }
  const canDrop = (dest: string) => dragging.length > 0 && dragging.every((path) => path !== dest && parentOf(path) !== dest && !dest.startsWith(path + "/"));
  function over(event: DragEvent, dest: string) {
    if (!canDrop(dest)) return;
    event.preventDefault();
    dropTo = dest;
  }
  async function drop(event: DragEvent, dest: string) {
    event.preventDefault();
    const paths = dragging;
    endDrag();
    if (paths.length && canDropPaths(paths, dest)) await moveTo(paths, dest);
  }
  const canDropPaths = (paths: string[], dest: string) => paths.every((path) => path !== dest && !dest.startsWith(path + "/"));

  const destChoices = $derived.by(() => {
    const moving = dialog?.rows.filter((r) => r.kind === "dir").map((r) => r.path) ?? [];
    return ["/", ...dirs.map((d) => d.path)].filter((path) => !moving.some((from) => path === from || path.startsWith(from + "/")));
  });
  const children = (path: string) => dirs.filter((d) => parentOf(d.path) === path);
  const size = (row: Row) => (row.item?.size == null ? "" : row.item.size < 1024 ? `${row.item.size} Б` : `${(row.item.size / 1024).toFixed(1)} КБ`);
  const titles = { folder: "Новая папка", file: "Новый файл", rename: "Переименовать", move: "Переместить", copy: "Копировать", rights: "Права" } as const;
</script>

{#snippet branch(path: string, depth: number)}
  {#each children(path) as dir (dir.path)}
    <div class="node" style="padding-left:{8 + depth * 14}px">
      {#if children(dir.path).length}
        <button class="tw" aria-label={open_[dir.path] ? "Свернуть" : "Развернуть"} onclick={() => (open_[dir.path] = !open_[dir.path])}>{open_[dir.path] ? "▾" : "▸"}</button>
      {:else}<span class="tw"></span>{/if}
      <button class="nbtn" class:on={cwd === dir.path && !flat} class:drop={dropTo === dir.path} onclick={() => goDir(dir.path)}
              ondragover={(e) => over(e, dir.path)} ondragleave={() => (dropTo = null)} ondrop={(e) => drop(e, dir.path)}>
        <FileIcon kind="folder" size={14} />{dir.name}{#if dir.mark === "override" || dir.mark === "added"}<i class="ch" title="Изменено на этой машине"></i>{/if}
      </button>
    </div>
    {#if open_[dir.path]}{@render branch(dir.path, depth + 1)}{/if}
  {/each}
{/snippet}

<div class="files">
  <header class="bar">
    <nav class="crumbs" aria-label="Путь">
      {#each crumbs as crumb, i}{#if i > 1}<span class="sep">/</span>{/if}<button class:drop={dropTo === crumb.path} onclick={() => goDir(crumb.path)}
        ondragover={(e) => over(e, crumb.path)} ondragleave={() => (dropTo = null)} ondrop={(e) => drop(e, crumb.path)}>{crumb.name}</button>{/each}
    </nav>
    <span class="spacer"></span>
    <input class="field search" placeholder="Поиск по всей машине" bind:value={query} aria-label="Поиск" />
    <button class="pill" class:on={onlyChanged} aria-pressed={onlyChanged} onclick={() => (onlyChanged = !onlyChanged)} disabled={!changed && !onlyChanged}
            title="Только то, что отличается от общих дисков">Изменено на машине · {changed}</button>
    <div class="adder">
      <button class="btn primary" onclick={(e) => { e.stopPropagation(); creating = !creating; }} aria-haspopup="menu" aria-expanded={creating}>Создать ▾</button>
      {#if creating}
        <div class="cmenu" role="menu">
          <button role="menuitem" onclick={() => { creating = false; ask_("folder"); }}>Новая папка</button>
          <button role="menuitem" onclick={() => { creating = false; ask_("file"); }}>Новый файл<span class="muted small">без объекта, любое расширение</span></button>
        </div>
      {/if}
    </div>
  </header>

  <div class="body">
    <aside class="tree">
      <div class="node" style="padding-left:8px"><span class="tw"></span>
        <button class="nbtn" class:on={cwd === "/" && !flat} class:drop={dropTo === "/"} onclick={() => goDir("/")}
                ondragover={(e) => over(e, "/")} ondragleave={() => (dropTo = null)} ondrop={(e) => drop(e, "/")}><FileIcon kind="folder" size={14} />/ (корень)</button>
      </div>
      {@render branch("/", 1)}
      <p class="muted small note">Правки ложатся в
        {#if overlayDisk}<a href="#/volumes/{overlayDisk}">диск отличий</a>{:else}диск отличий (создастся при первой правке){/if} этой машины. Общие диски не меняются.</p>
    </aside>

    <section class="list" aria-label="Файлы" onkeydown={listKey} role="presentation">
      <div class="row head">
        <span>Имя</span><span>Откуда<Hint text="Диск, из которого пришёл файл. «Изменён здесь», «добавлен здесь» и «скрыт» значат, что на этой машине файл отличается от общих дисков." /></span>
        <span>Права</span><span class="num">Размер</span><span></span>
      </div>
      {#if loading}
        <p class="muted pad">Загрузка…</p>
      {:else}
        {#each listing as row (row.path)}
          <div class="row" class:sel={sel.has(row.path)} class:gone={row.kind === "deleted"} class:drop={dropTo === row.path} class:dragged={dragging.includes(row.path)}
               role="row" tabindex="0" draggable={row.kind !== "deleted"} aria-selected={sel.has(row.path)}
               ondblclick={() => openRow(row)} onclick={(e) => pick(e, row)} oncontextmenu={(e) => showMenu(e, row)} onkeydown={(e) => onKey(e, row)}
               ondragstart={(e) => startDrag(e, row)} ondragend={endDrag}
               ondragover={(e) => row.kind === "dir" && over(e, row.path)} ondragleave={() => (dropTo = null)} ondrop={(e) => row.kind === "dir" && drop(e, row.path)}>
            <span class="name">
              <FileIcon kind={iconKind(row)} own={row.kind === "file" && !row.item} size={16} />
              <button class="link" onclick={(e) => { e.stopPropagation(); openRow(row); }}>{flat ? row.path : row.name}</button>
              {#if row.hidden}<span class="chip" title="Скрытый файл">скрыт ls</span>{/if}
              {#if row.kind === "file" && !row.item}<span class="chip own" title="Файл без объекта: текст лежит прямо в диске">без объекта</span>{/if}
              {#if row.layers}<span class="chip warn" title="У файла есть слои защиты">слои</span>{/if}
              {#if row.condition}<span class="chip warn" title="У файла есть условие доступа">условие</span>{/if}
              {#if MARK[row.mark]}<span class="mk {MARK[row.mark].tone}" title={MARK[row.mark].hint}>{MARK[row.mark].text}</span>{/if}
            </span>
            <span class="mono muted">{row.volume || "—"}</span>
            <span class="mono muted">{row.mode || "open"}{row.owner ? ` ${row.owner}${row.group ? `:${row.group}` : ""}` : ""}</span>
            <span class="num mono muted">{size(row)}</span>
            <span class="more"><button class="btn ghost" aria-label="Действия с {row.name}" onclick={(e) => menuButton(e, row)}>⋯</button></span>
          </div>
        {:else}
          <p class="muted pad">{flat ? "Ничего не нашлось." : "Папка пуста."}</p>
        {/each}
      {/if}
    </section>

    <FileDetails rows={picked} folder={cwd} shown={listing.length} onopen={openRow} onrename={(row) => ask_("rename", [row])} onprotect={protectRow} />
  </div>
</div>

<svelte:window onclick={() => (creating = false)} />
{#if menu}<ContextMenu x={menu.x} y={menu.y} items={menu.items} onclose={() => (menu = null)} />{/if}
{#if protect}<PlacementProtection itemId={protect.item} placed={protect.placed} onclose={() => (protect = null)} onsaved={load} />{/if}

{#if dialog}
  {@const kind = dialog.kind}
  {@const list = dialog.rows}
  <Dialog title={list.length > 1 ? `${titles[kind]}: ${list.length}` : titles[kind]}
          confirm={kind === "file" ? "Создать и открыть" : kind === "rights" ? "Сохранить" : "Готово"} {busy} onsubmit={submit} onclose={() => (dialog = null)}
          disabled={(kind === "folder" || kind === "file" || kind === "rename") && !field.name.trim()}>
    {#if kind === "folder" || kind === "file" || kind === "rename"}
      <label><span class="label">{kind === "rename" ? "Новое имя" : `Имя (в ${cwd})`}</span><input class="field mono" bind:value={field.name} placeholder={kind === "file" ? "notes.txt, data.xyz…" : ""} /></label>
      {#if kind === "file"}<p class="muted small">Файл создаётся без объекта и может иметь любое расширение, даже несуществующее.</p>{/if}
    {:else if kind === "move" || kind === "copy"}
      <label><span class="label">В папку</span>
        <select class="field mono" bind:value={field.dest}>{#each destChoices as path}<option value={path}>{path}</option>{/each}</select></label>
      <p class="muted small">{kind === "move" ? "Из общего диска файл или папка скрывается на старом месте и появляется на новом (папка со всем содержимым): общий диск не меняется." : "Объект копируется отдельным объектом: правки копии не затронут оригинал."}</p>
    {:else}
      <div class="trio">
        <label><span class="label">Владелец</span><input class="field mono" bind:value={field.owner} /></label>
        <label><span class="label">Группа</span><input class="field mono" bind:value={field.group} /></label>
        <label><span class="label">Права<Hint text="Три восьмеричные цифры: владелец, группа, остальные (чтение 4, запись 2, вход или запуск 1): 640, 755. Пусто: открыто." /></span><input class="field mono" bind:value={field.mode} placeholder="640" /></label>
      </div>
    {/if}
  </Dialog>
{/if}

<style>
  .files { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .bar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 10px 20px; border-bottom: 1px solid var(--line-soft); }
  .crumbs { display: flex; align-items: center; gap: 2px; font-family: var(--mono); }
  .crumbs button { border: 0; background: none; color: var(--accent); cursor: pointer; padding: 2px 4px; border-radius: var(--radius-s); }
  .crumbs button:hover, .crumbs button.drop { background: var(--panel-2); }
  .sep { color: var(--faint); }
  .spacer { flex: 1; }
  .search { width: 240px; }
  .pill { height: 30px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-2); cursor: pointer; }
  .pill.on { border-color: var(--accent); background: var(--accent-soft); }
  .pill:disabled { opacity: 0.5; cursor: default; }
  .adder { position: relative; }
  .cmenu { position: absolute; right: 0; top: calc(100% + 4px); z-index: 6; min-width: 230px; padding: 6px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45); }
  .cmenu button { display: flex; flex-direction: column; width: 100%; text-align: left; padding: 7px 10px; border: 0; border-radius: var(--radius-s); background: none; cursor: pointer; }
  .cmenu button:hover { background: var(--raise); }
  .body { flex: 1; min-height: 0; display: grid; grid-template-columns: 250px 1fr auto; }
  .tree { overflow: auto; padding: 8px 0 16px; border-right: 1px solid var(--line-soft); }
  .node { display: flex; align-items: center; gap: 2px; padding-right: 8px; }
  .tw { width: 16px; flex: none; border: 0; background: none; color: var(--muted); cursor: pointer; padding: 0; }
  .nbtn { display: flex; align-items: center; gap: 6px; flex: 1; padding: 3px 6px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; min-width: 0; }
  .nbtn:hover { background: var(--panel); }
  .nbtn.on { background: var(--accent-soft); }
  .nbtn.drop, .row.drop { outline: 2px dashed var(--accent); outline-offset: -2px; background: var(--accent-soft); }
  .ch { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); margin-left: auto; }
  .note { margin: 14px 12px 0; }
  .list { overflow: auto; min-width: 0; }
  .row { display: grid; grid-template-columns: minmax(280px, 1fr) 120px 110px 60px 36px; gap: 10px; align-items: center; padding: 0 16px; height: 36px; border-bottom: 1px solid var(--line-soft); user-select: none; }
  .row.head { position: sticky; top: 0; z-index: 1; background: var(--bg); height: 30px; color: var(--faint); font-size: 12px; }
  .row:not(.head):hover { background: var(--panel); }
  .row.sel { background: var(--accent-soft); }
  .row.dragged { opacity: 0.45; }
  .row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .row.gone .link { text-decoration: line-through; color: var(--muted); }
  .name { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .link { flex: 0 1 auto; min-width: 56px; border: 0; background: none; padding: 0; color: var(--text); cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
  .link:hover { color: var(--accent); }
  .num { text-align: right; }
  .more { text-align: right; }
  .more .btn { padding: 0 8px; height: 26px; }
  .name .chip, .mk { flex: none; }
  .chip.own { background: var(--raise); color: var(--muted); }
  .chip.warn { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  .mk { padding: 0 7px; border-radius: 999px; font-size: 11.5px; line-height: 19px; white-space: nowrap; }
  .mk.ovr { background: var(--accent-soft); color: var(--accent); }
  .mk.add { background: rgba(95, 208, 160, 0.14); color: var(--ok); }
  .mk.del { background: var(--danger-soft); color: var(--danger); }
  .pad { padding: 14px 16px; }
  .trio { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
  .small { font-size: 12px; }
</style>
