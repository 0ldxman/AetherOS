<script lang="ts" module>
  export type Tree = string | { not: Tree } | { all: Tree[] } | { any: Tree[] };
  export type Node = { kind: "key"; key: string; negated: boolean } | { kind: "all" | "any"; items: Node[]; negated: boolean };

  export function fromTree(tree: Tree): Node {
    if (typeof tree === "string") return { kind: "key", key: tree, negated: false };
    if ("not" in tree) {
      const inner = fromTree(tree.not);
      inner.negated = !inner.negated;
      return inner;
    }
    if ("all" in tree) return { kind: "all", items: tree.all.map(fromTree), negated: false };
    return { kind: "any", items: tree.any.map(fromTree), negated: false };
  }

  export function toTree(node: Node): Tree {
    const base: Tree = node.kind === "key" ? node.key : node.kind === "all" ? { all: node.items.map(toTree) } : { any: node.items.map(toTree) };
    return node.negated ? { not: base } : base;
  }
</script>

<script lang="ts">
  import AccessNode from "./AccessNode.svelte";

  let { node, root = false, onchange, onremove }: { node: Node; root?: boolean; onchange: () => void; onremove?: () => void } = $props();
</script>

{#if node.kind === "key"}
  <div class="leaf">
    <label class="not" title="Условие выполнится, когда ключа НЕТ"><input type="checkbox" checked={node.negated} onchange={(event) => { node.negated = event.currentTarget.checked; onchange(); }} /> не</label>
    <input
      class="field mono" list="access-keys" placeholder="ключ" aria-label="Ключ" value={node.key}
      oninput={(event) => { node.key = event.currentTarget.value.replace(/[^A-Za-z0-9_-]/g, ""); onchange(); }}
    />
    <button type="button" class="icon danger" aria-label="Убрать ключ" onclick={onremove}>✕</button>
  </div>
{:else}
  <div class="group" class:root>
    <div class="head">
      <label class="not" title="Инвертировать всю группу"><input type="checkbox" checked={node.negated} onchange={(event) => { node.negated = event.currentTarget.checked; onchange(); }} /> не</label>
      <select class="field" value={node.kind} onchange={(event) => { node.kind = event.currentTarget.value as "all" | "any"; onchange(); }}>
        <option value="all">нужны все из:</option>
        <option value="any">нужен любой из:</option>
      </select>
      {#if onremove}<button type="button" class="icon danger" aria-label={root ? "Убрать условие" : "Убрать группу"} onclick={onremove}>✕</button>{/if}
    </div>
    <div class="items">
      {#each node.items as child, at (at)}
        <AccessNode node={child} {onchange} onremove={() => { node.items.splice(at, 1); onchange(); }} />
      {:else}
        <span class="muted small">Пусто: добавьте ключ.</span>
      {/each}
    </div>
    <div class="adders">
      <button type="button" class="link" onclick={() => { node.items.push({ kind: "key", key: "", negated: false }); onchange(); }}>+ Ключ</button>
      <button type="button" class="link" onclick={() => { node.items.push({ kind: "any", items: [{ kind: "key", key: "", negated: false }], negated: false }); onchange(); }}>+ Группа</button>
    </div>
  </div>
{/if}

<style>
  .leaf { display: flex; align-items: center; gap: 8px; }
  .leaf .field { flex: 1; min-width: 0; }
  .group { display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); }
  .group.root { background: none; border-color: var(--line); }
  .head { display: flex; align-items: center; gap: 8px; }
  .head select { width: auto; }
  .items { display: flex; flex-direction: column; gap: 6px; padding-left: 12px; border-left: 2px solid var(--line); }
  .adders { display: flex; gap: 14px; }
  .not { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); cursor: pointer; white-space: nowrap; }
  .icon { width: 26px; height: 26px; border: 1px solid var(--line); border-radius: var(--radius-s); background: none; color: var(--muted); cursor: pointer; }
  .icon.danger:hover { color: var(--danger); border-color: var(--danger); }
  .link { padding: 0; border: 0; background: none; color: var(--accent); cursor: pointer; }
</style>
