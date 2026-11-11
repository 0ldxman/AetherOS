<script lang="ts">
  // Сценарий переписки: карта шагов (узлы ставит автор, выход варианта тянется на шаг) и боковая панель: шаг, песочница, проверка.
  // Правится на общем черновике: каждый шаг отдельное поле, два автора правят разные шаги одновременно.
  import { onMount, untrack } from "svelte";
  import { Background, Controls, MarkerType, MiniMap, Panel, SvelteFlow, type Connection, type Edge, type Node } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";
  import { api, problem, type Schemas } from "../../lib/api";
  import DraftState from "../../lib/DraftState.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { canAct, canEdit } from "../../lib/me.svelte";
  import { go } from "../../lib/router.svelte";
  import { SharedForm } from "../../lib/shared.svelte";
  import { toast } from "../../lib/toast.svelte";
  import AddStep from "./AddStep.svelte";
  import FitOnce from "./FitOnce.svelte";
  import Sandbox from "./Sandbox.svelte";
  import StepNode from "./StepNode.svelte";
  import StepPanel from "./StepPanel.svelte";
  import { emptyStep, freeName, gotos, renameRefs, stepField, stepsOf, toDoc, toForm, type Action, type Form, type StepDraft } from "./doc";

  let { id }: { id: number } = $props();

  let talk = $state<Schemas["MlTalk"] | null>(null);
  let personas = $state<Schemas["MlPersona"][]>([]);
  let picks = $state<Schemas["MlPicks"] | null>(null);
  let form = $state<Form>({ title: "", slug: "", note: "", persona: 0 });
  let base = $state<Form | null>(null);
  let saved = $state("");
  let problems = $state<Schemas["MlProblem"][]>([]);
  let selected = $state("");
  let selectedName = "";
  let tab = $state<"step" | "try" | "check">("step");
  let busy = $state(false);
  let current = $state("");                                       // шаг игрока в песочнице

  const editable = canEdit("mail");
  const steps = $derived(stepsOf(form));
  const names = $derived(steps.map((s) => s.name));
  const step = $derived(steps.find((s) => s.key === selected) ?? null);
  const docJson = $derived(JSON.stringify(toDoc(form)));
  const dirty = $derived(saved !== "" && docJson !== saved);
  const errors = $derived(problems.filter((p) => p.level === "error").length);
  guardUnsaved(() => dirty && !share.ready);

  function fill(data: Schemas["MlTalk"], keepDraft = false) {
    talk = data;
    base = toForm(data.doc);
    if (!keepDraft) form = toForm(data.doc);
    saved = JSON.stringify(toDoc(base));
    problems = data.problems;
    const again = steps.find((s) => s.key === selected) ?? steps.find((s) => s.name === selectedName);
    selected = again?.key ?? "";
  }

  async function load(keepDraft = false) {
    const { data } = await api.GET("/studio/api/mail/conversations/{talk_id}", { params: { path: { talk_id: id } } });
    if (data) fill(data, keepDraft);
    else toast("Сценарий не найден.", "error");
  }
  async function loadPicks() {
    const [letters, keys] = await Promise.all([
      api.GET("/studio/api/mail/picks", { params: { query: { kind: "letter" } } }),
      api.GET("/studio/api/mail/picks", { params: { query: { kind: "key" } } }),
    ]);
    if (letters.data) picks = { ...letters.data, items: [...letters.data.items, ...(keys.data?.items ?? [])] };
  }
  onMount(async () => {
    personas = (await api.GET("/studio/api/mail")).data ?? [];
    await Promise.all([load(), loadPicks()]);
  });

  const share = new SharedForm({ room: () => `mail/conversations/${id}`, open: true, draft: () => form, base: () => base, onRemoteSave: () => load(true) });

  // проверка черновика: ошибки на узлах и во вкладке «Проверка»
  let checkTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const body = docJson;
    if (!talk) return;
    clearTimeout(checkTimer);
    checkTimer = setTimeout(async () => {
      const { data } = await api.POST("/studio/api/mail/check", { body: JSON.parse(body) });
      if (data && body === docJson) problems = data;
    }, 400);
  });

  async function save() {
    busy = true;
    const { data, error } = await api.PUT("/studio/api/mail/conversations/{talk_id}", { params: { path: { talk_id: id } }, body: JSON.parse(docJson) });
    busy = false;
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    selectedName = step?.name ?? "";
    fill(data);
    share.markSaved();
    loadPicks();
    toast(data.problems.some((p) => p.level === "error") ? "Сохранено, но в сценарии есть ошибки: см. «Проверка»." : "Сценарий сохранён.");
  }

  async function remove() {
    if (!(await ask(`Удалить сценарий «${talk?.doc.title}»?`, "Игроки, которые его проходят, потеряют переписку с персонажем по нему.", "Удалить сценарий"))) return;
    const { error } = await api.DELETE("/studio/api/mail/conversations/{talk_id}", { params: { path: { talk_id: id } } });
    if (error) return toast(problem(error), "error");
    toast("Сценарий удалён.");
    go("/mail");
  }

  // ---- правка шагов ----
  const put = (next: StepDraft) => (form[stepField(next.key)] = next);

  function addStep(x: number, y: number) {
    const fresh = emptyStep(freeName(steps), (steps[steps.length - 1]?.order ?? -1) + 1, x, y);
    put(fresh);
    selected = fresh.key;
    tab = "step";
  }

  async function removeStep(target: StepDraft) {
    const incoming = gotos(steps).filter((g) => g.target === target.name).length;
    if (!(await ask(`Удалить шаг «${target.name}»?`, incoming ? `Переходы на него (${incoming}) тоже уберутся.` : "Его письмо и варианты пропадут после сохранения.", "Удалить шаг"))) return;
    form[stepField(target.key)] = null;
    for (const other of stepsOf(form)) {
      const variants = other.variants.map((v) => ({
        ...v, outcomes: Object.fromEntries(Object.entries(v.outcomes)
          .map(([socket, actions]) => [socket, actions.filter((a) => !(a.do === "goto" && a.step === target.name))] as const)
          .filter(([, actions]) => actions.length)),
      }));
      if (JSON.stringify(variants) !== JSON.stringify(other.variants)) put({ ...other, variants });
    }
    selected = "";
  }

  function rename(from: string, to: string) {
    for (const other of stepsOf(form)) {
      const next = renameRefs(other, from, to);
      if (next !== other) put(next);
    }
  }

  function setGoto(sourceKey: string, handle: string, targetName: string | null) {
    const source = steps.find((s) => s.key === sourceKey);
    if (!source) return;
    const [index, ...rest] = handle.split("|");
    const socket = rest.join("|");
    const variants = source.variants.map((v, i) => {
      if (i !== +index) return v;
      const actions: Action[] = (v.outcomes[socket] ?? []).filter((a) => a.do !== "goto");
      if (targetName) actions.unshift({ do: "goto", step: targetName });
      const outcomes = { ...v.outcomes };
      if (actions.length) outcomes[socket] = actions;
      else delete outcomes[socket];
      return { ...v, outcomes };
    });
    put({ ...source, variants });
  }

  // ---- карта ----
  const nodeTypes = { step: StepNode };
  let nodes = $state.raw<Node[]>([]);
  let edges = $state.raw<Edge[]>([]);

  $effect(() => {
    const list = steps;
    const found = problems;
    const chosen = selected;
    const first = list.find((s) => !s.opening)?.key;
    const keyOf = new Map(list.map((s) => [s.name, s.key]));
    untrack(() => {
      nodes = list.map((s) => ({
        id: s.key, type: "step", position: { x: s.x, y: s.y }, deletable: false, selected: s.key === chosen,
        data: { step: s, start: s.key === first, errors: found.filter((p) => p.step === s.name && p.level === "error").length,
                warnings: found.filter((p) => p.step === s.name && p.level === "warning").length },
      }));
      edges = gotos(list).flatMap((g, n) => {
        const target = keyOf.get(g.target);
        if (!target) return [];
        const bad = g.socket === "wrong" || g.socket === "exhausted";
        return [{ id: `${g.from.key}|${g.variant}|${g.socket}|${n}`, source: g.from.key, sourceHandle: `${g.variant}|${g.socket}`, target,
                  markerEnd: { type: MarkerType.ArrowClosed, color: bad ? "var(--danger)" : "var(--accent)" }, class: bad ? "bad" : "",
                  data: { name: g.target } } satisfies Edge];
      });
    });
  });

  function onconnect(connection: Connection) {
    const target = steps.find((s) => s.key === connection.target);
    if (!target || !connection.sourceHandle) return;
    setGoto(connection.source, connection.sourceHandle, target.name);
  }
  // выход брошен не на точку входа, а на сам узел шага: тоже переход
  function onconnectend(event: MouseEvent | TouchEvent, state: { isValid: boolean | null; fromNode: { id: string } | null; fromHandle: { id?: string | null } | null }) {
    if (state.isValid || !state.fromNode || !state.fromHandle?.id) return;
    const point = "changedTouches" in event ? event.changedTouches[0] : event;
    const element = document.elementFromPoint(point.clientX, point.clientY)?.closest(".svelte-flow__node");
    const target = steps.find((s) => s.key === element?.getAttribute("data-id"));
    if (target) setGoto(state.fromNode.id, state.fromHandle.id, target.name);
  }
  function ondelete({ edges: gone }: { nodes: Node[]; edges: Edge[] }) {
    for (const edge of gone) if (edge.sourceHandle) setGoto(edge.source, edge.sourceHandle, null);
  }
  function ondragstop({ nodes: moved }: { nodes: Node[] }) {
    for (const node of moved) {
      const s = stepsOf(form).find((x) => x.key === node.id);
      if (s && (s.x !== node.position.x || s.y !== node.position.y)) put({ ...s, x: Math.round(node.position.x), y: Math.round(node.position.y) });
    }
  }
  const stepProblems = $derived(step ? problems.filter((p) => p.step === step.name) : []);
  const persona = $derived(personas.find((p) => p.id === form.persona));
