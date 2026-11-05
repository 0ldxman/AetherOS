<script lang="ts">
  // Своя защита одного места объекта: условие и слои раздельно, у каждого режим «как у объекта», «заменить» или «нет».
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import Dialog from "../../lib/Dialog.svelte";
  import LayerBuilder from "../../lib/LayerBuilder.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { itemId, placed, onclose, onsaved }: { itemId: number; placed: Schemas["Placed"]; onclose: () => void; onsaved: () => void } = $props();

  let form = $state<Schemas["PlacementProtection"] | null>(null);
  let errors = $state<Record<string, string[]>>({});
  let busy = $state(false);
  const path = $derived({ item_id: itemId, placement_id: placed.placement });

  onMount(async () => {
    form = (await api.GET("/studio/api/items/{item_id}/placements/{placement_id}/protection", { params: { path } })).data ?? null;
  });

  async function save() {
    if (!form) return;
    busy = true;
    const { error } = await api.PUT("/studio/api/items/{item_id}/placements/{placement_id}/protection", { params: { path }, body: $state.snapshot(form) });
    busy = false;
    if (error) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error), "error");
    }
    toast("Защита места сохранена.");
    onsaved();
    onclose();
  }
</script>

<Dialog title="Защита места {placed.volume_name}:/{placed.path}" confirm="Сохранить" wide {busy} disabled={!form} onsubmit={save} {onclose}>
  {#if form}
    <p class="muted small">По умолчанию место защищено так же, как объект. Здесь можно задать только для этого места своё условие или свои слои, либо снять защиту объекта.</p>

    <section>
      <h3>Условие доступа</h3>
      <select class="field" bind:value={form.access_mode}>
        <option value="inherit">как у объекта</option>
        <option value="replace">своё условие</option>
        <option value="none">нет: открыто всем</option>
      </select>
      {#if form.access_mode === "replace"}
        <AccessBuilder bind:value={form.access} bad={!!errors.access} />
        {#if errors.access}<p class="err">{errors.access.join(" ")}</p>{/if}
      {/if}
    </section>

    <section>
      <h3>Слои защиты</h3>
      <select class="field" bind:value={form.state_mode}>
        <option value="inherit">как у объекта</option>
        <option value="replace">свои слои</option>
        <option value="none">нет: без слоёв</option>
      </select>
      {#if form.state_mode === "replace"}
        <LayerBuilder bind:value={form.state} />
        {#if errors.state}<ul class="err">{#each errors.state as message}<li>{message}</li>{/each}</ul>{/if}
      {/if}
    </section>
    {#if errors.__all__}<p class="err">{errors.__all__.join(" ")}</p>{/if}
  {:else}
    <p class="muted">Загрузка…</p>
  {/if}
</Dialog>

<style>
  section { display: flex; flex-direction: column; gap: 8px; }
  h3 { margin: 4px 0 0; font-size: 13px; }
  p { margin: 0; }
  .err { margin: 0; padding-left: 16px; color: var(--danger); font-size: 12px; }
  p.err { padding-left: 0; }
</style>
