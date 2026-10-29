<script lang="ts">
  // Ключи, вложенные в объект (их достаёт kex), подписи (ward verify) и, если сам объект ключ, где его требуют.
  import { onMount } from "svelte";
  import { adminUrl, api, problem, type Schemas } from "../../lib/api";
  import { toast } from "../../lib/toast.svelte";

  let { item }: { item: Schemas["ItemOut"] } = $props();

  let data = $state<Schemas["KeysOut"] | null>(null);
  let embedded = $state<string[]>([]);
  let signatures = $state<{ slug: string; valid: boolean; date: string | null }[]>([]);
  let saved = $state("");
  let pickEmbedded = $state("");
  let pickSigned = $state("");

  const path = $derived({ item_id: item.id });
  const dirty = $derived(JSON.stringify({ embedded, signatures }) !== saved);
  const name = (slug: string) => data?.registry.find((key) => key.slug === slug)?.name ?? slug;

  function fill(next: Schemas["KeysOut"]) {
    data = next;
    embedded = next.embedded.map((key) => key.slug);
    signatures = next.signatures.map((sign) => ({ slug: sign.slug, valid: sign.valid, date: sign.date ?? null }));
    saved = JSON.stringify({ embedded, signatures });
  }

  onMount(async () => {
    const { data: next } = await api.GET("/studio/api/items/{item_id}/keys", { params: { path } });
    if (next) fill(next);
  });

  async function save() {
    const { data: next, error } = await api.PUT("/studio/api/items/{item_id}/keys", { params: { path }, body: { embedded, signatures } });
    if (error || !next) return toast(problem(error), "error");
    fill(next);
    toast("Ключи и подписи сохранены.");
  }

  function addEmbedded() {
    if (pickEmbedded && !embedded.includes(pickEmbedded)) embedded = [...embedded, pickEmbedded];
    pickEmbedded = "";
  }

  function addSignature() {
    if (pickSigned && !signatures.some((sign) => sign.slug === pickSigned)) signatures = [...signatures, { slug: pickSigned, valid: true, date: null }];
    pickSigned = "";
  }
</script>

{#if data}
  <div class="wrap">
    <div class="bar">
      <span class="spacer"></span>
      <span class="muted small">{dirty ? "Не сохранено" : "Сохранено"}</span>
      <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
    </div>

    <div class="cols">
      <section class="card">
        <h2>Вложенные ключи</h2>
        <p class="muted small">Ключи, спрятанные в байтах файла: игрок достаёт их командой <span class="mono">kex</span> и кладёт к себе в секреты.</p>
        {#each embedded as slug}
          <div class="line"><b class="mono">{slug}</b><span class="muted">{name(slug)}</span><button class="btn ghost danger" onclick={() => (embedded = embedded.filter((s) => s !== slug))}>Убрать</button></div>
        {:else}
          <p class="muted">Ничего не вложено.</p>
        {/each}
        <div class="add">
          <select class="field mono" bind:value={pickEmbedded}>
            <option value="">— ключ из реестра —</option>
            {#each data.registry.filter((key) => !embedded.includes(key.slug) && key.slug !== item.slug) as key}<option value={key.slug}>{key.slug} — {key.name}</option>{/each}
          </select>
          <button class="btn" disabled={!pickEmbedded} onclick={addEmbedded}>Вложить</button>
        </div>
      </section>

      <section class="card">
        <h2>Подписи</h2>
        <p class="muted small">Чем подписан файл: <span class="mono">ward verify</span> сверит подпись. Снимите «сходится», чтобы подпись оказалась подделкой.</p>
        {#each signatures as sign (sign.slug)}
          <div class="line sig">
            <b class="mono">{sign.slug}</b>
            <label class="check"><input type="checkbox" bind:checked={sign.valid} /> сходится</label>
            <input class="field date" type="date" bind:value={sign.date} title="Дата подписи в мире (необязательно)" />
            <button class="btn ghost danger" onclick={() => (signatures = signatures.filter((s) => s.slug !== sign.slug))}>Убрать</button>
          </div>
        {:else}
          <p class="muted">Подписей нет.</p>
        {/each}
        <div class="add">
          <select class="field mono" bind:value={pickSigned}>
            <option value="">— ключ из реестра —</option>
            {#each data.registry.filter((key) => !signatures.some((s) => s.slug === key.slug)) as key}<option value={key.slug}>{key.slug} — {key.name}</option>{/each}
          </select>
          <button class="btn" disabled={!pickSigned} onclick={addSignature}>Подписать</button>
        </div>
      </section>
    </div>

    {#if data.is_key}
      <section class="card">
        <h2>Где этот ключ требуется</h2>
        {#each data.required_by as use}
          <div class="line"><span class="chip">{use.kind}</span> <a href={use.url.startsWith("/") ? use.url : adminUrl(use.url)}>{use.label}</a></div>
        {:else}
          <p class="muted">Нигде: ключ никому не нужен. Ключ, который нигде не требуется, игрок найдёт, но он ничего не откроет.</p>
        {/each}
      </section>
    {/if}
  </div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding: 12px 20px 24px; max-width: 1100px; }
  .pad { padding: 20px; }
  .bar { display: flex; align-items: center; gap: 10px; }
  .spacer { flex: 1; }
  .small { font-size: 12px; margin: 0; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start; }
  .card { display: flex; flex-direction: column; gap: 8px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  h2 { margin: 0; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .line { display: flex; align-items: center; gap: 12px; padding: 3px 0; }
  .line .btn { margin-left: auto; }
  .sig { display: grid; grid-template-columns: 1fr auto 150px auto; }
  .check { display: flex; align-items: center; gap: 6px; color: var(--muted); }
  .date { width: 150px; }
  .add { display: flex; gap: 8px; margin-top: 4px; }
</style>
