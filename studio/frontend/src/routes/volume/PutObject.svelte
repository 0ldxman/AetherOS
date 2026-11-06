<script lang="ts">
  // Положить в папку уже существующий объект (тот же объект, не копия): поиск по библиотеке и выбор.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { volume, folder, folderName, onclose, ondone }: {
    volume: number; folder: number | null; folderName: string; onclose: () => void; ondone: () => void;
  } = $props();

  let q = $state("");
  let rows = $state<Schemas["LibraryRow"][]>([]);
  let chosen = $state<Schemas["LibraryRow"] | null>(null);
  let name = $state("");
  let loading = $state(true);
  let busy = $state(false);
  let timer: ReturnType<typeof setTimeout>;

  async function search() {
    loading = true;
    rows = (await api.GET("/studio/api/items", { params: { query: { q, limit: 40 } } })).data ?? [];
    loading = false;
  }

  onMount(search);
  $effect(() => {
    q;
    clearTimeout(timer);
    timer = setTimeout(search, 250);
    return () => clearTimeout(timer);
  });

  async function put() {
    if (!chosen) return;
    busy = true;
    const { error } = await api.POST("/studio/api/items/{item_id}/placements", {
      params: { path: { item_id: chosen.id } }, body: { volume, parent: folder, name: name.trim() },
    });
    busy = false;
    if (error) return toast(problem(error), "error");
    toast("Объект положен.");
    ondone();
    onclose();
  }
</script>

<Dialog title="Положить объект в «{folderName}»" confirm="Положить сюда" wide {busy} disabled={!chosen} onsubmit={put} {onclose}>
  <p class="muted small">Объект останется один: правки текста, слоёв и ключей будут видны во всех местах, где он лежит.</p>
  <input class="field" placeholder="Поиск по названию, слагу или тексту" bind:value={q} />
  <div class="list" role="listbox" aria-label="Объекты">
    {#each rows as row (row.id)}
      <button type="button" class="pick" class:on={chosen?.id === row.id} role="option" aria-selected={chosen?.id === row.id} onclick={() => (chosen = row)}>
        <b>{row.name}</b>
        {#if row.format}<span class="chip">{row.format}</span>{/if}
        <span class="mono muted small">{row.slug}</span>
        <span class="muted small where">{row.where[0] ?? "нигде не лежит"}{row.places > 1 ? ` и ещё ${row.places - 1}` : ""}</span>
      </button>
    {:else}
      <p class="muted">{loading ? "Ищу…" : "Ничего не нашлось."}</p>
    {/each}
  </div>
  {#if chosen}
    <label>
      <span class="label">Имя в этой папке (пусто: как у объекта)</span>
      <input class="field" placeholder={chosen.name} bind:value={name} />
    </label>
  {/if}
</Dialog>

<style>
  .small { font-size: 12px; margin: 0; }
  .list { display: flex; flex-direction: column; gap: 2px; max-height: 300px; overflow-y: auto; padding: 4px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .pick { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; }
  .pick:hover { background: var(--panel); }
  .pick.on { background: var(--accent-soft); }
  .where { margin-left: auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 40%; }
</style>
