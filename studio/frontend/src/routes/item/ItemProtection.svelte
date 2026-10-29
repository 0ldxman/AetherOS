<script lang="ts">
  // Защита объекта: условие по ключам и слои. Справа сразу видно, что игрок получит в blk и txtx со слоями и без них.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import CodeEditor from "../../lib/CodeEditor.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { item, onsaved }: { item: Schemas["ItemOut"]; onsaved: () => void } = $props();

  let saved = $state<Schemas["ProtectionOut"] | null>(null);
  let form = $state({ access: "", state: "" });
  let preview = $state<Schemas["Preview"] | null>(null);
  let errors = $state<Record<string, string[]>>({});
  let conflict = $state<string | null>(null);
  let both = $state(true);

  const path = $derived({ item_id: item.id });
  const dirty = $derived(saved !== null && (form.access !== saved.access || form.state !== saved.state));

  async function load() {
    const { data } = await api.GET("/studio/api/items/{item_id}/protection", { params: { path } });
    if (!data) return;
    saved = data;
    form = { access: data.access, state: data.state };
  }
  onMount(load);

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const body = { access: form.access, state: form.state };
    clearTimeout(timer);
    timer = setTimeout(async () => {
      preview = (await api.POST("/studio/api/items/{item_id}/protection/preview", { params: { path }, body })).data ?? null;
    }, 300);
  });

  async function save(force = false) {
    if (!saved) return;
    errors = {};
    const { data, error, response } = await api.PUT("/studio/api/items/{item_id}/protection", {
      params: { path }, body: { ...form, version: saved.version, force },
    });
    if (response.status === 409) {
      conflict = (error as unknown as { by?: string | null })?.by ?? "кто-то";
      return;
    }
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    conflict = null;
    saved = data;
    toast("Защита сохранена.");
    onsaved();
  }

  const PARAMS = (layer: Schemas["Layer"]) => Object.entries(layer.params).map(([key, value]) => `${key}=${value}`).join(" ");
</script>

<div class="wrap">
  <div class="bar">
    {#if conflict}
      <span class="warn">Объект уже сохранил {conflict}.</span>
      <button class="btn danger" onclick={() => save(true)}>Сохранить моё поверх</button>
    {/if}
    <span class="spacer"></span>
    <span class="muted small">{dirty ? "Не сохранено" : "Сохранено"}</span>
    <button class="btn primary" disabled={!dirty} onclick={() => save()}>Сохранить защиту</button>
  </div>

  <div class="cols">
    <div class="col">
      <section class="card">
        <h2>Условие доступа</h2>
        <p class="muted small">Что должно лежать у игрока в секретах, чтобы он получил содержимое: <span class="mono">cardkey and (door or not alarm)</span>. Пусто: открыто.</p>
        <input class="field mono" bind:value={form.access} class:bad={errors.access || preview?.access_error} placeholder="открыто всем" />
        {#if preview?.access_error}<p class="err">{preview.access_error}</p>{:else if errors.access}<p class="err">{errors.access.join(" ")}</p>{/if}
        {#if preview?.keys.length}
          <div class="chips">
            {#each preview.keys as slug}
              <span class="chip" class:bad={preview.unknown_keys.includes(slug)} title={preview.unknown_keys.includes(slug) ? "Такого ключа нет в реестре" : ""}>
                {slug}{preview.unknown_keys.includes(slug) ? " — нет в реестре" : ""}
              </span>
            {/each}
          </div>
        {/if}
      </section>

      <section class="card grow">
        <h2>Слои защиты</h2>
        <p class="muted small">Что игроку надо пройти (подобрать пароль, снять маскировку, подобрать смещение). Строка — слой, верхний слой первым:
          <span class="mono">&gt; encrypted hunter2 attempts=3</span></p>
        <div class="editor"><CodeEditor bind:value={form.state} /></div>
        {#if preview?.problems.length}
          <ul class="problems">{#each preview.problems as bad}<li><span class="mono">стр. {bad.line}</span> {bad.message}</li>{/each}</ul>
        {:else if errors.state}
          <ul class="problems">{#each errors.state as message}<li>{message}</li>{/each}</ul>
        {:else if preview?.layers.length}
          <ol class="layers">
            {#each preview.layers as layer}<li><b class="mono">{layer.name}</b> <span class="muted mono">{PARAMS(layer)}</span></li>{/each}
          </ol>
        {/if}
      </section>
    </div>

    <section class="card bytes">
      <h2>Что получит игрок</h2>
      <p class="muted small">Первые байты файла, как их увидит <span class="mono">blk</span> и <span class="mono">txtx</span>.</p>
      {#snippet dump(title: string, data: Schemas["Dump"] | null | undefined, note: string)}
        <h3>{title}</h3>
        {#if data}
          <p class="muted small">{data.size} байт · формат {data.format ?? "—"} · читаемых {data.printable}% {note}</p>
          <div class="hex">
            {#each data.rows as row}
              <div class="hrow"><span class="off">{row.offset}</span><span class="hx">{row.hex}</span><span class="asc">{row.ascii}</span></div>
            {/each}
          </div>
        {:else}
          <p class="muted small">Нет данных.</p>
        {/if}
      {/snippet}
      {@render dump("Без слоёв", preview?.plain, "")}
      {#if preview?.layered}{@render dump("Со слоями из редактора", preview.layered, "")}{:else}<p class="muted small">Добавьте слой, чтобы увидеть разницу.</p>{/if}
    </section>
  </div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding: 12px 20px 24px; min-height: 0; flex: 1; }
  .bar { display: flex; align-items: center; gap: 10px; }
  .spacer { flex: 1; }
  .warn { color: var(--warn); }
  .small { font-size: 12px; margin: 0; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; min-height: 0; flex: 1; align-items: start; }
  .col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .card { display: flex; flex-direction: column; gap: 8px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  h2 { margin: 0; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3 { margin: 6px 0 0; font-size: 13px; }
  .editor { height: 190px; border: 1px solid var(--line); border-radius: var(--radius-s); overflow: hidden; }
  .field.bad { border-color: var(--danger); }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip.bad { background: var(--danger-soft); color: var(--danger); }
  .problems { margin: 0; padding: 8px 12px; list-style: none; border-radius: var(--radius-s); background: var(--danger-soft); color: var(--danger); font-size: 12.5px; }
  .layers { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 2px; }
  .hex { font: 12px/1.7 var(--mono); background: var(--bg); border-radius: var(--radius-s); padding: 8px 10px; overflow-x: auto; }
  .hrow { display: grid; grid-template-columns: 40px 1fr 140px; gap: 12px; white-space: pre; }
  .off { color: var(--faint); }
  .hx { color: var(--text); }
  .asc { color: var(--muted); }
</style>
