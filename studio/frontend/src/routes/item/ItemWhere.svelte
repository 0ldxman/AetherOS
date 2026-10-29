<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { item }: { item: Schemas["ItemOut"] } = $props();

  let data = $state<Schemas["Whereabouts"] | null>(null);
  let dialog = $state<null | "put" | "delete">(null);
  let detaching = $state<Schemas["Placed"] | null>(null);
  let volumes = $state<Schemas["VolumeRow"][]>([]);
  let target = $state({ volume: null as number | null, parent: null as number | null, name: "" });
  let folders = $state<{ id: number; path: string }[]>([]);

  const path = $derived({ item_id: item.id });

  async function load() {
    data = (await api.GET("/studio/api/items/{item_id}/where", { params: { path } })).data ?? null;
  }
  onMount(load);

  async function openPut() {
    volumes = (await api.GET("/studio/api/volumes")).data ?? [];
    target = { volume: null, parent: null, name: "" };
    folders = [];
    dialog = "put";
  }

  $effect(() => {
    const volume = target.volume;
    folders = [];
    if (volume === null) return;
    api.GET("/studio/api/volumes/{volume_id}", { params: { path: { volume_id: volume } } }).then(({ data: tree }) => {
      if (!tree) return;
      const byId = new Map(tree.rows.map((row) => [row.id, row]));
      const full = (id: number | null): string => {
        const row = id === null ? undefined : byId.get(id);
        return row ? `${full(row.parent)}/${row.name}` : "";
      };
      folders = tree.rows.filter((row) => row.kind === "folder").map((row) => ({ id: row.id, path: full(row.id) })).sort((a, b) => a.path.localeCompare(b.path));
    });
  });

  async function put() {
    if (target.volume === null) return;
    const { data: next, error } = await api.POST("/studio/api/items/{item_id}/placements", {
      params: { path }, body: { volume: target.volume, parent: target.parent, name: target.name },
    });
    if (error || !next) return toast(problem(error), "error");
    data = next;
    dialog = null;
    toast("Объект положен ещё в одно место.");
  }

  async function detach(placed: Schemas["Placed"]) {
    const { data: made, error } = await api.POST("/studio/api/items/{item_id}/detach", { params: { path }, body: { placement: placed.placement } });
    detaching = null;
    if (error || !made) return toast(problem(error), "error");
    toast("У этого места теперь своя копия.");
    go(`/items/${(made as { id: number }).id}/where`);
  }

  let toText = $state<null | { placement: Schemas["Placed"]; reasons: string[] }>(null);

  async function askText(placed: Schemas["Placed"]) {
    const { data: found } = await api.GET("/studio/api/items/{item_id}/text-blockers", { params: { path } });
    toText = { placement: placed, reasons: found?.reasons ?? [] };
  }

  async function makeText() {
    if (!toText) return;
    const { data: made, error } = await api.POST("/studio/api/items/{item_id}/to-text", { params: { path }, body: { placement: toText.placement.placement } });
    toText = null;
    if (error || !made) return toast(problem(error), "error");
    toast("Теперь это свой текст места, объекта больше нет.");
    go(`/volumes/${made.volume}/text/${made.placement}`);
  }

  async function remove() {
    const { error } = await api.DELETE("/studio/api/items/{item_id}", { params: { path } });
    dialog = null;
    if (error) return toast(problem(error), "error");
    toast("Объект удалён.");
    go("/items");
  }
</script>

