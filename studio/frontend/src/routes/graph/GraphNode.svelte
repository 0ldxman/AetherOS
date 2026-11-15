<script lang="ts">
  // Нода сценария, как в Blender: сверху выходы (справа), под ними входы (слева). Параметры ноды — тоже входы своего типа:
  // без провода значение правится прямо на ноде, с проводом приходит по нему. Выбор режима — параметр без входа.
  // Круг — событие и простые значения (да/нет, текст, число), ромб — вещь (файл, машина, персонаж…). Цвет — тип.
  import { Handle, Position, useUpdateNodeInternals } from "@xyflow/svelte";
  import { BOXES, COLORS, TYPES, inWhen, insOf, isThing, outsOf, propFields, rowsOf, socketFields, titleOf, typeColor, visibleRows, type Field, type GNode, type Iface, type Kind, type Row } from "./kinds";

  type Stat = { hits: number; players: number; waiting: number; oldest_days: number };
  type Option = { value: string; label: string };
  let { id, data, selected }: {
    id: string;
    data: { node: GNode; kind: Kind; waiting: boolean; summary: string; errors: number; warnings: number; stat: Stat | null; used: string[];
            usedIn: string[]; iface: Iface | null; box: number; help: Record<string, string>; fedFrom: Record<string, string>;
            picks: Record<string, Option[]>; editable: boolean; onfield: (name: string, value: unknown) => void };
    selected?: boolean;
  } = $props();

  const kind = $derived(data.kind);
  const values = $derived(data.node.data);
  const hide = $derived(!!data.node.collapsed);
  const isNoun = $derived(kind.group === "noun");
  const allIns = $derived(insOf(kind, values, data.iface));
  const flowIn = $derived(allIns.some((s) => s.name === "in") && !(isNoun && kind.start_only));
  const ins = $derived(allIns.filter((s) => s.name !== "in" && (!hide || data.usedIn.includes(s.name))));
  const outs = $derived(outsOf(kind, values, data.waiting, data.iface).filter((s) => !hide || data.used.includes(s.name)));
  // поля, которые есть в выбранном режиме (как в Blender: режим меняет набор входов); подключённые видны всегда
  const inMode = (f: Field) => {
    const mode = String(values.mode ?? "");
    if (kind.name === "wait") return ({ minutes: (mode || "delay") === "delay", at: mode === "until", condition: mode === "condition", timeout: mode === "condition" } as Record<string, boolean>)[f.name] ?? true;
    if (kind.name === "time" && f.name === "date") return mode === "once";
    if (kind.name === "do:player_count") return ({ delta: mode !== "set", value: mode === "set" } as Record<string, boolean>)[f.name] ?? true;
    if (kind.name === "do:file_change") return ({ item: (mode || "replace") === "replace", target: mode === "move" } as Record<string, boolean>)[f.name] ?? true;
    if (kind.name === "answer") return ({ text: mode !== "allow" && mode !== "default", minutes: mode === "block" } as Record<string, boolean>)[f.name] ?? true;
    return inWhen(kind, values, f.name);
  };
  const fields = $derived(socketFields(kind).filter((f) => data.usedIn.includes(`f:${f.name}`) || (!hide && inMode(f))));
  // выход данных с тем же именем или подписью, что у входа-поля (Машина, Объект, Путь…), стоит в той же строке справа
  const paired = $derived.by(() => {
    const found: Record<string, (typeof outs)[number]> = {};
    const free = outs.filter((o) => (o.type ?? "event") !== "event");
    for (const f of fields) {
      const out = free.find((o) => o.name === f.name || o.label === f.label);
      if (out) {
        found[f.name] = out;
        free.splice(free.indexOf(out), 1);
      }
    }
    return found;
  });
  const lone = $derived(outs.filter((o) => !Object.values(paired).includes(o)));
  // сверху — выходы-события (и сокеты групп), снизу, под всеми полями, — выходы данных без своего поля
  const isData = (o: (typeof outs)[number]) => (o.type ?? "event") !== "event" && !BOXES.includes(kind.name) && kind.name !== "group_in";
  const topOuts = $derived(lone.filter((o) => !isData(o)));
  const bottomOuts = $derived(lone.filter(isData));
  // вход «Ждать с» / «Когда» в одной строке с первым выходом-событием («Получен», «Сделано»)
  const beside = $derived(flowIn ? topOuts[0] ?? null : null);
  const restOuts = $derived(beside ? topOuts.slice(1) : topOuts);
  const params = $derived(hide ? [] : propFields(kind).filter((f) => inWhen(kind, values, f.name)));
  // растущий список: подстановки шаблона («имя» + значение) или входы «Логики» (A, B, C…)
  const grow = $derived(kind.grow ?? null);
  const rows = $derived(visibleRows(kind, values).filter((r) => !hide || data.usedIn.includes(`f:${r.id}`)));
  const letter = (i: number) => (i < 26 ? String.fromCharCode(65 + i) : `${i + 1}`);
  function setRow(row: Row, patch: Partial<Row>) {
    const list = rowsOf(kind, values);
    const next = list.some((r) => r.id === row.id) ? list.map((r) => (r.id === row.id ? { ...r, ...patch } : r)) : [...list, { id: row.id, ...patch }];
    data.onfield(grow!.field, next);
  }
  const flowLabel = $derived(isNoun ? "Ждать с" : "Когда");
  const shape = $derived([ins.map((s) => s.name), outs.map((s) => s.name), fields.map((f) => f.name), rows.map((r) => r.id), data.waiting, hide, flowIn].join("|"));
  const update = useUpdateNodeInternals();
  $effect(() => {
    shape;
    queueMicrotask(() => update(id));
  });
  const role = $derived(data.waiting ? { text: "ждёт", tip: "Есть провод в «Ждать с»: прохождение ждёт событие здесь" }
                        : outs.some((o) => (o.type ?? "event") === "event" && data.used.includes(o.name)) || !data.used.length ? { text: "старт", tip: "Нет провода в «Ждать с»: событие запускает прохождение" }
                        : { text: "данные", tip: "Подключены только данные: нода ничего не ловит, а отдаёт вещь или значение" });
  const days = (value: number) => (value < 1 ? "<1 дн." : `${Math.floor(value)} дн.`);
  const tip = (title: string, type: string, text: string, extra = "") => [title, [type, text].filter(Boolean).join(" · "), extra].filter(Boolean).join("\n");
  const typeLabel = (type: string | undefined) => TYPES[type ?? "event"]?.label ?? "";
  const outTip = (name: string, label: string, type: string | undefined) => tip(label || name, typeLabel(type), data.help[name] ?? (name.match(/^[a-z]\d+$/) ? "ветка" : ""));
  const inTip = (name: string, label: string, type: string | undefined) => tip(label, typeLabel(type), data.help[name] ?? "", data.fedFrom[name] ? `подключено: ${data.fedFrom[name]}` : "не подключено");
  const val = (name: string) => (values[name] === undefined || values[name] === null ? "" : String(values[name]));
  const options = (f: Field) => data.picks[f.kind] ?? [];
  const shown = (f: Field) => {
    const raw = val(f.name);
    return options(f).find((o) => o.value === raw)?.label.split(" · ")[0] ?? raw;
  };
  const set = (name: string, value: unknown) => data.onfield(name, value === "" ? undefined : value);