</script>

{#if !talk}
  <p class="muted pad">Загрузка…</p>
{:else}
  <div class="talk">
    <header class="head">
      <a class="btn ghost" href={persona ? `#/mail/personas/${persona.id}` : "#/mail"} aria-label="К персонажу" title="К персонажу">←</a>
      <input class="title" bind:value={form.title} aria-label="Название сценария" disabled={!editable} />
      <span class="who muted">{persona ? (persona.name ? `${persona.name} · ${persona.address}` : persona.address) : ""}</span>
      <span class="spacer"></span>
      <DraftState {share} {dirty} />
      {#if canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
      <button class="btn primary" disabled={!dirty || busy || !editable || !form.title.trim()} onclick={save}>Сохранить</button>
    </header>

    <div class="cols">
      <div class="map">
        {#if nodes.length || !steps.length}
        <SvelteFlow bind:nodes bind:edges {nodeTypes} colorMode="dark" minZoom={0.2} maxZoom={1.5} nodesDraggable={editable} nodesConnectable={editable}
                    deleteKey={["Delete", "Backspace"]} {onconnect} {onconnectend} {ondelete} onnodedragstop={ondragstop}
                    onnodeclick={({ node }) => { selected = node.id; tab = "step"; }} onpaneclick={() => (selected = "")}
                    defaultEdgeOptions={{ type: "smoothstep" }} proOptions={{ hideAttribution: true }}>
          <FitOnce />
          <Background gap={24} />
          <Controls showLock={false} />
          <MiniMap pannable zoomable bgColor="#15171c" nodeColor="#2a2e37" maskColor="rgba(0, 0, 0, 0.5)" />
          <Panel position="top-left">
            {#if editable}<AddStep onadd={addStep} />{/if}
            <span class="tip muted">Тяните точку выхода варианта на шаг, чтобы задать переход. Delete убирает выбранную стрелку.</span>
          </Panel>
        </SvelteFlow>
        {/if}
      </div>

      <aside class="side">
        <div class="tabs" role="tablist">
          <button role="tab" class:on={tab === "step"} aria-selected={tab === "step"} onclick={() => (tab = "step")}>{step ? `Шаг ${step.name}` : "Сценарий"}</button>
          <button role="tab" class:on={tab === "try"} aria-selected={tab === "try"} onclick={() => { tab = "try"; if (!current) current = (steps.find((s) => s.opening) ?? steps[0])?.key ?? ""; }}>Песочница</button>
          <button role="tab" class:on={tab === "check"} aria-selected={tab === "check"} onclick={() => (tab = "check")}>Проверка{#if problems.length}<span class="count" class:bad={errors > 0}>{problems.length}</span>{/if}</button>
        </div>
        <div class="pane">
          {#if tab === "step" && step}
            {#key step.key}
              <StepPanel {step} steps={names} {picks} problems={stepProblems} onchange={put} onrename={rename} onremove={() => removeStep(step)} />
            {/key}
          {:else if tab === "step"}
            <div class="settings">
              <label><span class="label">Персонаж</span>
                <select class="field" bind:value={form.persona} disabled={!editable}>
                  {#each personas as p (p.id)}<option value={p.id}>{p.name ? `${p.name} · ${p.address}` : p.address}</option>{/each}
                </select></label>
              <label><span class="label">Идентификатор</span><input class="field mono" bind:value={form.slug} disabled={!editable} /></label>
              <p class="muted small">Запуск из слоя: хук <code>mail {form.slug}</code>, игрок получит письмо первого шага. Игрок может и сам написать на адрес персонажа: тогда ему видны варианты шагов «начало».</p>
              <label><span class="label">Заметка автора</span><textarea class="field" rows="5" bind:value={form.note} disabled={!editable} placeholder="Что задумано, где игрок берёт пароль, что проверить"></textarea></label>
              <p class="muted small">Шагов {steps.length}. Выберите шаг на карте, чтобы править его письмо и варианты.</p>
            </div>
          {:else if tab === "try"}
            <Sandbox {steps} {picks} bind:current />
          {:else}
            <div class="checks">
              {#each problems as p, i (i)}
                <button class="problem" class:error={p.level === "error"} onclick={() => { const s = steps.find((x) => x.name === p.step); if (s) { selected = s.key; tab = "step"; } }}>
                  {#if p.step}<span class="mono">{p.step}{p.variant !== null ? ` · вариант ${p.variant + 1}` : ""}</span>{/if}
                  <span>{p.text}</span>
                </button>
              {:else}
                <p class="muted small">Ошибок нет.</p>
              {/each}
            </div>
          {/if}
        </div>
      </aside>
    </div>
  </div>
  <datalist id="mail-flags">{#each picks?.flags ?? [] as f (f)}<option value={f}></option>{/each}</datalist>
  <datalist id="mail-keys">{#each (picks?.items ?? []).filter((i) => i.format === "key") as k (k.slug)}<option value={k.slug}></option>{/each}</datalist>
{/if}

<style>
  .pad { padding: 20px 32px; }
  .talk { display: flex; flex-direction: column; height: 100vh; }
  .head { display: flex; align-items: center; gap: 10px; padding: 12px 20px; border-bottom: 1px solid var(--line-soft); }
  .title { min-width: 0; width: 360px; padding: 6px 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; font-size: 18px; font-weight: 600; }
  .title:hover, .title:focus { border-color: var(--line-soft); background: var(--bg); outline: none; }
  .who { font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .spacer { flex: 1; }
  .cols { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 440px; }
  .map { position: relative; min-width: 0; min-height: 0; }
  .side { display: flex; flex-direction: column; min-height: 0; border-left: 1px solid var(--line-soft); }
  .tabs { display: flex; gap: 2px; padding: 8px 10px 0; border-bottom: 1px solid var(--line-soft); }
  .tabs button { padding: 7px 12px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); cursor: pointer; font: inherit; font-size: 13px; }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .count { margin-left: 6px; padding: 0 6px; border-radius: 999px; background: var(--warn); color: #111; font-size: 11px; font-weight: 700; }
  .count.bad { background: var(--danger); }
  .pane { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px 40px; }
  .settings { display: flex; flex-direction: column; gap: 12px; }
  label { display: flex; flex-direction: column; gap: 4px; }
  textarea { resize: vertical; font: inherit; }
  .mono { font-family: var(--mono); }
  .small { font-size: 12px; margin: 0; }
  .tip { font-size: 12px; margin-left: 10px; }
  .checks { display: flex; flex-direction: column; gap: 6px; }
  .problem { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border: 0; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); text-align: left; font: inherit; font-size: 12.5px; cursor: pointer; }
  .problem.error { background: var(--danger-soft); color: var(--danger); }
  .problem .mono { font-size: 11.5px; opacity: 0.85; }
  .map :global(.svelte-flow) { --xy-background-color: var(--bg); --xy-edge-stroke: var(--accent); --xy-edge-stroke-width: 1.6; --xy-controls-button-background-color: var(--panel-2);
                               --xy-controls-button-border-color: var(--line); --xy-controls-button-color: var(--text); }
  .map :global(.svelte-flow__edge.bad path) { stroke: var(--danger); }
  .map :global(.svelte-flow__edge.selected path) { stroke-width: 3; }
  .map :global(.svelte-flow__node) { border: 0; padding: 0; background: none; width: auto; }
</style>
