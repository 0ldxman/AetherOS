<script lang="ts">
  // Новая машина: с нуля (корень пустой, по шаблону, готовый том) или по образцу другой машины.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { machines, like = null, onclose }: { machines: Schemas["MachineRow"][]; like?: number | null; onclose: () => void } = $props();

  let form = $state({ hostname: "", name: "", system: "AETHER", status: "OFFLINE", root: "template", template: null as number | null,
                      volume: null as number | null, like: null as number | null });
  let systems = $state<Schemas["SystemRow"][]>([]);
  let templates = $state<Schemas["Template"][]>([]);
  let volumes = $state<Schemas["VolumeRow"][]>([]);
  let errors = $state<Record<string, string[]>>({});
  let busy = $state(false);

  onMount(async () => {
    const [s, t, v] = await Promise.all([api.GET("/studio/api/systems"), api.GET("/studio/api/templates"), api.GET("/studio/api/volumes")]);
    systems = s.data ?? [];
    templates = t.data ?? [];
    volumes = v.data ?? [];
    form.template = templates[0]?.id ?? null;
    if (!templates.length) form.root = "empty";
    if (like !== null) Object.assign(form, { root: "like", like });
  });

  const template = $derived(templates.find((item) => item.id === form.template));

  async function submit() {
    busy = true;
    errors = {};
    const { data, error } = await api.POST("/studio/api/machines", { body: form });
    busy = false;
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error, "Машина не создалась."), "error");
    }
    toast("Машина создана.");
    onclose();
    go(`/machines/${data.id}`);
  }
</script>

<Dialog title="Новая машина" confirm="Создать" {busy} onsubmit={submit} {onclose}>
  <div class="pair">
    <label><span class="label">Хост</span><input class="field mono" bind:value={form.hostname} placeholder="gw-07" class:bad={errors.hostname} /></label>
    <label><span class="label">Название</span><input class="field" bind:value={form.name} placeholder="как хост" /></label>
  </div>
  {#if errors.hostname}<p class="err">{errors.hostname.join(" ")}</p>{/if}

  <div class="options">
    <label class="option" class:on={form.root === "template"}>
      <input type="radio" bind:group={form.root} value="template" disabled={!templates.length} />
      <span><b>Свой диск по шаблону</b><small>новый том с папками шаблона файловой структуры</small></span>
    </label>
    <label class="option" class:on={form.root === "volume"}>
      <input type="radio" bind:group={form.root} value="volume" />
      <span><b>Общий образ</b><small>готовый том на корне: его видят все машины, где он смонтирован</small></span>
    </label>
    <label class="option" class:on={form.root === "like"}>
      <input type="radio" bind:group={form.root} value="like" />
      <span><b>По образцу машины</b><small>учётки, группы, пути, экспорты и диски; личные тома копируются</small></span>
    </label>
    <label class="option" class:on={form.root === "empty"}>
      <input type="radio" bind:group={form.root} value="empty" />
      <span><b>Пустая</b><small>корень появится при первой записи</small></span>
    </label>
  </div>

  {#if form.root === "template"}
    <label><span class="label">Шаблон</span>
      <select class="field" bind:value={form.template}>{#each templates as item}<option value={item.id}>{item.name}</option>{/each}</select>
    </label>
    {#if template}<p class="muted small mono">{template.folders.join("  ")}</p>{/if}
  {:else if form.root === "volume"}
    <label><span class="label">Том</span>
      <select class="field" bind:value={form.volume}>
        <option value={null}>—</option>
        {#each volumes as item}<option value={item.id}>{item.name || item.slug} ({item.slug})</option>{/each}
      </select>
    </label>
  {:else if form.root === "like"}
    <label><span class="label">Образец</span>
      <select class="field mono" bind:value={form.like}>
        <option value={null}>—</option>
        {#each machines as item}<option value={item.id}>{item.hostname || item.name}</option>{/each}
      </select>
    </label>
  {/if}

  {#if form.root !== "like"}
    <div class="pair">
      <label><span class="label">Тип системы</span>
        <select class="field" bind:value={form.system}>{#each systems as item}<option value={item.code}>{item.code} — {item.name}</option>{/each}</select>
      </label>
      <label><span class="label">Статус</span>
        <select class="field" bind:value={form.status}><option>OFFLINE</option><option>ONLINE</option><option>MAINTENANCE</option></select>
      </label>
    </div>
  {/if}
</Dialog>

<style>
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .options { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .option { display: flex; gap: 8px; align-items: flex-start; padding: 10px; border: 1px solid var(--line); border-radius: var(--radius-s); cursor: pointer; }
  .option.on { border-color: var(--accent); background: var(--accent-soft); }
  .option b { display: block; font-weight: 600; }
  .option small { color: var(--muted); font-size: 11.5px; line-height: 1.35; }
  .small { font-size: 12px; margin: 0; }
  .field.bad { border-color: var(--danger); }
  .err { margin: -6px 0 0; color: var(--danger); font-size: 12px; }
</style>