</script>

<div class="node" class:selected class:muted-node={data.node.mute} class:box={kind.name === "group" || kind.name === "scenario"} style="--head: {COLORS[kind.group] ?? '#555'}">
  <header data-tip={tip(kind.title ? `${kind.label}: ${titleOf(kind, values)}` : kind.label, "", kind.help)}>
    <b>{titleOf(kind, values)}</b>
    {#if isNoun}<span class="tag" title={role.tip}>{role.text}</span>{/if}
    {#if kind.name === "group"}<span class="tag" title="Tab — войти в группу">Tab</span>{/if}
    {#if kind.owned}<span class="tag" title="Tab — граф попытки этой вещи">Tab</span>{/if}
    {#if hide}<span class="tag" title="Неподключённые сокеты скрыты (Ctrl+H)">…</span>{/if}
    <span class="spacer"></span>
    {#if data.errors}<span class="n err" title="Ошибок: {data.errors}">{data.errors}</span>{/if}
    {#if data.box}<span class="n err" title="Ошибок внутри: {data.box}">{data.box}</span>{/if}
    {#if data.warnings}<span class="n warn" title="Предупреждений: {data.warnings}">{data.warnings}</span>{/if}
  </header>
  {#if data.summary && kind.name === "group"}<div class="summary" title={data.summary}>{data.summary}</div>{/if}

  {#if params.length}
    <div class="props">
      {#each params as f (f.name)}
        <select class="nodrag inline wide" value={val(f.name) || f.options[0]?.value} disabled={!data.editable} aria-label={f.label} title={f.label}
                onchange={(e) => set(f.name, e.currentTarget.value)}>
          {#each f.options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
        </select>
      {/each}
    </div>
  {/if}

  {#if beside}
    <div class="row both" class:used={data.usedIn.includes("in") || data.used.includes(beside.name)}>
      <span class="half in" class:used={data.usedIn.includes("in")} data-tip={inTip("in", flowLabel, "event")}>
        <Handle type="target" position={Position.Left} id="in" class="sock" style="--c: {TYPES.event.color}" />{flowLabel}
      </span>
      <span class="half out" class:used={data.used.includes(beside.name)} data-tip={outTip(beside.name, beside.label, beside.type)}>
        {beside.label}<Handle type="source" position={Position.Right} id={beside.name} class="sock" style="--c: {typeColor(beside.type ?? 'event')}" />
      </span>
    </div>
  {/if}
  {#each restOuts as sock (sock.name)}
    <div class="row out" class:used={data.used.includes(sock.name)} class:attempt={sock.name === "attempt"} data-tip={outTip(sock.name, sock.label, sock.type)}>
      <span>{sock.label}</span>
      <Handle type="source" position={Position.Right} id={sock.name} class="sock" style="--c: {typeColor(sock.type ?? 'event')}" data-thing={isThing(sock.type) ? "1" : undefined} />
    </div>
  {/each}


  {#if flowIn && !beside}
    <div class="row in" class:used={data.usedIn.includes("in")} data-tip={inTip("in", flowLabel, "event")}>
      <Handle type="target" position={Position.Left} id="in" class="sock" style="--c: {TYPES.event.color}" />
      <span>{flowLabel}</span>
    </div>
  {/if}
  {#each ins as sock (sock.name)}
    <div class="row in" class:used={data.usedIn.includes(sock.name)} data-tip={inTip(sock.name, sock.label, sock.type)}>
      <Handle type="target" position={Position.Left} id={sock.name} class="sock" style="--c: {typeColor(sock.type ?? 'event')}" data-thing={isThing(sock.type) ? "1" : undefined} />
      <span>{sock.label}</span>
    </div>
  {/each}
  {#each fields as f (f.name)}
    {@const key = `f:${f.name}`}
    {@const fed = data.usedIn.includes(key)}
    <div class="row in field" class:used={fed} data-tip={inTip(key, f.label, f.socket)}>
      <Handle type="target" position={Position.Left} id={key} class="sock" style="--c: {typeColor(f.socket)}" data-thing={isThing(f.socket) ? "1" : undefined} />
      <span class="label" class:req={f.required && !fed && !val(f.name)}>{f.label}</span>
      {#if !fed}
        {#if f.socket === "bool" && f.kind === "bool"}
          <input class="nodrag check" type="checkbox" checked={!!values[f.name]} disabled={!data.editable} onchange={(e) => set(f.name, e.currentTarget.checked || undefined)} aria-label={f.label} />
        {:else if options(f).length}
          <select class="nodrag inline" value={val(f.name)} disabled={!data.editable} onchange={(e) => set(f.name, f.kind === "section" ? Number(e.currentTarget.value) || undefined : e.currentTarget.value)}
                  aria-label={f.label} title={shown(f)}>
            <option value="">{f.placeholder || "—"}</option>
            {#if val(f.name) && !options(f).some((o) => o.value === val(f.name))}<option value={val(f.name)}>{val(f.name)}</option>{/if}
            {#each options(f) as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
          </select>
        {:else if f.socket === "number"}
          <input class="nodrag inline num" type="number" value={val(f.name)} placeholder={f.placeholder} disabled={!data.editable} aria-label={f.label}
                 oninput={(e) => set(f.name, e.currentTarget.value === "" ? undefined : +e.currentTarget.value)} />
        {:else}
          <input class="nodrag inline" class:mono={f.kind === "condition" || f.kind === "expr" || f.kind === "path" || f.kind === "clock"} value={val(f.name)}
                 placeholder={f.placeholder} disabled={!data.editable} aria-label={f.label} title={val(f.name)} oninput={(e) => set(f.name, e.currentTarget.value)} />
        {/if}
      {:else if paired[f.name]}<span class="spacer"></span>
      {/if}
      {#if paired[f.name]}
        {@const out = paired[f.name]}
        <span class="pass" class:used={data.used.includes(out.name)} data-tip={outTip(out.name, out.label, out.type)}>
          <Handle type="source" position={Position.Right} id={out.name} class="sock" style="--c: {typeColor(out.type ?? 'event')}" data-thing={isThing(out.type) ? "1" : undefined} />
        </span>
      {/if}
    </div>
  {/each}
  {#if grow}
    {#each rows as row, i (row.id)}
      {@const key = `f:${row.id}`}
      {@const fed = data.usedIn.includes(key)}
      <div class="row in field" class:used={fed || !row.empty} class:empty={row.empty && !fed}
           data-tip={inTip(key, grow.named ? String(row.name || "подстановка") : letter(i), grow.type)}>
        <Handle type="target" position={Position.Left} id={key} class="sock" style="--c: {typeColor(grow.type)}" data-thing={isThing(grow.type) ? "1" : undefined} />
        {#if grow.named}
          <input class="nodrag inline name mono" value={String(row.name ?? "")} placeholder="имя" disabled={!data.editable} aria-label="Имя подстановки"
                 oninput={(e) => setRow(row, { name: e.currentTarget.value.replace(/[{}]/g, "") || undefined })} />
          {#if !fed}
            <input class="nodrag inline" value={row.value === undefined || row.value === null ? "" : String(row.value)} placeholder="значение"
                   disabled={!data.editable} aria-label="Значение подстановки" oninput={(e) => setRow(row, { value: e.currentTarget.value || undefined })} />
          {/if}
        {:else}
          <span class="label">{letter(i)}</span>
          {#if !fed && grow.type === "bool"}
            <input class="nodrag check" type="checkbox" checked={!!row.value} disabled={!data.editable} aria-label={letter(i)}
                   onchange={(e) => setRow(row, { value: e.currentTarget.checked || undefined })} />
          {/if}
        {/if}
      </div>
    {/each}
  {/if}

  {#each bottomOuts as sock (sock.name)}
    <div class="row out" class:used={data.used.includes(sock.name)} data-tip={outTip(sock.name, sock.label, sock.type)}>
      <span>{sock.label}</span>
      <Handle type="source" position={Position.Right} id={sock.name} class="sock" style="--c: {typeColor(sock.type ?? 'event')}" data-thing={isThing(sock.type) ? "1" : undefined} />
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
  .node { width: 250px; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--radius); font-size: 12px; color: var(--text); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); padding-bottom: 4px; }
  .node.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 4px 14px rgba(0, 0, 0, 0.35); }
  .node.muted-node { opacity: 0.45; }
  .node.box { border-width: 2px; border-style: double; }
  header { display: flex; align-items: center; gap: 6px; padding: 5px 10px; margin-bottom: 4px; background: color-mix(in srgb, var(--head) 70%, var(--raise)); border-radius: var(--radius) var(--radius) 0 0; }
  header b { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tag { font-size: 10px; padding: 0 5px; border-radius: 999px; background: rgba(0, 0, 0, 0.25); color: var(--text); }
  .spacer { flex: 1; }
  .n { min-width: 16px; padding: 0 5px; border-radius: 999px; text-align: center; font-size: 10.5px; font-weight: 600; color: #111; }
  .n.err { background: var(--danger); }
  .n.warn { background: var(--warn); }
  .summary { padding: 0 10px 4px; color: var(--muted); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row { position: relative; display: flex; align-items: center; gap: 6px; padding: 1px 12px; min-height: 21px; color: var(--faint); font-size: 11.5px; }
  .row.out { justify-content: flex-end; }
  .row.used { color: var(--text); }
  .row.field .label { flex: 0 0 auto; max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row.field.used .label { max-width: none; }
  .label.req { color: var(--danger); }
  .props { display: flex; flex-direction: column; gap: 3px; padding: 3px 12px; }
  .inline { flex: 1; min-width: 0; height: 19px; padding: 0 5px; border: 1px solid var(--line); border-radius: 4px; background: var(--bg); color: var(--text); font: inherit; font-size: 11px; }
  .inline:focus { outline: none; border-color: var(--accent); }
  .inline.num { flex: 0 0 72px; margin-left: auto; }
  .inline.wide { width: 100%; }
  .inline.name { flex: 0 0 74px; }
  .row.empty .inline { border-style: dashed; }
  .row.both { justify-content: space-between; padding: 1px 0; }
  .half { display: flex; align-items: center; padding: 0 12px; min-height: 21px; color: var(--faint); }
  .half.used { color: var(--text); }
  .half.used :global(.svelte-flow__handle.sock) { background: var(--c); }
  .row.field:has(.pass) { padding-right: 14px; }
  .pass { position: absolute; right: 0; top: 50%; width: 0; height: 0; }
  .pass.used :global(.svelte-flow__handle.sock) { background: var(--c); }
  .mono { font-family: var(--mono); }
  .check { margin-left: auto; }
  footer { display: flex; flex-wrap: wrap; gap: 4px 8px; margin-top: 4px; padding: 4px 10px 0; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 10.5px; }
  .wait { color: var(--accent); }
  .wait.old { color: var(--warn); }
  .node :global(.svelte-flow__handle.sock) { width: 10px; height: 10px; background: var(--panel-2); border: 2px solid var(--c); }
  .node :global(.svelte-flow__handle.sock[data-thing]) { width: 9px; height: 9px; border-radius: 1px; }
  .node :global(.svelte-flow__handle.sock[data-thing].svelte-flow__handle-left) { transform: translate(-50%, -50%) rotate(45deg); }
  .node :global(.svelte-flow__handle.sock[data-thing].svelte-flow__handle-right) { transform: translate(50%, -50%) rotate(45deg); }
  .row.used :global(.svelte-flow__handle.sock) { background: var(--c); }
</style>
