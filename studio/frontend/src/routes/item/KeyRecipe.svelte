<script lang="ts">
  // Сборка ключа из частей: части (обычные ключи), где каждая выдаётся, расходуются ли. Игрок собирает командой kjoin.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { item }: { item: Schemas["ItemOut"] } = $props();

  let data = $state<Schemas["WsRecipe"] | null>(null);
  let keys = $state<{ slug: string; description: string }[]>([]);
  let dialog = $state<null | "split" | "pick">(null);
  let count = $state(3);
  let picked = $state<string[]>([]);
  let filter = $state("");
  let busy = $state(false);

  const path = $derived({ slug: item.slug });
  async function load() {
    data = (await api.GET("/studio/api/world/state/keys/{slug}/recipe", { params: { path } })).data ?? null;
  }
  onMount(load);

  async function openPick() {
    keys = ((await api.GET("/studio/api/keys")).data ?? []) as { slug: string; description: string }[];
    picked = data?.parts.map((p) => p.slug) ?? [];
    filter = "";
    dialog = "pick";
  }
  async function save(parts: string[], consume: boolean) {
    busy = true;
    const { data: next, error } = await api.PUT("/studio/api/world/state/keys/{slug}/recipe", { params: { path }, body: { parts, consume } });
    busy = false;
    if (error || !next) return toast(problem(error), "error");
    data = next;
    dialog = null;
    toast(parts.length ? "Части сохранены." : "Сборка убрана: ключ больше не собирается из частей.");
  }
  async function split() {
    busy = true;
    const { data: next, error } = await api.POST("/studio/api/world/state/keys/{slug}/split", { params: { path }, body: { count, consume: false } });
    busy = false;
    if (error || !next) return toast(problem(error), "error");
    data = next;
    dialog = null;
    toast(`Созданы ${count} ключа-части. Раздайте их игрокам: блоком в файле, исходом письма или ответчика.`);
  }
  const shown = $derived(keys.filter((k) => k.slug !== item.slug && (!filter || k.slug.includes(filter) || k.description.toLowerCase().includes(filter.toLowerCase()))));
  function toggle(slug: string) { picked = picked.includes(slug) ? picked.filter((s) => s !== slug) : [...picked, slug]; }
</script>

<section class="card">
  {#if data}
    {#if data.part_of.length}
      <p class="partof">Этот ключ — часть {#each data.part_of as [slug, n], i}{i ? ", " : ""}<b class="mono">{slug}</b> ({n}){/each}. Сборка настраивается на странице итогового ключа.</p>
    {/if}
    <div class="head">
      <div>
        <h3>Собирается из частей</h3>
        <p class="muted small">Игрок складывает части у себя в секретах командой <code>kjoin &lt;части&gt;</code> и получает этот ключ. Части — обычные ключи: их выдают как любые ключи.</p>
      </div>
      <div class="acts">
        {#if !data.parts.length}<button class="btn" onclick={() => (dialog = "split")}>Разделить на части…</button>{/if}
        <button class="btn ghost" onclick={openPick}>Выбрать части…</button>
      </div>
    </div>

    {#if data.parts.length}
      <ul class="parts">
        {#each data.parts as part, i (part.slug)}
          <li>
            <span class="n mono">{i + 1}</span>
            <span class="slug mono">{part.slug}</span>
            <span class="name muted">{part.name}</span>
            <span class="src">
              {#if part.sources.length}{#each part.sources as [kind, where]}<span class="ok">✓ {kind}: {where}</span>{/each}
              {:else}<span class="warn">⚠ нигде не выдаётся: собрать ключ будет нельзя</span>{/if}
            </span>
          </li>
        {/each}
      </ul>
      <div class="foot">
        <label class="check"><input type="checkbox" checked={data.consume} onchange={(e) => save(data!.parts.map((p) => p.slug), e.currentTarget.checked)} /> Части пропадают после сборки</label>
        <button class="btn ghost small danger" onclick={() => save([], false)}>Убрать сборку</button>
      </div>
    {:else}
      <p class="muted empty">Не собирается: обычный ключ. Разделите его на части, чтобы игроки собирали его сообща.</p>
    {/if}
  {:else}<p class="muted">Загрузка…</p>{/if}
</section>

{#if dialog === "split"}
  <Dialog title="Разделить ключ на части" confirm="Создать части" {busy} disabled={!(count >= 2 && count <= 12)} onsubmit={split} onclose={() => (dialog = null)}>
    <label class="col"><span class="label">Сколько частей</span><input class="field mono" type="number" min="2" max="12" bind:value={count} /></label>
    <p class="muted small">Будут созданы ключи <span class="mono">{item.slug}.1 … {item.slug}.{count || "N"}</span> с именами «fragment 1/{count}» и так далее. Их можно переименовать.</p>
  </Dialog>
{:else if dialog === "pick"}
  <Dialog wide title="Части ключа" confirm="Сохранить" {busy} disabled={picked.length === 1} onsubmit={() => save(picked, data?.consume ?? false)} onclose={() => (dialog = null)}>
    <input class="field" placeholder="Найти ключ" bind:value={filter} />
    <ul class="pick">
      {#each shown as k (k.slug)}
        <li><label class="check"><input type="checkbox" checked={picked.includes(k.slug)} onchange={() => toggle(k.slug)} />
          <span class="mono">{k.slug}</span><span class="muted small">{k.description}</span>{#if picked.includes(k.slug)}<span class="badge">часть {picked.indexOf(k.slug) + 1}</span>{/if}</label></li>
      {/each}
    </ul>
    <p class="muted small">Порядок частей — в порядке выбора. Для сборки порядок не важен, он только для подписи «1 из 3».</p>
  </Dialog>
{/if}

<style>
  .card { margin: 16px 32px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 12px; }
  .head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
  h3 { margin: 0 0 4px; font-size: 15px; }
  .head p { margin: 0; }
  .acts { display: flex; gap: 6px; flex-shrink: 0; }
  .partof { margin: 0; padding: 8px 12px; border-radius: var(--radius-s); background: var(--raise); font-size: 13px; }
  .parts { list-style: none; margin: 0; padding: 0; border: 1px solid var(--line-soft); border-radius: var(--radius); }
  .parts li { display: grid; grid-template-columns: 24px minmax(140px, auto) minmax(0, 1fr) minmax(0, 1.4fr); gap: 12px; align-items: baseline; padding: 8px 12px; border-bottom: 1px solid var(--line-soft); font-size: 13px; }
  .parts li:last-child { border-bottom: 0; }
  .n { color: var(--muted); }
  .src { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
  .ok { color: var(--ok, #4cc38a); }
  .warn { color: var(--warn); }
  .foot { display: flex; justify-content: space-between; align-items: center; }
  .check { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
  .check input { width: auto; }
  .empty { margin: 0; }
  .col { display: flex; flex-direction: column; gap: 4px; }
  .label { font-size: 12px; color: var(--muted); }
  .pick { list-style: none; margin: 8px 0; padding: 0; max-height: 50vh; overflow: auto; display: flex; flex-direction: column; gap: 2px; }
  .pick label { padding: 4px 6px; border-radius: var(--radius-s); cursor: pointer; }
  .pick label:hover { background: var(--raise); }
  .badge { margin-left: auto; padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .small { font-size: 12px; }
  .mono { font-family: var(--mono); }
  code { font-family: var(--mono); font-size: 12px; }
</style>
