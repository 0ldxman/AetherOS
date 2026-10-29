<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { toast } from "../../lib/toast.svelte";

  type Mount = Schemas["DiskMount"];

  let { machine }: { machine: Schemas["Overview"] } = $props();

  let disks = $state<Schemas["Disks"] | null>(null);
  let editing = $state<null | { id: number | null; mode: string; volume: number | null; volume_path: string; host: number | null;
                                host_path: string; account: number | null; mount_path: string; order: number }>(null);
  let errors = $state<Record<string, string[]>>({});
  let newExport = $state("");
  let viewer = $state<number | null>(null);
  let listing = $state<Schemas["Listing"] | null>(null);

  const path = $derived({ machine_id: machine.id });
  const host = $derived(disks?.hosts.find((item) => item.id === editing?.host));

  onMount(async () => {
    disks = (await api.GET("/studio/api/machines/{machine_id}/disks", { params: { path } })).data ?? null;
    viewer = machine.accounts.find((a) => !a.root)?.id ?? machine.accounts[0]?.id ?? null;
  });

  $effect(() => { if (viewer !== null) open("/"); });

  async function open(target: string) {
    if (viewer === null) return;
    listing = (await api.GET("/studio/api/machines/{machine_id}/tree", { params: { path, query: { account: viewer, path: target } } })).data ?? null;
  }

  function edit(mount: Mount | null) {
    errors = {};
    editing = mount
      ? { id: mount.id, mode: mount.mode, volume: mount.volume?.id ?? null, volume_path: mount.volume_path, host: mount.host?.id ?? null,
          host_path: mount.host_path, account: mount.account?.id ?? null, mount_path: mount.mount_path, order: mount.order }
      : { id: null, mode: "local", volume: null, volume_path: "", host: null, host_path: "", account: null, mount_path: "", order: 0 };
  }

  async function saveMount() {
    if (!editing) return;
    const { id, ...body } = editing;
    const { data, error } = id === null
      ? await api.POST("/studio/api/machines/{machine_id}/mounts", { params: { path }, body })
      : await api.PUT("/studio/api/machines/{machine_id}/mounts/{mount_id}", { params: { path: { ...path, mount_id: id } }, body });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    disks = data;
    editing = null;
    toast("Монтирование сохранено.");
    if (listing) open(listing.path);
  }

  async function dropMount(mount: Mount) {
    const { data } = await api.DELETE("/studio/api/machines/{machine_id}/mounts/{mount_id}", { params: { path: { ...path, mount_id: mount.id } } });
    if (data) disks = data;
  }

  async function addExport() {
    const { data, error } = await api.POST("/studio/api/machines/{machine_id}/exports", { params: { path }, body: { path: newExport } });
    if (error || !data) return toast(problem(error), "error");
    disks = data;
    newExport = "";
  }

  async function dropExport(id: number) {
    const { data } = await api.DELETE("/studio/api/machines/{machine_id}/exports/{export_id}", { params: { path: { ...path, export_id: id } } });
    if (data) disks = data;
  }

  const crumbs = $derived.by(() => {
    const parts = (listing?.path ?? "/").split("/").filter(Boolean);
    return [{ name: "/", path: "/" }, ...parts.map((name, i) => ({ name, path: "/" + parts.slice(0, i + 1).join("/") }))];
  });

  function fieldError(name: string) {
    return errors[name]?.join(" ") ?? "";
  }
</script>

