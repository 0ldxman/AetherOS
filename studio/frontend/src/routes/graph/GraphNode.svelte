<script lang="ts">
  // Нода сценария, раскладка как в Blender: сверху выходы (справа), под ними входы (слева), каждая строка подписана.
  // Цвет точки — тип: белая — событие («случилось», по нему идёт ход), цветные ◆ — вещи (файл, персонаж, метка…).
  import { Handle, Position, useUpdateNodeInternals } from "@xyflow/svelte";
  import { COLORS, TYPES, insOf, outsOf, refOf, typeColor, type GNode, type Iface, type Kind } from "./kinds";

  type Stat = { hits: number; players: number; waiting: number; oldest_days: number };
  type RefField = { name: string; label: string; type: string; value: string };
  let { id, data, selected }: {
    id: string;
    data: { node: GNode; kind: Kind; waiting: boolean; summary: string; errors: number; warnings: number; stat: Stat | null; refFields: RefField[]; used: string[];
            usedIn: string[]; iface: Iface | null; box: number; help: Record<string, string>; fedFrom: Record<string, string> };
    selected?: boolean;
  } = $props();

  const kind = $derived(data.kind);
  const hide = $derived(!!data.node.collapsed);
  const isNoun = $derived(kind.group === "noun");
  const allIns = $derived(insOf(kind, data.node.data, data.iface));
  const flowIn = $derived(allIns.some((s) => s.name === "in") && !(isNoun && kind.start_only));
  const ins = $derived(allIns.filter((s) => s.name !== "in" && (!hide || data.usedIn.includes(s.name))));
  const outs = $derived(outsOf(kind, data.node.data, data.waiting, data.iface).filter((s) => !hide || data.used.includes(s.name)));
  const ref = $derived(hide && !data.used.includes("ref") ? null : refOf(kind));
  const refFields = $derived(data.refFields.filter((f) => !hide || data.usedIn.includes(`f:${f.name}`)));
  const flowLabel = $derived(isNoun ? "Ждать с" : kind.name === "group_out" ? "" : "Запуск");
  const shape = $derived([ins.map((s) => s.name), outs.map((s) => s.name), refFields.map((f) => f.name), data.waiting, hide, flowIn].join("|"));
  const update = useUpdateNodeInternals();
  $effect(() => {
    shape;
    queueMicrotask(() => update(id));
  });
  const role = $derived(data.waiting ? { text: "ждёт", tip: "Есть входящий провод: прохождение ждёт событие здесь" }
                        : data.used.some((o) => o !== "ref") || !data.used.includes("ref") ? { text: "старт", tip: "Нет входящего провода: событие запускает прохождение" }
                        : { text: "ссылка", tip: "Подключён только ◆: нода даёт вещь в поле действия и ничего не ловит" });
  const days = (value: number) => (value < 1 ? "<1 дн." : `${Math.floor(value)} дн.`);
  const refType = $derived(kind.ref || "");
  // подсказка как в Blender: название, тип и смысл, значение или откуда подключено (строки через \n; показывает холст)
  const tip = (title: string, type: string, text: string, extra = "") => [title, [type, text].filter(Boolean).join(" · "), extra].filter(Boolean).join("\n");
  const outTip = (name: string, label: string) => tip(label || name, "Событие", data.help[name] ?? (name.match(/^[a-z]\d+$/) ? "ветка" : ""));
  const inTip = (name: string, label: string) => tip(label || "Запуск", "Событие", data.help[name] ?? "", data.fedFrom[name] ? `подключено: ${data.fedFrom[name]}` : "не подключено");
</script>

