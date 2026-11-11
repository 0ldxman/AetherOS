<script lang="ts">
  // Узел карты: шаг переписки. Вход слева (на шаг ведут переходы), справа выходы вариантов: тянешь выход на шаг, получаешь переход.
  import { Handle, Position, useUpdateNodeInternals } from "@xyflow/svelte";
  import { socketLabel, socketsOf, type StepDraft } from "./doc";

  let { id, data, selected }: { id: string; data: { step: StepDraft; errors: number; warnings: number; start: boolean }; selected?: boolean } = $props();

  const step = $derived(data.step);
  const rows = $derived(step.variants.map((variant, index) => ({ variant, index, sockets: socketsOf(variant) })));
  const shape = $derived(rows.map((r) => r.sockets.join(",")).join(";"));
  const update = useUpdateNodeInternals();
  $effect(() => {
    shape;
    queueMicrotask(() => update(id));
  });
  const used = (variant: StepDraft["variants"][number], socket: string) => !!variant.outcomes?.[socket]?.length;
</script>

<div class="node" class:selected class:start={data.start}>
  <Handle type="target" position={Position.Left} class="in" />
  <header>
    <b class="name">{step.name || "без имени"}</b>
    {#if step.opening}<span class="tag" title="Игрок пишет первым: варианты этого шага видны в новом письме">начало</span>
    {:else if data.start}<span class="tag" title="С этого шага сценарий начинается по хуку mail">первый</span>{/if}
    <span class="spacer"></span>
    {#if data.errors}<span class="n-err" title="Ошибок: {data.errors}">{data.errors}</span>{/if}
    {#if data.warnings}<span class="n-warn" title="Предупреждений: {data.warnings}">{data.warnings}</span>{/if}
  </header>
  {#if step.letter?.subject || step.letter?.text}
    <div class="letter" title="Письмо персонажа на этом шаге">✉ {step.letter.subject || "(без темы)"}{#if step.letter_delay}<span class="muted"> · {step.letter_delay} с</span>{/if}</div>
  {/if}
  {#each rows as row (row.variant.key)}
    <div class="variant">
      <div class="title">
        {#if row.variant.mode === "forward"}<span class="muted" title="Пересылка письма">↪</span>{/if}
        {#if row.variant.condition || row.variant.need_flags.length || row.variant.deny_flags.length || row.variant.account}<span class="lock" title="Вариант открывается по условию">усл.</span>{/if}
        {row.variant.title || "…"}
      </div>
      {#each row.sockets as socket (socket)}
        <div class="socket" class:used={used(row.variant, socket)} class:bad={socket === "wrong" || socket === "exhausted"}>
          <span>{socketLabel(socket)}</span>
          <Handle type="source" position={Position.Right} id={`${row.index}|${socket}`} class="out" />
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty muted">нет вариантов ответа</div>
  {/each}
</div>

<style>
  .node { width: 240px; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--radius); font-size: 12.5px; color: var(--text); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); }
  .node.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 4px 14px rgba(0, 0, 0, 0.35); }
  header { display: flex; align-items: center; gap: 6px; padding: 7px 10px; border-bottom: 1px solid var(--line); background: var(--raise); border-radius: var(--radius) var(--radius) 0 0; }
  .start header { background: color-mix(in srgb, var(--accent) 22%, var(--raise)); }
  .name { font-family: var(--mono); font-size: 12.5px; }
  .tag { font-size: 10.5px; padding: 0 6px; border-radius: 999px; border: 1px solid var(--accent); color: var(--accent); }
  .spacer { flex: 1; }
  .n-err, .n-warn { min-width: 16px; padding: 0 5px; border-radius: 999px; text-align: center; font-size: 10.5px; font-weight: 600; color: #111; }
  .n-err { background: var(--danger); }
  .n-warn { background: var(--warn); }
  .letter { padding: 6px 10px; color: var(--muted); border-bottom: 1px solid var(--line-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .variant { padding: 6px 0 4px; border-bottom: 1px solid var(--line-soft); }
  .variant:last-child { border-bottom: 0; }
  .title { padding: 0 10px 2px; font-weight: 500; overflow-wrap: anywhere; }
  .lock { color: var(--warn); font-size: 10.5px; font-weight: 400; border: 1px solid currentColor; border-radius: 4px; padding: 0 3px; margin-right: 2px; }
  .socket { position: relative; display: flex; justify-content: flex-end; padding: 1px 14px 1px 10px; color: var(--faint); font-size: 11.5px; }
  .socket.used { color: var(--text); }
  .socket.bad.used { color: var(--danger); }
  .empty { padding: 8px 10px; font-size: 12px; }
  .muted { color: var(--muted); }
  .node :global(.svelte-flow__handle) { width: 9px; height: 9px; background: var(--panel-2); border: 2px solid var(--muted); }
  .node :global(.svelte-flow__handle.in) { top: 17px; border-color: var(--accent); }
  .socket.used :global(.svelte-flow__handle) { background: var(--accent); border-color: var(--accent); }
  .socket.bad.used :global(.svelte-flow__handle) { background: var(--danger); border-color: var(--danger); }
</style>
