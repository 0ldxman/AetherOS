<script lang="ts">
  // Конструктор условия доступа. Текст (value) остаётся источником правды, как у слоёв: конструктор собирает его из дерева.
  import { onMount, untrack } from "svelte";
  import { api, type Schemas } from "./api";
  import AccessNode, { fromTree, toTree, type Node, type Tree } from "./AccessNode.svelte";
  import { engine } from "./engine.svelte";

  let { value = $bindable(""), bad = false }: { value: string; bad?: boolean } = $props();

  const facts = engine();
  let keys = $state<Schemas["Key"][]>([]);
  let mode = $state<"build" | "text">("build");
  let model = $state<Node | null>(null);
  let error = $state("");

  let lastBuilt = value ?? "";
  let sequence = 0;
  let timer: ReturnType<typeof setTimeout>;

  onMount(async () => {
    keys = (await api.GET("/studio/api/keys")).data ?? [];
  });

  async function parse(text: string) {
    const mine = ++sequence;
    const { data } = await api.POST("/studio/api/access/parse", { body: { text } });
    if (!data || mine !== sequence) return;
    lastBuilt = text;
    error = data.ok ? "" : data.error;
    if (!data.ok) {
      model = null;
      mode = "text";
      return;
    }
    const root = data.tree == null ? null : fromTree(data.tree as Tree);
    model = root && root.kind === "key" ? { kind: "all", items: [root], negated: false } : root;
  }

  // текст изменился снаружи (режим «Текст», загрузка): разбираем заново
  let loaded = false;
  $effect(() => {
    const text = value ?? "";
    if (text === lastBuilt && loaded) return;
    untrack(() => {
      clearTimeout(timer);
      timer = setTimeout(() => { loaded = true; parse(text); }, loaded ? 250 : 0);
    });
  });

  async function push() {
    const mine = ++sequence;
    const tree = model ? toTree($state.snapshot(model) as Node) : null;
    const { data } = await api.POST("/studio/api/access/format", { body: { tree } });
    if (!data || mine !== sequence) return;
    lastBuilt = data.text;
    value = data.text;
  }

  function start() {
    model = { kind: "all", items: [{ kind: "key", key: "", negated: false }], negated: false };
  }

  function clear() {
    model = null;
    push();
  }
</script>

<div class="access">
  <div class="bar">
    <div class="seg" role="tablist">
      <button type="button" class:on={mode === "build"} disabled={!!error} title={error} onclick={() => (mode = "build")}>Конструктор</button>
      <button type="button" class:on={mode === "text"} onclick={() => (mode = "text")}>Текст</button>
    </div>
  </div>
  {#if error}<p class="warn small">Конструктор недоступен: {error} Поправьте текст, и он снова включится.</p>{/if}

  {#if mode === "text"}
    <input class="field mono" class:bad bind:value placeholder="открыто всем" aria-label="Условие доступа" />
    <p class="muted small">Ключи по слагу, <span class="mono">and</span>, <span class="mono">or</span>, <span class="mono">not</span> и скобки: <span class="mono">cardkey and (door or not alarm)</span>.</p>
  {:else if !model}
    <p class="muted small">Открыто всем: никаких проверок нет.</p>
    <button type="button" class="btn" onclick={start}>+ Задать условие</button>
  {:else}
    <AccessNode node={model} root onchange={push} onremove={clear} />
  {/if}
  <datalist id="access-keys">
    {#each keys as key (key.slug)}<option value={key.slug}>{key.description}</option>{/each}
    {#each facts.catalog?.picks.flag ?? [] as o (o.value)}<option value={"flag:" + o.value}>метка игрока</option>{/each}
    {#each facts.catalog?.picks.world_flag ?? [] as o (o.value)}<option value={"world:" + o.value}>метка мира</option>{/each}
  </datalist>
</div>

<style>
  .access { display: flex; flex-direction: column; gap: 8px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: var(--radius-s); overflow: hidden; }
  .seg button { padding: 4px 12px; border: 0; background: none; color: var(--muted); cursor: pointer; }
  .seg button.on { background: var(--panel-2); color: var(--text); }
  .seg button:disabled { opacity: 0.45; cursor: not-allowed; }
  .warn { margin: 0; color: var(--warn); }
  p { margin: 0; }
  .btn { align-self: flex-start; }
  .field.bad { border-color: var(--danger); }
</style>