{#if disks}
  <div class="grid">
    <div class="col">
      <section class="card">
        <h2>Монтирования <button class="btn ghost" onclick={() => edit(null)}>+ Подключить</button></h2>
        {#each disks.mounts as mount (mount.id)}
          <div class="mount">
            <span class="point mono">{mount.mount_path || "(без точки)"}</span>
            <span class="arrow">←</span>
            {#if mount.mode === "remote"}
              <span><span class="chip net">сеть</span> <span class="mono">{mount.host?.label}:{mount.host_path}</span>
                <span class="muted">как {mount.account?.label ?? "guest"}</span></span>
            {:else}
              <span><span class="chip">том</span> {mount.volume?.label}{#if mount.volume_path}<span class="mono muted"> /{mount.volume_path}</span>{/if}</span>
            {/if}
            {#if mount.order}<span class="chip">слой {mount.order}</span>{/if}
            <span class="spacer"></span>
            <button class="btn ghost" onclick={() => edit(mount)}>Изменить</button>
            <button class="btn ghost danger" onclick={() => dropMount(mount)}>Отключить</button>
          </div>
        {:else}
          <p class="muted">Ничего не смонтировано: корень появится сам, когда на машину впервые что-то запишут.</p>
        {/each}
      </section>

      <section class="card">
        <h2>Экспорты</h2>
        <p class="muted small">Что эта машина отдаёт по сети: подключиться можно к пути и к тому, что под ним.</p>
        {#each disks.exports as row (row.id)}
          <div class="export"><span class="mono">{row.path}</span><button class="btn ghost danger" onclick={() => dropExport(row.id)}>Убрать</button></div>
        {:else}
          <p class="muted">Ничего не отдаёт.</p>
        {/each}
        <form class="add" onsubmit={(event) => { event.preventDefault(); addExport(); }}>
          <input class="field mono" placeholder="/srv/harbor" bind:value={newExport} />
          <button class="btn" disabled={!newExport.trim()}>Отдавать</button>
        </form>
      </section>
    </div>

    <section class="card eyes">
      <h2>
        Глазами учётки
        <select class="field mono pick" bind:value={viewer}>
          {#each machine.accounts as account}<option value={account.id}>{account.login}{account.root ? " (root)" : ""}</option>{/each}
        </select>
      </h2>
      <nav class="crumbs">
        {#each crumbs as crumb, i}
          {#if i > 1}<span class="sep">/</span>{/if}
          <button onclick={() => open(crumb.path)}>{crumb.name}</button>
        {/each}
      </nav>
      {#if listing && !listing.readable}
        <p class="denied">Permission denied: {listing.denied}. Этой учётке сюда нельзя.</p>
      {:else if listing}
        {#each listing.nodes as node (node.path)}
          <div class="node" class:locked={!node.readable} class:hidden={node.hidden}>
            {#if node.is_dir && node.readable}
              <button class="name" onclick={() => open(node.path)}><span class="ico dir">▣</span>{node.name}</button>
            {:else}
              <span class="name"><span class="ico" class:dir={node.is_dir}>{node.is_dir ? "▣" : "▤"}</span>{node.name}</span>
            {/if}
            <span class="flags">
              {#if node.mount}<span class="chip net">точка</span>{/if}
              {#if node.layers}<span class="chip warnchip" title="Слои защиты">слои</span>{/if}
              {#if node.keys}<span class="chip warnchip" title="Нужны ключи">ключи</span>{/if}
              {#if !node.readable}<span class="chip bad">нет доступа</span>{/if}
            </span>
            <span class="mono muted rights">{node.mode || "open"} {node.owner}{node.group ? `:${node.group}` : ""}</span>
          </div>
        {:else}
          <p class="muted">Пусто.</p>
        {/each}
      {:else}
        <p class="muted">Выберите учётку.</p>
      {/if}
    </section>
  </div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

{#if editing}
  <Dialog title={editing.id === null ? "Подключить диск" : "Изменить монтирование"} confirm="Сохранить" onsubmit={saveMount} onclose={() => (editing = null)}>
    <div class="modes">
      <label class="radio"><input type="radio" bind:group={editing.mode} value="local" /> том</label>
      <label class="radio"><input type="radio" bind:group={editing.mode} value="remote" /> путь другой машины по сети</label>
    </div>
    {#if editing.mode === "local"}
      <label><span class="label">Том</span>
        <select class="field" bind:value={editing.volume}>
          <option value={null}>—</option>
          {#each disks?.volumes ?? [] as volume}<option value={volume.id}>{volume.label}</option>{/each}
        </select>
      </label>
      {#if fieldError("volume")}<p class="err">{fieldError("volume")}</p>{/if}
      <label><span class="label">Папка тома (пусто: весь том)</span><input class="field mono" bind:value={editing.volume_path} /></label>
    {:else}
      <label><span class="label">Хост</span>
        <select class="field" bind:value={editing.host}>
          <option value={null}>—</option>
          {#each disks?.hosts ?? [] as item}<option value={item.id}>{item.label}</option>{/each}
        </select>
      </label>
      {#if fieldError("host")}<p class="err">{fieldError("host")}</p>{/if}
      <label><span class="label">Путь на хосте {host?.exports.length ? `(отдаёт: ${host.exports.join(", ")})` : host ? "(хост ничего не отдаёт)" : ""}</span>
        <input class="field mono" bind:value={editing.host_path} placeholder="/srv/harbor" /></label>
      {#if fieldError("host_path")}<p class="err">{fieldError("host_path")}</p>{/if}
      <label><span class="label">Учётка хоста</span>
        <select class="field mono" bind:value={editing.account}>
          <option value={null}>guest (если есть)</option>
          {#each host?.accounts ?? [] as account}<option value={account.id}>{account.label}</option>{/each}
        </select>
      </label>
    {/if}
    <div class="pair">
      <label><span class="label">Точка монтирования</span><input class="field mono" bind:value={editing.mount_path} placeholder="/mnt/harbor или C:" /></label>
      <label><span class="label">Слой (порядок)</span><input class="field" type="number" min="0" bind:value={editing.order} /></label>
    </div>
    {#if fieldError("mount_path") || fieldError("__all__")}<p class="err">{fieldError("mount_path")} {fieldError("__all__")}</p>{/if}
  </Dialog>
{/if}

<style>
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 20px 24px; align-items: start; }
  .col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .pad { padding: 20px; }
  .card { display: flex; flex-direction: column; gap: 8px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  h2 { display: flex; align-items: center; gap: 10px; margin: 0 0 4px; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h2 .btn { margin-left: auto; text-transform: none; letter-spacing: 0; }
  .pick { margin-left: auto; width: auto; text-transform: none; letter-spacing: 0; }
  .small { font-size: 12px; margin: 0; }
  .mount { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .mount:last-child { border-bottom: 0; }
  .point { font-weight: 600; min-width: 110px; }
  .arrow { color: var(--faint); }
  .spacer { flex: 1; }
  .chip.net { background: var(--accent-soft); color: var(--accent); }
  .chip.warnchip { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  .chip.bad { background: var(--danger-soft); color: var(--danger); }
  .export { display: flex; justify-content: space-between; align-items: center; }
  .add { display: flex; gap: 8px; margin-top: 4px; }
  .crumbs { display: flex; flex-wrap: wrap; gap: 2px; align-items: center; font-family: var(--mono); }
  .crumbs button { border: 0; background: none; cursor: pointer; padding: 2px 4px; border-radius: 4px; }
  .crumbs button:hover { background: var(--panel-2); }
  .sep { color: var(--faint); }
  .denied { margin: 0; padding: 10px 12px; border-radius: var(--radius-s); background: var(--danger-soft); color: var(--danger); font-family: var(--mono); font-size: 12.5px; }
  .node { display: grid; grid-template-columns: 1fr auto 150px; gap: 10px; align-items: center; height: 32px; padding: 0 6px; border-radius: var(--radius-s); }
  .node:hover { background: var(--panel-2); }
  .node.locked .name { color: var(--muted); }
  .node.hidden .name { font-style: italic; }
  .name { display: flex; align-items: center; gap: 8px; border: 0; background: none; padding: 0; text-align: left; cursor: default; }
  button.name { cursor: pointer; }
  button.name:hover { color: var(--accent); }
  .ico { color: var(--faint); font-size: 12px; }
  .ico.dir { color: var(--warn); }
  .flags { display: flex; gap: 4px; }
  .rights { text-align: right; font-size: 12px; }
  .modes { display: flex; gap: 16px; }
  .radio { display: flex; align-items: center; gap: 6px; }
  .pair { display: grid; grid-template-columns: 2fr 1fr; gap: 10px; }
  .err { margin: -6px 0 0; color: var(--danger); font-size: 12px; }
</style>
