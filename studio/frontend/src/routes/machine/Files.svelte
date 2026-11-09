<script lang="ts">
  // Файлы машины: её файловая система целиком (все диски вместе). Любая правка ложится в диск отличий этой машины,
  // общие диски не меняются. Пометки показывают, откуда файл: общий, изменён здесь, добавлен здесь, скрыт.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import FileIcon from "../../lib/FileIcon.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import ContextMenu, { type MenuItem } from "../volume/ContextMenu.svelte";

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
  let dialog = $state<null | { kind: "folder" | "file" | "rename" | "move" | "copy" | "rights"; row?: Row }>(null);
  let field = $state({ name: "", dest: "/", owner: "", group: "", mode: "" });
  let busy = $state(false);
  let selected = $state<string | null>(null);

  function read(): string {
    try { return sessionStorage.getItem(key()) || "/"; } catch { return "/"; }
  }
  $effect(() => { try { sessionStorage.setItem(key(), cwd); } catch { /* вкладка без хранилища */ } });

  async function load() {
    const { data } = await api.GET("/studio/api/machines/{machine_id}/files", { params: { path: { machine_id: machine.id } } });
    if (data) { rows = data.rows; overlayDisk = data.overlay ?? null; changed = data.changed; }
    loading = false;
    if (cwd !== "/" && !rows.some((r) => r.path === cwd && r.kind === "dir")) cwd = "/";
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
  const crumbs = $derived.by(() => {
    const parts = cwd.split("/").filter(Boolean);
    return [{ name: "/", path: "/" }, ...parts.map((name, i) => ({ name, path: "/" + parts.slice(0, i + 1).join("/") }))];
  });

  const MARK: Record<string, { text: string; tone: string; hint: string }> = {
    override: { text: "изменён здесь", tone: "ovr", hint: "Копия этого файла лежит в диске отличий машины: общий файл не тронут." },
    added: { text: "добавлен здесь", tone: "add", hint: "Файла нет на общих дисках: он лежит только на этой машине." },
    deleted: { text: "скрыт", tone: "del", hint: "Файл общего диска скрыт на этой машине. Его можно вернуть." },
    base: { text: "общий", tone: "base", hint: "Файл общего диска. Правка создаст копию на этой машине." },
  };
  const iconKind = (row: Row) => (row.kind === "dir" ? "folder" : row.item ? "object" : "file");

  async function call<T = unknown>(path: string, body: Record<string, unknown>, done: string): Promise<T | null> {
    busy = true;
    const { data, error } = await api.POST(`/studio/api/machines/{machine_id}/files/${path}` as "/studio/api/machines/{machine_id}/files/open",
      { params: { path: { machine_id: machine.id } }, body: body as { path: string } });
    busy = false;
    if (error || !data) { toast(problem(error, "Не получилось."), "error"); return null; }
    if (done) toast(done);
    await load();
    return data as T;
  }

  async function openRow(row: Row) {
    if (row.kind === "dir") { cwd = row.path; query = ""; onlyChanged = false; return; }
    if (row.kind === "deleted") return;
    const opened = await call<Schemas["MachineFileOpen"]>("open", { path: row.path }, "");
    if (!opened) return;
    if (opened.kind === "item" && opened.item) go(`/items/${opened.item}`);
    else if (opened.volume && opened.placement) go(`/volumes/${opened.volume}/text/${opened.placement}`);
  }

  function ask_(kind: NonNullable<typeof dialog>["kind"], row?: Row) {
    field = { name: row ? row.name : "", dest: row ? parentOf(row.path) : cwd, owner: row?.owner ?? "", group: row?.group ?? "", mode: row?.mode ?? "" };
    dialog = { kind, row };
  }

  async function submit() {
    if (!dialog) return;
    const { kind, row } = dialog;
    const name = field.name.trim();
    let ok: unknown = null;
    if (kind === "folder") ok = await call("folder", { parent: cwd, name }, "Папка создана.");
    else if (kind === "file") {
      const made = await call<Schemas["MachineFileOpen"]>("file", { parent: cwd, name }, "");
      ok = made;
      if (made?.volume && made.placement) { dialog = null; return go(`/volumes/${made.volume}/text/${made.placement}`); }
    }
    else if (kind === "rename" && row) ok = await call("rename", { path: row.path, name }, "Переименовано.");
    else if (kind === "move" && row) ok = await call("move", { path: row.path, dest: field.dest }, "Перенесено.");
    else if (kind === "copy" && row) ok = await call("copy", { path: row.path, dest: field.dest }, "Копия создана.");
    else if (kind === "rights" && row) ok = await call("rights", { path: row.path, owner: field.owner, group: field.group, mode: field.mode }, "Права сохранены.");
    if (ok) dialog = null;
  }

  async function hide(row: Row) {
    const own = row.mark === "added";
    const text = own ? "Файл есть только на этой машине: он удалится совсем." : "Общий диск не изменится: файл пропадёт только из вида этой машины, его можно вернуть.";
    if (!(await ask(own ? `Удалить «${row.name}»?` : `Скрыть «${row.name}» на этой машине?`, text, own ? "Удалить" : "Скрыть"))) return;
    await call("delete", { path: row.path }, own ? "Удалено." : "Скрыто на этой машине.");
  }
  async function reset(row: Row) {
    if (!(await ask(`Сбросить правки «${row.name}»?`, "Копия на этой машине удалится, вернётся файл общего диска.", "Сбросить"))) return;
    await call("reset", { path: row.path }, "Правки сброшены.");
  }

  function menuFor(row: Row): MenuItem[] {
    if (row.kind === "deleted") return [{ label: "Вернуть", run: () => call("restore", { path: row.path }, "Файл возвращён.") }];
    const items: MenuItem[] = [{ label: row.kind === "dir" ? "Открыть папку" : "Открыть и править", run: () => openRow(row) }, "sep"];
    items.push({ label: "Переименовать…", run: () => ask_("rename", row) });
    items.push({ label: "Переместить…", run: () => ask_("move", row) });
    if (row.kind !== "dir") items.push({ label: "Копировать…", run: () => ask_("copy", row) });
    items.push({ label: "Права…", run: () => ask_("rights", row) }, "sep");
    if (row.mark === "override") items.push({ label: "Сбросить к общему", hint: "Убрать копию, вернуть файл общего диска", run: () => reset(row) });
    items.push({ label: row.mark === "added" ? "Удалить…" : "Скрыть на машине…", danger: true, run: () => hide(row) });
    return items;
  }
  function showMenu(event: MouseEvent, row: Row) {
    event.preventDefault();
    selected = row.path;
    menu = { x: event.clientX, y: event.clientY, items: menuFor(row) };
  }
  function menuButton(event: MouseEvent, row: Row) {
    event.stopPropagation();
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    selected = row.path;
    menu = { x: box.left, y: box.bottom + 2, items: menuFor(row) };
  }

  const destChoices = $derived(["/", ...dirs.map((d) => d.path)].filter((path) => !(dialog?.row?.kind === "dir" && (path === dialog.row.path || path.startsWith(dialog.row.path + "/")))));
  const children = (path: string) => dirs.filter((d) => parentOf(d.path) === path);
  const size = (row: Row) => (row.item?.size == null ? "" : row.item.size < 1024 ? `${row.item.size} Б` : `${(row.item.size / 1024).toFixed(1)} КБ`);
</script>

{#snippet branch(path: string, depth: number)}
  {#each children(path) as dir (dir.path)}
    <div class="node" style="padding-left:{8 + depth * 14}px">
      {#if children(dir.path).length}
        <button class="tw" aria-label={open_[dir.path] ? "Свернуть" : "Развернуть"} onclick={() => (open_[dir.path] = !open_[dir.path])}>{open_[dir.path] ? "▾" : "▸"}</button>
      {:else}<span class="tw"></span>{/if}
      <button class="nbtn" class:on={cwd === dir.path && !flat} onclick={() => { cwd = dir.path; query = ""; onlyChanged = false; }}>
        <FileIcon kind="folder" size={14} />{dir.name}{#if dir.mark === "override" || dir.mark === "added"}<i class="ch" title="Изменено на этой машине"></i>{/if}
      </button>
    </div>
    {#if open_[dir.path]}{@render branch(dir.path, depth + 1)}{/if}
  {/each}
{/snippet}

<div class="files">
  <header class="bar">
    <nav class="crumbs" aria-label="Путь">
      {#each crumbs as crumb, i}{#if i > 1}<span class="sep">/</span>{/if}<button onclick={() => { cwd = crumb.path; query = ""; onlyChanged = false; }}>{crumb.name}</button>{/each}
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
        <button class="nbtn" class:on={cwd === "/" && !flat} onclick={() => { cwd = "/"; query = ""; onlyChanged = false; }}><FileIcon kind="folder" size={14} />/ (корень)</button>
      </div>
      {@render branch("/", 1)}
      <p class="muted small note">Правки ложатся в
        {#if overlayDisk}<a href="#/volumes/{overlayDisk}">диск отличий</a>{:else}диск отличий (создастся при первой правке){/if} этой машины. Общие диски не меняются.</p>
    </aside>

    <section class="list" aria-label="Файлы">
      <div class="row head">
        <span>Имя</span><span>Откуда<Hint text="Диск, из которого пришёл файл. «Изменён здесь», «добавлен здесь» и «скрыт» значат, что на этой машине файл отличается от общих дисков." /></span>
        <span>Права</span><span class="num">Размер</span><span></span>
      </div>
      {#if loading}
        <p class="muted pad">Загрузка…</p>
      {:else}
        {#each listing as row (row.path)}
          <div class="row" class:sel={selected === row.path} class:gone={row.kind === "deleted"} role="row" tabindex="0"
               ondblclick={() => openRow(row)} onclick={() => (selected = row.path)} oncontextmenu={(e) => showMenu(e, row)}
               onkeydown={(e) => { if (e.key === "Enter") openRow(row); else if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) { e.preventDefault(); selected = row.path; const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); menu = { x: r.left + 40, y: r.bottom, items: menuFor(row) }; } }}>
            <span class="name">
              <FileIcon kind={iconKind(row)} own={row.kind === "file" && !row.item} size={16} />
              <button class="link" onclick={(e) => { e.stopPropagation(); openRow(row); }}>{flat ? row.path : row.name}</button>
              {#if row.hidden}<span class="chip" title="Скрытый файл">скрыт ls</span>{/if}
              {#if row.kind === "file" && !row.item}<span class="chip own" title="Файл без объекта: текст лежит прямо в диске">без объекта</span>{/if}
              {#if MARK[row.mark] && (row.mark !== "base" || false)}<span class="mk {MARK[row.mark].tone}" title={MARK[row.mark].hint}>{MARK[row.mark].text}</span>{/if}
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
  </div>
</div>

<svelte:window onclick={() => (creating = false)} />
{#if menu}<ContextMenu x={menu.x} y={menu.y} items={menu.items} onclose={() => (menu = null)} />{/if}

{#if dialog}
  {@const kind = dialog.kind}
  <Dialog title={{ folder: "Новая папка", file: "Новый файл", rename: "Переименовать", move: "Переместить", copy: "Копировать", rights: "Права" }[kind]}
          confirm={kind === "file" ? "Создать и открыть" : kind === "rights" ? "Сохранить" : "Готово"} {busy} onsubmit={submit} onclose={() => (dialog = null)}
          disabled={(kind === "folder" || kind === "file" || kind === "rename") && !field.name.trim()}>
    {#if kind === "folder" || kind === "file" || kind === "rename"}
      <label><span class="label">{kind === "rename" ? "Новое имя" : `Имя (в ${cwd})`}</span><input class="field mono" bind:value={field.name} placeholder={kind === "file" ? "notes.txt, data.xyz…" : ""} /></label>
      {#if kind === "file"}<p class="muted small">Файл создаётся без объекта и может иметь любое расширение, даже несуществующее.</p>{/if}
    {:else if kind === "move" || kind === "copy"}
      <label><span class="label">В папку</span>
        <select class="field mono" bind:value={field.dest}>{#each destChoices as path}<option value={path}>{path}</option>{/each}</select></label>
      <p class="muted small">{kind === "move" ? "Файл общего диска скрывается на старом месте и появляется на новом: общий диск не меняется." : "Объект копируется отдельным объектом: правки копии не затронут оригинал."}</p>
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
  .crumbs button:hover { background: var(--panel-2); }
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
  .body { flex: 1; min-height: 0; display: grid; grid-template-columns: 250px 1fr; }
  .tree { overflow: auto; padding: 8px 0 16px; border-right: 1px solid var(--line-soft); }
  .node { display: flex; align-items: center; gap: 2px; padding-right: 8px; }
  .tw { width: 16px; flex: none; border: 0; background: none; color: var(--muted); cursor: pointer; padding: 0; }
  .nbtn { display: flex; align-items: center; gap: 6px; flex: 1; padding: 3px 6px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; min-width: 0; }
  .nbtn:hover { background: var(--panel); }
  .nbtn.on { background: var(--accent-soft); }
  .ch { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); margin-left: auto; }
  .note { margin: 14px 12px 0; }
  .list { overflow: auto; min-width: 0; }
  .row { display: grid; grid-template-columns: minmax(220px, 1fr) 130px 150px 70px 40px; gap: 10px; align-items: center; padding: 0 16px; height: 36px; border-bottom: 1px solid var(--line-soft); }
  .row.head { position: sticky; top: 0; z-index: 1; background: var(--bg); height: 30px; color: var(--faint); font-size: 12px; }
  .row:not(.head):hover, .row.sel { background: var(--panel); }
  .row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .row.gone .link { text-decoration: line-through; color: var(--muted); }
  .name { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .link { border: 0; background: none; padding: 0; color: var(--text); cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
  .link:hover { color: var(--accent); }
  .num { text-align: right; }
  .more { text-align: right; }
  .more .btn { padding: 0 8px; height: 26px; }
  .chip.own { background: var(--raise); color: var(--muted); }
  .mk { padding: 0 7px; border-radius: 999px; font-size: 11.5px; line-height: 19px; white-space: nowrap; }
  .mk.ovr { background: var(--accent-soft); color: var(--accent); }
  .mk.add { background: rgba(95, 208, 160, 0.14); color: var(--ok); }
  .mk.del { background: var(--danger-soft); color: var(--danger); }
  .pad { padding: 14px 16px; }
  .trio { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
  .small { font-size: 12px; }
</style>