<div class="node" class:selected class:muted-node={data.node.mute} class:box={kind.name === "group" || kind.name === "scenario"} style="--head: {COLORS[kind.group] ?? '#555'}">
  <header data-tip={tip(kind.label, "", kind.help)}>
    <b>{kind.label}</b>
    {#if isNoun}<span class="tag" title={role.tip}>{role.text}</span>{/if}
    {#if kind.name === "group"}<span class="tag" title="Tab — войти в группу">Tab</span>{/if}
    {#if hide}<span class="tag" title="Неподключённые сокеты скрыты (Ctrl+H)">…</span>{/if}
    <span class="spacer"></span>
    {#if data.errors}<span class="n err" title="Ошибок: {data.errors}">{data.errors}</span>{/if}
    {#if data.box}<span class="n err" title="Ошибок внутри: {data.box}">{data.box}</span>{/if}
    {#if data.warnings}<span class="n warn" title="Предупреждений: {data.warnings}">{data.warnings}</span>{/if}
  </header>
  {#if data.summary}<div class="summary" title={data.summary}>{data.summary}</div>{/if}

  {#each outs as sock (sock.name)}
    <div class="row out" class:used={data.used.includes(sock.name)} class:attempt={sock.name === "attempt"} data-tip={outTip(sock.name, sock.label)}>
      <span>{sock.label}</span>
      <Handle type="source" position={Position.Right} id={sock.name} class="sock event" style="--c: {TYPES.event.color}" />
    </div>
  {/each}
  {#if ref}
    <div class="row out" class:used={data.used.includes("ref")} data-tip={tip(ref.label, TYPES[refType]?.label ?? "", data.help.ref ?? "")}>
      <span>{ref.label}</span>
      <Handle type="source" position={Position.Right} id="ref" class="sock thing" style="--c: {typeColor(refType)}" />
    </div>
  {/if}

  {#if flowIn}
    <div class="row in" class:used={data.usedIn.includes("in")} data-tip={inTip("in", flowLabel)}>
      <Handle type="target" position={Position.Left} id="in" class="sock event" style="--c: {TYPES.event.color}" />
      <span>{flowLabel}</span>
    </div>
  {/if}
  {#each ins as sock (sock.name)}
    <div class="row in" class:used={data.usedIn.includes(sock.name)} data-tip={inTip(sock.name, sock.label)}>
      <Handle type="target" position={Position.Left} id={sock.name} class="sock event" style="--c: {TYPES.event.color}" />
      <span>{sock.label}</span>
    </div>
  {/each}
  {#each refFields as f (f.name)}
    {@const fed = data.usedIn.includes(`f:${f.name}`)}
    <div class="row in" class:used={fed} data-tip={tip(f.label, TYPES[f.type]?.label ?? "", "поле действия", fed ? `подключено: ${data.fedFrom[`f:${f.name}`] ?? ""}` : f.value ? `значение: ${f.value}` : "не заполнено")}>
      <Handle type="target" position={Position.Left} id={`f:${f.name}`} class="sock thing" style="--c: {typeColor(f.type)}" />
      <span>{f.label}</span>
      {#if !fed && f.value}<em class="value">{f.value}</em>{/if}
    </div>
  {/each}

  {#if data.stat && (data.stat.hits || data.stat.waiting)}
    <footer>
      {#if data.stat.hits}<span title="Сколько раз прошли через ноду / сколько разных игроков">прошли {data.stat.hits}{data.stat.players ? ` · игроков ${data.stat.players}` : ""}</span>{/if}
      {#if data.stat.waiting}<span class="wait" class:old={data.stat.oldest_days >= 3} title="Сколько прохождений стоит здесь и сколько ждёт самое старое">ждут {data.stat.waiting} · {days(data.stat.oldest_days)}</span>{/if}
    </footer>
  {/if}
</div>

<style>
  .node { width: 220px; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--radius); font-size: 12px; color: var(--text); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); }
  .node.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 4px 14px rgba(0, 0, 0, 0.35); }
  .node.muted-node { opacity: 0.45; }
  .node.box { border-width: 2px; border-style: double; }
  header { display: flex; align-items: center; gap: 6px; padding: 5px 10px; background: color-mix(in srgb, var(--head) 70%, var(--raise)); border-radius: var(--radius) var(--radius) 0 0; }
  header b { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tag { font-size: 10px; padding: 0 5px; border-radius: 999px; background: rgba(0, 0, 0, 0.25); color: var(--text); }
  .spacer { flex: 1; }
  .n { min-width: 16px; padding: 0 5px; border-radius: 999px; text-align: center; font-size: 10.5px; font-weight: 600; color: #111; }
  .n.err { background: var(--danger); }
  .n.warn { background: var(--warn); }
  .summary { padding: 4px 10px; color: var(--muted); font-family: var(--mono); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px solid var(--line-soft); }
  .row { position: relative; display: flex; align-items: center; gap: 6px; padding: 2px 12px; min-height: 20px; color: var(--faint); font-size: 11.5px; }
  .row.out { justify-content: flex-end; }
  .row.out + .row.in, .summary + .row.in { margin-top: 4px; }
  .row.used { color: var(--text); }
  .row.attempt span::before { content: "◇ "; }
  .value { margin-left: auto; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-style: normal; font-family: var(--mono); font-size: 10.5px; }
  footer { display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 4px 10px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 10.5px; }
  .wait { color: var(--accent); }
  .wait.old { color: var(--warn); }
  /* событие — круг, вещь — ромб; цвет — тип; заливка — подключено */
  .node :global(.svelte-flow__handle.sock) { width: 10px; height: 10px; background: var(--panel-2); border: 2px solid var(--c); }
  .node :global(.svelte-flow__handle.sock.thing) { width: 9px; height: 9px; border-radius: 1px; }
  .node :global(.svelte-flow__handle.sock.thing.svelte-flow__handle-left) { transform: translate(-50%, -50%) rotate(45deg); }
  .node :global(.svelte-flow__handle.sock.thing.svelte-flow__handle-right) { transform: translate(50%, -50%) rotate(45deg); }
  .row.used :global(.svelte-flow__handle.sock) { background: var(--c); }
</style>