{#if data}
  <div class="wrap">
    <section class="card">
      <h2>В томах <button class="btn ghost" onclick={openPut}>+ Положить ещё в…</button></h2>
      {#each data.placements as placed (placed.placement)}
        <div class="place">
          <a class="mono path" href="#/volumes/{placed.volume}{placed.parent ? `/${placed.parent}` : ''}">
            {placed.volume_name}:/{placed.path}{#if placed.volume_name !== placed.volume_slug}<span class="muted"> · {placed.volume_slug}</span>{/if}
          </a>
          <span class="mono muted">{placed.mode || "open"}{placed.owner ? ` ${placed.owner}` : ""}{placed.group ? `:${placed.group}` : ""}</span>
          <span class="flags">
            {#if placed.hidden}<span class="chip">скрыт</span>{/if}
            {#if placed.own_access}<span class="chip warnchip" title="Условие доступа этого места заменяет объектное">своё условие</span>{/if}
            {#if placed.own_state}<span class="chip warnchip" title="Слои этого места заменяют объектные">свои слои</span>{/if}
          </span>
          {#if data.placements.length > 1}
            <button class="btn ghost" onclick={() => (detaching = placed)}>Своя копия здесь</button>
          {:else}
            <button class="btn ghost" onclick={() => askText(placed)}>Сделать своим текстом</button>
          {/if}
        </div>
      {:else}
        <p class="muted">Объект не лежит ни в одном томе.</p>
      {/each}
      {#if data.placements.length > 1}
        <p class="muted small">Это один объект: правка текста, слоёв или ключей видна во всех {data.placements.length} местах.</p>
      {/if}
    </section>

    {#if data.archives.length || data.members.length}
      <section class="card">
        {#if data.archives.length}
          <h2>Входит в архивы</h2>
          {#each data.archives as row}<div class="line"><a href="#/items/{row.archive}/where">{row.name}</a> <span class="mono muted">→ {row.path}</span></div>{/each}
        {/if}
        {#if data.members.length}
          <h2>Содержимое архива</h2>
          {#each data.members as row}<div class="line"><span class="mono">{row.path}</span> <a href="#/items/{row.archive}">{row.name}</a></div>{/each}
        {/if}
      </section>
    {/if}

    {#if data.mentions.length}
      <section class="card">
        <h2>Ссылаются</h2>
        {#each data.mentions as row}<div class="line"><span class="chip">{row.kind}</span> {row.label}</div>{/each}
      </section>
    {/if}

    <section class="card">
      <h2>У игроков</h2>
      {#if data.players.copies}
        <p class="line">{data.players.copies} файлов игроков ссылаются на объект{data.players.edits ? `, в ${data.players.edits} игрок правил текст` : ""}.
          <span class="muted">{data.players.users.join(", ")}</span></p>
        <p class="muted small">Их копии и перенесённые файлы видят правку объекта; правленный игроком текст остаётся его.</p>
      {:else}
        <p class="muted">Ни у кого из игроков нет своих копий.</p>
      {/if}
    </section>

    <div class="danger-zone">
      <button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить объект</button>
    </div>
  </div>
{:else}
  <p class="muted wrap">Загрузка…</p>
{/if}

{#if dialog === "put"}
  <Dialog title="Положить «{item.name}» ещё в…" confirm="Положить" onsubmit={put} onclose={() => (dialog = null)}>
    <p class="muted small">Это тот же объект, не копия: правка будет видна в обоих местах.</p>
    <label><span class="label">Том</span>
      <select class="field" bind:value={target.volume}>
        <option value={null}>—</option>
        {#each volumes as volume}<option value={volume.id}>{volume.name || volume.slug}</option>{/each}
      </select>
    </label>
    <label><span class="label">Папка</span>
      <select class="field mono" bind:value={target.parent} disabled={target.volume === null}>
        <option value={null}>/ (корень тома)</option>
        {#each folders as folder}<option value={folder.id}>{folder.path}</option>{/each}
      </select>
    </label>
    <label><span class="label">Имя в этом месте (пусто: как у объекта)</span><input class="field mono" bind:value={target.name} /></label>
  </Dialog>
{:else if dialog === "delete" && data}
  <Dialog title="Удалить «{item.name}»?" confirm="Удалить" danger onsubmit={remove} onclose={() => (dialog = null)}>
    {#if data.holders.length}
      <p>Удалить нельзя: объект нужен.</p>
      {#each data.holders as row}<p class="line"><span class="chip">{row.kind}</span> {row.label}</p>{/each}
    {:else}
      <p class="muted">Пропадёт из {data.placements.length} мест в томах{data.mentions.length ? `, из ${data.mentions.length} писем и ресурсов` : ""}{data.players.copies ? `, у игроков пропадут ${data.players.copies} файлов` : ""}. История версий удалится вместе с ним.</p>
    {/if}
  </Dialog>
{:else if toText}
  <Dialog title="Сделать своим текстом места?" confirm="Превратить" danger onsubmit={makeText} onclose={() => (toText = null)}>
    {#if toText.reasons.length}
      <p>Нельзя: объект нужен как объект.</p>
      {#each toText.reasons as reason}<p class="line">{reason}</p>{/each}
    {:else}
      <p class="mono">{toText.placement.volume_name}:/{toText.placement.path}</p>
      <p class="muted">Текст, условие и слои переедут в само место, объект и его история удалятся. Вернуть можно кнопкой «Сделать объектом».</p>
    {/if}
  </Dialog>
{:else if detaching}
  {@const place = detaching}
  <Dialog title="Своя копия для этого места?" confirm="Сделать копию" onsubmit={() => detach(place)} onclose={() => (detaching = null)}>
    <p class="mono">{place.volume_name}:/{place.path}</p>
    <p class="muted">Здесь будет лежать новый объект с тем же содержимым, ключами и подписями. Дальше правки этого места и остальных
      {data ? data.placements.length - 1 : ""} не будут влиять друг на друга.</p>
  </Dialog>
{/if}

<style>
  .wrap { display: flex; flex-direction: column; gap: 14px; padding: 16px 20px 24px; max-width: 980px; }
  .card { display: flex; flex-direction: column; gap: 6px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  h2 { display: flex; align-items: center; margin: 0 0 6px; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h2:not(:first-child) { margin-top: 10px; }
  h2 .btn { margin-left: auto; text-transform: none; letter-spacing: 0; }
  .place { display: grid; grid-template-columns: 1fr 160px auto auto; gap: 12px; align-items: center; padding: 5px 0; border-bottom: 1px solid var(--line-soft); }
  .place:last-of-type { border-bottom: 0; }
  .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .flags { display: flex; gap: 4px; }
  .chip.warnchip { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  .line { margin: 0; display: flex; gap: 8px; align-items: baseline; }
  .small { font-size: 12px; margin: 0; }
  .danger-zone { padding-top: 4px; }
</style>
