<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import FileIcon from "../lib/FileIcon.svelte";
  import FormatOptions from "../lib/FormatOptions.svelte";
  import Hint from "../lib/Hint.svelte";
  import { describe, typeHint } from "../lib/fileKind";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import PutObject from "./volume/PutObject.svelte";
  import ContextMenu, { type MenuItem } from "./volume/ContextMenu.svelte";
  import Details from "./volume/Details.svelte";
  import PlacementProtection from "./item/PlacementProtection.svelte";

  type Node = Schemas["Node"];

  let { id, folder }: { id: number; folder: number | null } = $props();

  let volume = $state<Schemas["VolumeTree"] | null>(null);
  let formats = $state<Schemas["Format"][]>([]);
  let selected = $state<Set<number>>(new Set());
  let propsOpen = $state(false);
  let props_ = $state({ slug: "", name: "", label: "", uuid: "", capacity_gb: null as number | null, used_gb: null as number | null });
  let propErrors = $state<Record<string, string[]>>({});

  // раскрытые папки дерева помнятся на время работы (по тому)
  const openKey = () => `studio.tree.${id}`;
  let opened = $state<Set<number>>(restore());
  function restore(): Set<number> {
    try { return new Set(JSON.parse(sessionStorage.getItem(openKey()) ?? "[]")); } catch { return new Set(); }
  }
  function remember() {
    try { sessionStorage.setItem(openKey(), JSON.stringify([...opened])); } catch { /* память браузера закрыта: не страшно */ }
  }

  function openProps() {
    if (!volume) return;
    props_ = { slug: volume.slug, name: volume.name, label: volume.label, uuid: volume.uuid, capacity_gb: volume.capacity_gb ?? null, used_gb: volume.used_gb ?? null };
    propErrors = {};
    propsOpen = true;
  }

  async function saveProps() {
    const { data, error } = await api.PUT("/studio/api/volumes/{volume_id}", { params: { path: { volume_id: id } }, body: props_ });
    if (error || !data) {
      propErrors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    if (volume) volume = { ...volume, ...data, rows: volume.rows };
    propsOpen = false;
    toast("Свойства тома сохранены.");
  }

  const gbOf = (value: string) => (value === "" ? null : Math.max(0, Math.round(+value)));

  function randomUsed() {
    if (props_.capacity_gb) props_.used_gb = Math.round((props_.capacity_gb * (20 + Math.random() * 50)) / 100);
  }

  type DialogKind = "folder" | "file" | "object" | "rename" | "delete" | "rights";
  let putting = $state(false);
  let menu = $state<null | { x: number; y: number; items: MenuItem[] }>(null);
  let protect = $state<Node | null>(null);

  // права: владелец, группа и три цифры; при нескольких выбранных меняется только то, что тронули
  type RightsKey = "owner" | "group" | "mode";
  let rights = $state({ owner: "", group: "", mode: "" });
  let touched = $state<Set<RightsKey>>(new Set());
  const PRESETS: [string, string][] = [
    ["644", "все читают, пишет владелец"], ["640", "читают владелец и группа"], ["600", "только владелец"],
    ["755", "все читают и запускают"], ["700", "только владелец, с запуском"], ["", "открыто всем"],
  ];
  const sameOf = (key: RightsKey) => (new Set(selectedNodes.map((node) => node[key])).size === 1 ? selectedNodes[0][key] : "");
  const mixed = (key: RightsKey) => selectedNodes.length > 1 && new Set(selectedNodes.map((node) => node[key])).size > 1;
  function openRights() {
    rights = { owner: sameOf("owner"), group: sameOf("group"), mode: sameOf("mode") };
    touched = new Set();
    dialog = { kind: "rights", name: "", format: "" };
  }
  function setRight(key: RightsKey, value: string) {
    rights[key] = key === "mode" ? value.replace(/[^0-7]/g, "").slice(0, 3) : value;
    touched = new Set([...touched, key]);
  }
  const WHO = ["Владелец", "Группа", "Остальные"];
  const BITS: [number, string][] = [[4, "чтение"], [2, "запись"], [1, "запуск"]];
  function decode(mode: string): string {
    if (!/^[0-7]{3}$/.test(mode)) return mode ? "Нужны три цифры от 0 до 7, например 640." : "Права не заданы: файл открыт всем.";
    return [...mode].map((digit, at) => {
      const can = BITS.filter(([bit]) => (+digit & bit) !== 0).map(([, name]) => name);
      return `${WHO[at]}: ${can.length ? can.join(", ") : "ничего"}`;
    }).join(". ") + ".";
  }

  // панель сведений справа: можно скрыть, выбор запоминается
  const DETAILS_KEY = "studio.volumeDetails";
  let showDetails = $state((() => { try { return localStorage.getItem(DETAILS_KEY) !== "off"; } catch { return true; } })());
  function toggleDetails() {
    showDetails = !showDetails;
    try { localStorage.setItem(DETAILS_KEY, showDetails ? "on" : "off"); } catch { /* ничего */ }
  }
  let dialog = $state<null | { kind: DialogKind; name: string; format: string }>(null);
  let busy = $state(false);
  let dragging = $state<number[]>([]);
  let dropTarget = $state<number | null | undefined>(undefined);

  // сортировка таблицы: папки всегда выше файлов
  let sortKey = $state<"name" | "type" | "size">("name");
  let sortDown = $state(false);

  const byId = $derived(new Map((volume?.rows ?? []).map((row) => [row.id, row])));
  const children = $derived.by(() => {
    const found = new Map<number | null, Node[]>();
    for (const row of volume?.rows ?? []) {
      const list = found.get(row.parent) ?? [];
      list.push(row);
      found.set(row.parent, list);
    }
    for (const list of found.values()) {
      list.sort((a, b) => (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1) || a.name.localeCompare(b.name, "ru"));
    }
    return found;
  });
  const count = (nodeId: number | null) => children.get(nodeId)?.length ?? 0;
  // путь каждой папки: нужен поиску, который показывает файлы всего тома
  const paths = $derived.by(() => {
    const found = new Map<number | null, string>([[null, "/"]]);
    const walk = (node: Node): string => {
      const known = found.get(node.id);
      if (known !== undefined) return known;
      const text = (node.parent === null ? "" : walk(byId.get(node.parent)!)).replace(/^\/$/, "") + "/" + node.name;
      found.set(node.id, text);
      return text;
    };
    for (const row of volume?.rows ?? []) walk(row);
    return found;
  });
  const dirOf = (node: Node) => (node.parent === null ? "/" : paths.get(node.parent) ?? "/");

  const FILTERS: [string, string, (node: Node) => boolean][] = [
    ["guard", "С защитой", (node) => node.layers || node.condition],
    ["hidden", "Скрытые", (node) => node.hidden],
    ["system", "Системные", (node) => node.system],
    ["object", "Объекты", (node) => !!node.item],
    ["own", "Файлы без объекта", (node) => node.own],
  ];
  let query = $state("");
  let active = $state<Set<string>>(new Set());
  const searching = $derived(query.trim() !== "" || active.size > 0);
  function toggleFilter(key: string) {
    const next = new Set(active);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    active = next;
  }
  function clearSearch() {
    query = "";
    active = new Set();
  }

  const listing = $derived.by(() => {
    let rows: Node[];
    if (searching) {
      const words = query.trim().toLowerCase();
      const need = FILTERS.filter(([key]) => active.has(key));
      rows = (volume?.rows ?? []).filter((node) =>
        (!words || node.name.toLowerCase().includes(words) || (paths.get(node.id) ?? "").toLowerCase().includes(words)) && need.every(([, , test]) => test(node)),
      );
    } else rows = [...(children.get(folder) ?? [])];
    const sign = sortDown ? -1 : 1;
    const key = (node: Node) => (sortKey === "size" ? node.size ?? -1 : sortKey === "type" ? describe(node, formats, count(node.id)).label : node.name);
    return rows.sort((a, b) => {
      const folders = (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1);
      if (folders) return folders;
      const x = key(a), y = key(b);
      return sign * (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "ru")) || a.name.localeCompare(b.name, "ru");
    });
  });
  const crumbs = $derived.by(() => {
    const chain: Node[] = [];
    let node = folder === null ? undefined : byId.get(folder);
    while (node) {
      chain.unshift(node);
      node = node.parent === null ? undefined : byId.get(node.parent);
    }
    return chain;
  });
  const single = $derived(selected.size === 1 ? byId.get([...selected][0]) : undefined);
  const selectedNodes = $derived([...selected].map((key) => byId.get(key)).filter((node): node is Node => !!node));
  const allHidden = $derived(selected.size > 0 && [...selected].every((key) => byId.get(key)?.hidden));

  function sortBy(key: "name" | "type" | "size") {
    if (sortKey === key) sortDown = !sortDown;
    else { sortKey = key; sortDown = false; }
  }
  const arrow = (key: string) => (sortKey === key ? (sortDown ? " ↓" : " ↑") : "");

  async function load() {
    const { data, error } = await api.GET("/studio/api/volumes/{volume_id}", { params: { path: { volume_id: id } } });
    if (error || !data) return toast("Том не найден.", "error");
    volume = data;
    selected = new Set([...selected].filter((key) => data.rows.some((row) => row.id === key)));
    for (const node of crumbs) opened.add(node.id);
    remember();
  }

  onMount(async () => {
    const { data } = await api.GET("/studio/api/formats");
    formats = data ?? [];
    await load();
  });

  function openFolder(target: number | null) {
    selected = new Set();
    clearSearch();
    go(target === null ? `/volumes/${id}` : `/volumes/${id}/${target}`);
  }

  function activate(node: Node) {
    if (node.kind === "folder") openFolder(node.id);
    else if (node.item) go(`/items/${node.item.id}`);
    else if (node.kind === "file") go(`/volumes/${id}/text/${node.id}`);
  }

  function pick(node: Node, event: MouseEvent) {
    const next = new Set(event.ctrlKey || event.metaKey ? selected : []);
    if (event.shiftKey && selected.size) {
      const ids = listing.map((row) => row.id);
      const from = ids.indexOf([...selected].at(-1)!);
      const to = ids.indexOf(node.id);
      for (const key of ids.slice(Math.min(from, to), Math.max(from, to) + 1)) next.add(key);
    } else if (next.has(node.id)) next.delete(node.id);
    else next.add(node.id);
    selected = next;
  }

  function toggle(node: Node) {
    const next = new Set(opened);
    if (next.has(node.id)) next.delete(node.id);
    else next.add(node.id);
    opened = next;
    remember();
  }

  async function run(action: () => Promise<{ error?: unknown }>, done: string) {
    busy = true;
    const { error } = await action();
    busy = false;
    if (error) return toast(problem(error), "error");
    dialog = null;
    toast(done);
    await load();
  }

  function submit() {
    if (!dialog) return;
    const path = { volume_id: id };
    if (dialog.kind === "folder") {
      run(() => api.POST("/studio/api/volumes/{volume_id}/folders", { params: { path }, body: { parent: folder, name: dialog!.name } }), "Папка создана.");
    } else if (dialog.kind === "file") {
      // файл без объекта: любое имя и любое расширение, объект не создаётся
      busy = true;
      api.POST("/studio/api/volumes/{volume_id}/text-files", { params: { path }, body: { parent: folder, name: dialog.name, content: "" } }).then(({ data, error }) => {
        busy = false;
        if (error) return toast(problem(error), "error");
        dialog = null;
        if (data) go(`/volumes/${id}/text/${data.id}`);
      });
    } else if (dialog.kind === "object") {
      const { name, format } = dialog;
      busy = true;
      api.POST("/studio/api/volumes/{volume_id}/files", { params: { path }, body: { parent: folder, name, format } }).then(({ data, error }) => {
        busy = false;
        if (error) return toast(problem(error), "error");
        dialog = null;
        if (data?.item) go(`/items/${data.item}`);
      });
    } else if (dialog.kind === "rename" && single) {
      run(() => api.PATCH("/studio/api/volumes/{volume_id}/placements/{placement_id}", {
        params: { path: { ...path, placement_id: single.id } }, body: { name: dialog!.name },
      }), "Переименовано.");
    } else if (dialog.kind === "rights") {
      const body: Partial<Record<RightsKey, string>> = {};
      for (const key of touched) body[key] = rights[key];
      const ids = [...selected];
      if (!Object.keys(body).length) { dialog = null; return; }
      run(async () => {
        for (const placement_id of ids) {
          const answer = await api.PATCH("/studio/api/volumes/{volume_id}/placements/{placement_id}", { params: { path: { volume_id: id, placement_id } }, body });
          if (answer.error) return answer;
        }
        return {};
      }, "Права сохранены.");
    } else if (dialog.kind === "delete") {
      busy = true;
      api.POST("/studio/api/volumes/{volume_id}/delete", { params: { path }, body: { ids: [...selected] } }).then(async ({ data, error }) => {
        busy = false;
        if (error || !data) return toast(problem(error), "error");
        dialog = null;
        selected = new Set();
        await load();
        toast(`Удалено: ${data.count}.`, "ok", data.undo ? { label: "Отменить", run: () => undo(data.undo) } : undefined);
      });
    }
  }

  // вернуть удалённое по снимку, который прислал сервер
  async function undo(snapshot: unknown) {
    const { error } = await api.POST("/studio/api/volumes/{volume_id}/restore", { params: { path: { volume_id: id } }, body: { undo: snapshot } });
    if (error) return toast(problem(error, "Не получилось вернуть."), "error");
    toast("Возвращено.");
    await load();
  }

  function setHidden(hidden: boolean) {
    const ids = [...selected];
    run(async () => {
      for (const placement_id of ids) {
        const answer = await api.PATCH("/studio/api/volumes/{volume_id}/placements/{placement_id}", {
          params: { path: { volume_id: id, placement_id } }, body: { hidden },
        });
        if (answer.error) return answer;
      }
      return {};
    }, hidden ? "Скрыто." : "Видно.");
  }

  // перетаскивание: тянуть можно строку таблицы и узел дерева; принимают папки, узлы дерева и звенья пути
  function startDrag(node: Node, event: DragEvent) {
    dragging = selected.has(node.id) ? [...selected] : [node.id];
    event.dataTransfer?.setData("text/plain", dragging.join(","));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "copyMove";
    const ghost = document.createElement("div");
    ghost.textContent = dragging.length > 1 ? `Перенести: ${dragging.length}` : `Перенести «${node.name}»`;
    Object.assign(ghost.style, { position: "fixed", top: "-100px", padding: "4px 10px", background: "#22262e", color: "#e6e8ec", border: "1px solid #7aa2ff", borderRadius: "6px", font: "13px sans-serif" });
    document.body.append(ghost);
    event.dataTransfer?.setDragImage(ghost, 12, 12);
    setTimeout(() => ghost.remove(), 0);
  }

  function endDrag() {
    dragging = [];
    dropTarget = undefined;
  }

  function canDrop(target: number | null) {
    return dragging.length > 0 && !dragging.includes(target as number);
  }

  function over(target: number | null, event: DragEvent) {
    if (!canDrop(target)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = event.altKey ? "copy" : "move";
    dropTarget = target;
  }

  function leave(event: DragEvent) {
    if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as globalThis.Node | null)) dropTarget = undefined;
  }

  function drop(target: number | null, event: DragEvent) {
    event.preventDefault();
    const ids = dragging;
    endDrag();
    if (!ids.length || ids.includes(target as number)) return;
    const copy = event.altKey;
    run(
      () => api.POST(copy ? "/studio/api/volumes/{volume_id}/copy" : "/studio/api/volumes/{volume_id}/move", {
        params: { path: { volume_id: id } }, body: { ids, parent: target },
      }),
      copy ? "Скопировано." : "Перенесено.",
    );
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape" && searching && (event.target as HTMLElement).closest("input.search")) { clearSearch(); return; }
    if (dialog || (event.target as HTMLElement).closest("input, textarea, select")) return;
    if (event.key === "Delete" && selected.size) dialog = { kind: "delete", name: "", format: "" };
    else if (event.key === "F2" && single) dialog = { kind: "rename", name: single.name, format: "" };
    else if (event.key === "Enter" && single && !(event.target as HTMLElement).closest(".tree")) activate(single);
    else if ((event.ctrlKey || event.metaKey) && event.key === "a") {
      event.preventDefault();
      selected = new Set(listing.map((row) => row.id));
    }
  }

  // дерево с клавиатуры: ↑↓ между папками, → раскрыть, ← свернуть или перейти к родителю, Enter открыть папку
  function treeKey(event: KeyboardEvent) {
    const here = (event.target as HTMLElement).closest<HTMLElement>(".twig-name");
    if (!here) return;
    const names = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>(".twig-name")];
    const at = names.indexOf(here);
    const nodeId = Number(here.closest<HTMLElement>(".twig")?.dataset.id ?? NaN);
    const node = Number.isNaN(nodeId) ? undefined : byId.get(nodeId);
    if (event.key === "ArrowDown") names[at + 1]?.focus();
    else if (event.key === "ArrowUp") names[at - 1]?.focus();
    else if (event.key === "ArrowRight" && node && !opened.has(node.id) && (children.get(node.id) ?? []).some((row) => row.kind === "folder")) toggle(node);
    else if (event.key === "ArrowLeft" && node) {
      if (opened.has(node.id)) toggle(node);
      else (node.parent === null ? names[0] : (event.currentTarget as HTMLElement).querySelector<HTMLElement>(`.twig[data-id="${node.parent}"] .twig-name`))?.focus();
    } else return;
    event.preventDefault();
  }

  // «Дублировать»: копия рядом с оригиналом (имя подбирается само)
  function duplicate() {
    const ids = [...selected];
    run(async () => {
      for (const key of ids) {
        const answer = await api.POST("/studio/api/volumes/{volume_id}/copy", {
          params: { path: { volume_id: id } }, body: { ids: [key], parent: byId.get(key)?.parent ?? null },
        });
        if (answer.error) return answer;
      }
      return {};
    }, "Продублировано.");
  }

  function openMenu(node: Node, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!selected.has(node.id)) selected = new Set([node.id]);
    const hide = !selectedNodes.every((row) => row.hidden);
    // у объектов (и папок с ними) копия остаётся тем же объектом, а не новым: так и подписано
    const shares = selectedNodes.some((row) => row.item || row.kind === "folder");
    const dup: MenuItem = { label: shares ? "Дублировать (объекты те же)" : "Дублировать", run: duplicate };
    const remove: MenuItem = { label: "Удалить", danger: true, run: () => (dialog = { kind: "delete", name: "", format: "" }) };
    const items: MenuItem[] = selected.size > 1
      ? [dup, { label: hide ? "Скрыть" : "Показать", run: () => setHidden(hide) }, "sep", remove]
      : [
          { label: "Открыть", run: () => activate(node) },
          { label: "Переименовать", run: () => (dialog = { kind: "rename", name: node.name, format: "" }) },
          dup,
          "sep",
          { label: node.hidden ? "Показать" : "Скрыть", run: () => setHidden(!node.hidden) },
          ...(node.item ? [{ label: "Защита места…", run: () => (protect = node) } satisfies MenuItem] : []),
          ...(node.own ? [{ label: "Сделать объектом…", run: () => go(`/volumes/${id}/text/${node.id}`) } satisfies MenuItem] : []),
          "sep",
          remove,
        ];
    menu = { x: event.clientX, y: event.clientY, items };
  }

  const createItems = (): MenuItem[] => [
    { label: "Новая папка", run: () => (dialog = { kind: "folder", name: "", format: "" }) },
    { label: "Пустой файл", hint: "без объекта: лежит только здесь", run: () => (dialog = { kind: "file", name: "", format: "" }) },
    { label: "Новый объект…", hint: "общий: с форматом, историей, несколькими местами", run: () => (dialog = { kind: "object", name: "", format: "" }) },
    { label: "Положить объект…", hint: "уже существующий, из библиотеки", run: () => (putting = true) },
  ];

  // кнопка «Создать»: второй клик закрывает меню
  function openCreate(event: MouseEvent) {
    if (menu) { menu = null; return; }
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    menu = { x: box.left, y: box.bottom + 4, items: createItems() };
  }

  // правый клик по пустому месту таблицы: то же самое меню
  function emptyMenu(event: MouseEvent) {
    if ((event.target as HTMLElement).closest(".row")) return;
    event.preventDefault();
    selected = new Set();
    menu = { x: event.clientX, y: event.clientY, items: createItems() };
  }

  // место объекта для окна «Защита места» (нужны только номер, том и путь)
  const placedOf = (node: Node) => ({
    placement: node.id, volume: id, parent: node.parent, volume_name: volume?.name || volume?.slug || "", volume_slug: volume?.slug ?? "",
    path: (paths.get(node.id) ?? "").replace(/^\//, ""), owner: node.owner, group: node.group, mode: node.mode, hidden: node.hidden,
    own_access: node.access !== "inherit", own_state: node.state !== "inherit",
  }) as Schemas["Placed"];

  function size(node: Node) {
    const bytes = node.size;
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  }
</script>

<svelte:window onkeydown={onKey} />

{#snippet branch(parent: number | null, depth: number)}
  {#each (children.get(parent) ?? []).filter((row) => row.kind === "folder") as node (node.id)}
    {@const kids = (children.get(node.id) ?? []).some((row) => row.kind === "folder")}
    <div
      class="twig"
      class:on={folder === node.id}
      class:drop={dropTarget === node.id}
      style:padding-left="{10 + depth * 14}px"
      data-id={node.id}
      role="treeitem"
      aria-selected={folder === node.id}
      aria-expanded={kids ? opened.has(node.id) : undefined}
      tabindex="-1"
      draggable="true"
      ondragstart={(event) => startDrag(node, event)}
      ondragend={endDrag}
      ondragover={(event) => over(node.id, event)}
      ondragleave={leave}
      ondrop={(event) => drop(node.id, event)}
    >
      <button class="arrow" class:open={opened.has(node.id)} class:none={!kids} onclick={() => toggle(node)} aria-label="Раскрыть" tabindex="-1">▸</button>
      <button class="twig-name" class:hidden={node.hidden} onclick={() => openFolder(node.id)}><FileIcon kind="folder" size={14} /> <span class="tname">{node.name}</span></button>
      {#if count(node.id)}<span class="count" title="Элементов внутри">{count(node.id)}</span>{/if}
    </div>
    {#if opened.has(node.id)}{@render branch(node.id, depth + 1)}{/if}
  {/each}
{/snippet}

<div class="volume">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="tree" role="tree" tabindex="-1" onkeydown={treeKey}>
    <button class="back" onclick={() => go("/volumes")}>← Все тома</button>
    <div
      class="twig root"
      class:on={folder === null}
      class:drop={dropTarget === null}
      role="treeitem"
      aria-selected={folder === null}
      tabindex="-1"
      ondragover={(event) => over(null, event)}
      ondragleave={leave}
      ondrop={(event) => drop(null, event)}
    >
      <button class="twig-name" onclick={() => openFolder(null)}><FileIcon kind="folder" size={14} /> <span class="tname">{volume?.name || volume?.slug || "…"}</span></button>
      {#if count(null)}<span class="count" title="Элементов в корне">{count(null)}</span>{/if}
    </div>
    {@render branch(null, 0)}
  </div>

  <section class="body">
    <header class="bar">
      <nav class="crumbs">
        <button class:drop={dropTarget === null} onclick={() => openFolder(null)} ondragover={(event) => over(null, event)} ondragleave={leave} ondrop={(event) => drop(null, event)}>{volume?.name || volume?.slug || "…"}</button>
        {#each crumbs as node (node.id)}
          <span class="sep">/</span><button class:drop={dropTarget === node.id} onclick={() => openFolder(node.id)} ondragover={(event) => over(node.id, event)} ondragleave={leave} ondrop={(event) => drop(node.id, event)}>{node.name}</button>
        {/each}
      </nav>
      <div class="actions">
        <button class="btn ghost" onclick={openProps}>Свойства</button>
      </div>
    </header>

    <div class="toolbar">
      <button class="btn primary" aria-haspopup="menu" onmousedown={(event) => event.stopPropagation()} onclick={openCreate} title="Папка, файл, объект">Создать ▾</button>
      <span class="vsep"></span>
      <button class="btn ghost" disabled={!single} onclick={() => single && activate(single)}>Открыть</button>
      <button class="btn ghost" disabled={!single} onclick={() => single && (dialog = { kind: "rename", name: single.name, format: "" })}>Переименовать</button>
      <button class="btn ghost" disabled={!selected.size} onclick={() => setHidden(!allHidden)} title="Скрытый файл игрок не видит в списке">{allHidden ? "Показать" : "Скрыть"}</button>
      <button class="btn ghost" disabled={!selected.size} onclick={openRights} title="Владелец, группа и права доступа игровых учёток">Права…</button>
      <button class="btn ghost danger" disabled={!selected.size} onclick={() => (dialog = { kind: "delete", name: "", format: "" })}>Удалить</button>
    </div>

    <div class="filters">
      {#each FILTERS as [key, label]}
        <button class="pick" class:on={active.has(key)} onclick={() => toggleFilter(key)}>{label}</button>
      {/each}
      {#if searching}
        <span class="muted small">Найдено: {listing.length}</span>
        <button class="link" onclick={clearSearch}>Сбросить</button>
      {/if}
      <span class="grow"></span>
      <input class="field search" placeholder="Поиск в томе" aria-label="Поиск в томе" bind:value={query} />
      <button class="btn ghost small" class:on={showDetails} onclick={toggleDetails} title="Панель сведений справа">Сведения</button>
      <Hint align="right">
        Перетащите файл или папку на папку (в таблице, в дереве или в пути сверху), чтобы перенести. С клавишей Alt: скопировать.<br />
        Клавиши: Enter открыть, F2 переименовать, Delete удалить, Ctrl+A выбрать всё, Shift или Ctrl+клик выбрать несколько. В дереве: стрелки.
      </Hint>
    </div>

    <div class="content">
    <div class="table" role="grid" tabindex="-1" oncontextmenu={emptyMenu}>
      <div class="row head" role="row">
        <span><button class="sort" onclick={() => sortBy("name")}>Имя{arrow("name")}</button></span>
        <span><button class="sort" onclick={() => sortBy("type")}>Тип{arrow("type")}</button></span>
        <span>Защита<Hint text="«слои» — файл надо расшифровать, снять маскировку и т. п. «условие» — нужны определённые ключи. Видно и у объектов, и у файлов без объекта." /></span>
        <span class="num"><button class="sort" onclick={() => sortBy("size")}>Размер{arrow("size")}</button></span>
      </div>
      {#each listing as node (node.id)}
        {@const kind = describe(node, formats, count(node.id))}
        <div
          class="row"
          class:sel={selected.has(node.id)}
          class:drop={node.kind === "folder" && dropTarget === node.id}
          class:dim={node.hidden}
          role="row"
          tabindex="-1"
          draggable="true"
          onclick={(event) => pick(node, event)}
          ondblclick={() => activate(node)}
          oncontextmenu={(event) => openMenu(node, event)}
          onkeydown={() => {}}
          ondragstart={(event) => startDrag(node, event)}
          ondragend={endDrag}
          ondragover={(event) => node.kind === "folder" && over(node.id, event)}
          ondragleave={leave}
          ondrop={(event) => node.kind === "folder" && drop(node.id, event)}
        >
          <span class="name">
            <FileIcon kind={kind.kind} own={kind.own} />
            <span class="text">{node.name}</span>
            {#if searching}<span class="where muted small" title="Где лежит">{dirOf(node)}</span>{/if}
            {#if node.item && node.item.used > 1}<span class="chip" title="Тот же объект лежит в других местах: {node.item.used}">×{node.item.used}</span>{/if}
            {#if node.hidden}<span class="chip" title="Игрок не видит этот файл в списке">скрыт</span>{/if}
            {#if node.system}<span class="chip" title="Игрок не может удалить">системный</span>{/if}
          </span>
          <span class="muted type" class:obj={!kind.own && node.kind !== "folder"}>{kind.label}</span>
          <span class="guard">
            {#if node.layers}<span class="chip warnchip" title="У файла есть слои защиты">слои</span>{/if}
            {#if node.condition}<span class="chip warnchip" title="Файл открывается только при условии по ключам">условие</span>{/if}
          </span>
          <span class="muted mono num">{size(node)}</span>
        </div>
      {:else}
        <div class="empty muted">
          {#if searching}
            <p>Ничего не нашлось.</p>
            <p class="small">Поиск идёт по всему тому: по имени и по пути. <button class="link" onclick={clearSearch}>Сбросить поиск</button></p>
          {:else}
            <p>Папка пуста.</p>
            <p class="small">Создайте файл или папку кнопками сверху или перетащите сюда что-нибудь из дерева.</p>
          {/if}
        </div>
      {/each}
    </div>
    {#if showDetails}
      <Details
        nodes={selectedNodes} folderNodes={listing} folderPath={searching ? "Результаты поиска" : folder === null ? "/" : paths.get(folder) ?? "/"}
        kind={(node) => describe(node, formats, count(node.id))} pathOf={(node) => paths.get(node.id) ?? ""}
        onopen={activate} onrename={(node) => { selected = new Set([node.id]); dialog = { kind: "rename", name: node.name, format: "" }; }} onprotect={(node) => (protect = node)}
      />
    {/if}
    </div>
  </section>
</div>

{#if menu}
  <ContextMenu x={menu.x} y={menu.y} items={menu.items} onclose={() => (menu = null)} />
{/if}

{#if protect?.item}
  <PlacementProtection itemId={protect.item.id} placed={placedOf(protect)} onclose={() => (protect = null)} onsaved={load} />
{/if}

{#if putting}
  <PutObject volume={id} {folder} folderName={folder === null ? volume?.name || volume?.slug || "корень" : byId.get(folder)?.name ?? ""} onclose={() => (putting = false)} ondone={load} />
{/if}

{#if propsOpen}
  <Dialog title="Свойства тома" confirm="Сохранить" onsubmit={saveProps} onclose={() => (propsOpen = false)}>
    <label><span class="label">Название диска (как в игре)</span><input class="field" bind:value={props_.name} /></label>
    <label><span class="label">Слаг</span><input class="field mono" bind:value={props_.slug} class:bad={propErrors.slug} /></label>
    {#if propErrors.slug}<p class="err">{propErrors.slug.join(" ")}</p>{/if}
    <label><span class="label">Метка для студии</span><input class="field" bind:value={props_.label} /></label>
    <div class="two">
      <label><span class="label">Ёмкость, ГБ (декор)</span><input class="field" type="number" min="0" value={props_.capacity_gb ?? ""} oninput={(e) => (props_.capacity_gb = gbOf(e.currentTarget.value))} /></label>
      <label><span class="label">Занято, ГБ</span>
        <span class="inline"><input class="field" type="number" min="0" value={props_.used_gb ?? ""} oninput={(e) => (props_.used_gb = gbOf(e.currentTarget.value))} />
          <button type="button" class="btn ghost" disabled={!props_.capacity_gb} onclick={randomUsed}>Случайно</button></span>
      </label>
    </div>
    {#if propErrors.used_gb}<p class="err">{propErrors.used_gb.join(" ")}</p>{/if}
    <label><span class="label">UUID</span><input class="field mono" bind:value={props_.uuid} class:bad={propErrors.uuid} /></label>
    {#if propErrors.uuid}<p class="err">{propErrors.uuid.join(" ")}</p>{/if}
  </Dialog>
{/if}

{#if dialog?.kind === "folder"}
  <Dialog title="Новая папка" confirm="Создать" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <input class="field" placeholder="Имя папки" bind:value={dialog.name} />
  </Dialog>
{:else if dialog?.kind === "file"}
  <Dialog title="Пустой файл" confirm="Создать и открыть" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <label><span class="label">Имя файла</span><input class="field" placeholder="notes.txt" bind:value={dialog.name} /></label>
    <p class="muted small">{typeHint(dialog.name, formats)}</p>
    <p class="muted small">Файл лежит только в этом месте и не создаёт объект. Нужна общая запись, история или несколько мест? Создайте объект через «Создать → Новый объект…».</p>
  </Dialog>
{:else if dialog?.kind === "object"}
  <Dialog title="Новый объект" confirm="Создать и открыть" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <label><span class="label">Название (расширение подберёт формат)</span><input class="field" placeholder="report.rec" bind:value={dialog.name} /></label>
    <label>
      <span class="label">Формат</span>
      <select class="field" bind:value={dialog.format}>
        <option value="">по расширению</option>
        <FormatOptions {formats} />
      </select>
    </label>
    <p class="muted small">Объект общий: его можно положить в несколько мест, у него есть история и защита объекта. Для обычного файла, который нужен только здесь, используйте «Пустой файл».</p>
  </Dialog>
{:else if dialog?.kind === "rename"}
  <Dialog title="Переименовать" confirm="Сохранить" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <input class="field" bind:value={dialog.name} />
  </Dialog>
{:else if dialog?.kind === "rights"}
  <Dialog title="Права: {selected.size === 1 ? `«${single?.name}»` : `${selected.size} элементов`}" confirm="Сохранить" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <p class="muted small">Права нужны игровым учёткам: кто может читать, менять и запускать файл на машине. Пусто: права не заданы, файл открыт всем.</p>
    <div class="two">
      <label>
        <span class="label">Владелец<Hint text="Логин учётки на машине, например ivan." /></span>
        <input class="field mono" placeholder={mixed("owner") ? "разные" : "не задан"} value={rights.owner} oninput={(event) => setRight("owner", event.currentTarget.value)} />
      </label>
      <label>
        <span class="label">Группа<Hint text="Группа учётки, например users." /></span>
        <input class="field mono" placeholder={mixed("group") ? "разные" : "не задана"} value={rights.group} oninput={(event) => setRight("group", event.currentTarget.value)} />
      </label>
    </div>
    <label>
      <span class="label">Права<Hint text="Три цифры: владелец, группа, остальные. Чтение 4, запись 2, запуск или вход в папку 1, цифры складываются: 6 — чтение и запись, 5 — чтение и запуск." /></span>
      <input class="field mono" maxlength="3" placeholder={mixed("mode") ? "разные" : "не заданы"} value={rights.mode} oninput={(event) => setRight("mode", event.currentTarget.value)} />
    </label>
    <div class="presets">
      {#each PRESETS as [value, label]}
        <button type="button" class="pick" class:on={touched.has("mode") && rights.mode === value} onclick={() => setRight("mode", value)}><b class="mono">{value || "—"}</b> {label}</button>
      {/each}
    </div>
    <p class="muted small">{decode(rights.mode)}</p>
  </Dialog>
{:else if dialog?.kind === "delete"}
  <Dialog title="Удалить {selected.size === 1 ? `«${single?.name}»` : `${selected.size} элементов`}?" confirm="Удалить" danger {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <p class="muted">Папки удаляются вместе с содержимым. Объекты, которые лежат и в других местах, там останутся. После удаления будет 10 секунд, чтобы нажать «Отменить».</p>
  </Dialog>
{/if}

<style>
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .inline { display: flex; gap: 6px; }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .field.bad { border-color: var(--danger); }
  .small { font-size: 12px; margin: 0; }
  .volume { display: grid; grid-template-columns: 260px 1fr; height: 100%; }
  .tree { padding: 12px 8px; border-right: 1px solid var(--line-soft); overflow: auto; background: var(--panel); }
  .back { margin: 0 0 10px 6px; background: none; border: 0; color: var(--muted); cursor: pointer; padding: 4px; }
  .back:hover { color: var(--text); }
  .twig { display: flex; align-items: center; gap: 2px; border-radius: var(--radius-s); }
  .twig.root { padding-left: 6px; font-weight: 600; }
  .twig:hover { background: var(--panel-2); }
  .twig.on { background: var(--accent-soft); }
  .twig.drop, .row.drop { outline: 1px dashed var(--accent); background: var(--accent-soft); }
  .arrow { width: 18px; border: 0; background: none; color: var(--faint); cursor: pointer; transition: transform 0.12s; padding: 0; }
  .arrow.open { transform: rotate(90deg); }
  .arrow.none { visibility: hidden; }
  .twig-name { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; text-align: left; border: 0; background: none; padding: 5px 6px; cursor: pointer; }
  .tname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .twig-name.hidden { color: var(--muted); font-style: italic; }
  .count { margin: 0 6px 0 4px; color: var(--faint); font-size: 11.5px; font-variant-numeric: tabular-nums; }
  .body { display: flex; flex-direction: column; min-width: 0; }
  .bar { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 18px 24px 10px; }
  .crumbs { display: flex; align-items: center; gap: 4px; font-size: 15px; min-width: 0; flex-wrap: wrap; }
  .crumbs button { border: 0; background: none; cursor: pointer; padding: 2px 4px; border-radius: 4px; font-weight: 600; }
  .crumbs button:hover { background: var(--panel-2); }
  .crumbs button.drop { outline: 1px dashed var(--accent); background: var(--accent-soft); }
  .sep { color: var(--faint); }
  .actions { display: flex; gap: 8px; }
  .toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 0 24px 10px; padding: 6px 8px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .vsep { width: 1px; align-self: stretch; margin: 2px 6px; background: var(--line); }
  .grow { flex: 1; }
  .presets { display: flex; flex-wrap: wrap; gap: 6px; }
  .search { width: 190px; height: 28px; }
  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 24px 8px; }
  .pick { padding: 2px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--muted); cursor: pointer; }
  .pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .link { padding: 0; border: 0; background: none; color: var(--accent); cursor: pointer; }
  .where { margin-left: 6px; white-space: nowrap; }
  .btn.on { background: var(--accent-soft); color: var(--accent); }
  .body { min-height: 0; }
  .content { display: flex; flex: 1; min-height: 0; min-width: 0; }
  .table { flex: 1; min-width: 0; padding: 0 24px 24px; overflow: auto; }
  .row {
    display: grid; grid-template-columns: minmax(240px, 1fr) 200px 130px 90px; align-items: center; gap: 12px;
    padding: 0 10px; height: 36px; border-radius: var(--radius-s); cursor: default; user-select: none;
  }
  .row:not(.head):hover { background: var(--panel); }
  .row.sel { background: var(--accent-soft); }
  .row.dim .name { color: var(--muted); font-style: italic; }
  .row.head { color: var(--faint); font-size: 12px; height: 28px; border-bottom: 1px solid var(--line-soft); border-radius: 0; margin-bottom: 4px; }
  .sort { padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
  .sort:hover { color: var(--text); }
  .num { text-align: right; }
  .name { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .text { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .type { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .type.obj { color: var(--accent); }
  .guard { display: flex; gap: 4px; }
  .chip.warnchip { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  .empty { padding: 28px 10px; }
  .empty p { margin: 0 0 4px; }
</style>
