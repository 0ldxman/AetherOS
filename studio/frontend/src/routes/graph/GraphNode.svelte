<script lang="ts">
  // Нода сценария: шапка цвета группы, подпись, выходы справа, входы слева. ▶ — поток, ◆ — ссылка на вещь (в поле действия).
  import { Handle, Position, useUpdateNodeInternals } from "@xyflow/svelte";
  import { COLORS, insOf, outsOf, refOf, type GNode, type Iface, type Kind } from "./kinds";

  type Stat = { hits: number; players: number; waiting: number; oldest_days: number };
  let { id, data, selected }: {
    id: string;
    data: { node: GNode; kind: Kind; waiting: boolean; summary: string; errors: number; warnings: number; stat: Stat | null; refFields: { name: string; label: string }[]; used: string[];
            usedIn: string[]; iface: Iface | null; box: number };
    selected?: boolean;
  } = $props();

  const kind = $derived(data.kind);
  const hide = $derived(!!data.node.collapsed);
  const ins = $derived(insOf(kind, data.node.data, data.iface).filter((s) => !hide || s.name === "in" || data.usedIn.includes(s.name)));
  const outs = $derived(outsOf(kind, data.node.data, data.waiting, data.iface).filter((s) => !hide || data.used.includes(s.name)));
  const ref = $derived(hide && !data.used.includes("ref") ? null : refOf(kind));
  const refFields = $derived(data.refFields.filter((f) => !hide || data.usedIn.includes(`f:${f.name}`)));
  const isNoun = $derived(kind.group === "noun");
  const shape = $derived([ins.map((s) => s.name), outs.map((s) => s.name), refFields.map((f) => f.name), data.waiting, hide].join("|"));
  const update = useUpdateNodeInternals();
  $effect(() => {
    shape;
    queueMicrotask(() => update(id));
  });
  const role = $derived(data.waiting ? { text: "ждёт", tip: "Есть входящий провод: прохождение ждёт событие здесь" }
                        : data.used.some((o) => o !== "ref") || !data.used.includes("ref") ? { text: "старт", tip: "Нет входящего провода: событие запускает прохождение" }
                        : { text: "ссылка", tip: "Подключён только ◆: нода даёт вещь в поле действия и ничего не ловит" });
  const days = (value: number) => (value < 1 ? "<1 дн." : `${Math.floor(value)} дн.`);
</script>

<div class="node" class:selected class:muted-node={data.node.mute} class:box={kind.name === "group" || kind.name === "scenario"} style="--head: {COLORS[kind.group] ?? '#555'}">
  <header>
    {#if ins.length === 1 && ins[0].name === "in" && !(isNoun && kind.start_only)}
      <Handle type="target" position={Position.Left} id="in" class="flow" />
    {/if}
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
    <div class="row out" class:used={data.used.includes(sock.name)} class:bad={sock.name === "fail" || sock.name === "timeout" || sock.name === "late"} class:attempt={sock.name === "attempt"}>
      <span>{sock.label}</span>
      <Handle type="source" position={Position.Right} id={sock.name} class="flow" />
    </div>
  {/each}
  {#if ref}
    <div class="row out ref" class:used={data.used.includes("ref")}>
      <span>{ref.label}</span>
      <Handle type="source" position={Position.Right} id="ref" class="ref" />
    </div>
  {/if}
  {#each ins.filter((s) => s.name !== "in") as sock (sock.name)}
    <div class="row in">
      <Handle type="target" position={Position.Left} id={sock.name} class="flow" />
      <span>{sock.label}</span>
    </div>
  {/each}
  {#each refFields as f (f.name)}
    <div class="row in ref">
      <Handle type="target" position={Position.Left} id={`f:${f.name}`} class="ref" />
      <span>{f.label}</span>
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
  .node { width: 210px; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--radius); font-size: 12px; color: var(--text); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); }
  .node.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 4px 14px rgba(0, 0, 0, 0.35); }
  .node.muted-node { opacity: 0.45; }
  .node.box { border-width: 2px; border-style: double; }
  header { position: relative; display: flex; align-items: center; gap: 6px; padding: 5px 10px; background: color-mix(in srgb, var(--head) 70%, var(--raise));
           border-radius: var(--radius) var(--radius) 0 0; }
  header b { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tag { font-size: 10px; padding: 0 5px; border-radius: 999px; background: rgba(0, 0, 0, 0.25); color: var(--text); }
  .spacer { flex: 1; }
  .n { min-width: 16px; padding: 0 5px; border-radius: 999px; text-align: center; font-size: 10.5px; font-weight: 600; color: #111; }
  .n.err { background: var(--danger); }
  .n.warn { background: var(--warn); }
  .summary { padding: 4px 10px; color: var(--muted); font-family: var(--mono); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px solid var(--line-soft); }
  .row { position: relative; display: flex; padding: 2px 12px; color: var(--faint); font-size: 11.5px; }
  .row.out { justify-content: flex-end; }
  .row.used { color: var(--text); }
  .row.ref span::after { content: " ◆"; color: #c792ea; }
  .row.in.ref span::before { content: "◆ "; color: #c792ea; }
  .row.in.ref span::after { content: ""; }
  footer { display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 4px 10px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 10.5px; }
  .wait { color: var(--accent); }
  .wait.old { color: var(--warn); }
  .node :global(.svelte-flow__handle.flow) { width: 10px; height: 10px; background: var(--panel-2); border: 2px solid #d9dde4; }
  .node :global(.svelte-flow__handle.ref) { width: 9px; height: 9px; border-radius: 1px; transform: translate(0, -50%) rotate(45deg); background: var(--panel-2); border: 2px solid #c792ea; }
  .node :global(.svelte-flow__handle.ref.svelte-flow__handle-left) { transform: translate(-50%, -50%) rotate(45deg); }
  .node :global(.svelte-flow__handle.ref.svelte-flow__handle-right) { transform: translate(50%, -50%) rotate(45deg); }
  .row.used :global(.svelte-flow__handle.flow) { background: #d9dde4; }
  .row.bad.used :global(.svelte-flow__handle.flow) { background: var(--warn); border-color: var(--warn); }
  .row.used :global(.svelte-flow__handle.ref) { background: #c792ea; }
  .row.attempt { color: #e9a86a; }
  .row.attempt :global(.svelte-flow__handle.flow) { border-color: #e9a86a; border-radius: 2px; transform: translate(50%, -50%) rotate(45deg); }
  .row.attempt.used :global(.svelte-flow__handle.flow) { background: #e9a86a; }
</style>
