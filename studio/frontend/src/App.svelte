<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "./lib/api";
  import { match, route } from "./lib/router.svelte";
  import { toasts } from "./lib/toast.svelte";
  import Volumes from "./routes/Volumes.svelte";
  import Volume from "./routes/Volume.svelte";
  import Item from "./routes/Item.svelte";

  let user = $state("");

  onMount(async () => {
    const { data } = await api.GET("/studio/api/me");
    user = data?.username ?? "";
  });

  type Page = { name: "volumes" } | { name: "volume"; id: number; folder: number | null } | { name: "item"; id: number };

  const page: Page = $derived.by((): Page => {
    let found;
    if ((found = match("/volumes/:id/:folder", route.path))) return { name: "volume", id: +found.id, folder: +found.folder || null };
    if ((found = match("/volumes/:id", route.path))) return { name: "volume", id: +found.id, folder: null };
    if ((found = match("/items/:id", route.path))) return { name: "item", id: +found.id };
    return { name: "volumes" };
  });

  const NAV = [
    { href: "#/volumes", label: "Тома и файлы", section: ["volumes", "volume", "item"] },
  ];
</script>

<div class="shell">
  <aside class="side">
    <div class="brand">
      <span class="mark">◆</span>
      <span>Студия</span>
    </div>
    <nav>
      {#each NAV as item}
        <a class="nav" class:on={item.section.includes(page.name)} href={item.href}>{item.label}</a>
      {/each}
      <span class="nav soon">Машины</span>
      <span class="nav soon">Карта</span>
      <span class="nav soon">Почта</span>
    </nav>
    <div class="foot">
      <a href={window.STUDIO.admin}>Старая админка</a>
      <a href={window.STUDIO.site}>Игра</a>
      {#if user}<span class="muted">{user}</span>{/if}
    </div>
  </aside>

  <main class="main">
    {#if page.name === "volume"}
      {#key page.id}<Volume id={page.id} folder={page.folder} />{/key}
    {:else if page.name === "item"}
      {#key page.id}<Item id={page.id} />{/key}
    {:else}
      <Volumes />
    {/if}
  </main>
</div>

<div class="toasts" aria-live="polite">
  {#each toasts as item (item.id)}
    <div class="toast" class:error={item.kind === "error"}>{item.text}</div>
  {/each}
</div>

<style>
  .shell { display: grid; grid-template-columns: 220px 1fr; height: 100%; }
  .side {
    display: flex; flex-direction: column; gap: 18px;
    padding: 16px 12px; border-right: 1px solid var(--line-soft); background: var(--panel);
  }
  .brand { display: flex; align-items: center; gap: 8px; padding: 0 8px; font-weight: 650; letter-spacing: 0.2px; }
  .mark { color: var(--accent); }
  nav { display: flex; flex-direction: column; gap: 2px; }
  .nav { padding: 6px 10px; border-radius: var(--radius-s); color: var(--muted); }
  .nav:hover { background: var(--panel-2); color: var(--text); text-decoration: none; }
  .nav.on { background: var(--accent-soft); color: var(--text); }
  .nav.soon { color: var(--faint); cursor: default; }
  .nav.soon::after { content: " · скоро"; font-size: 11px; }
  .foot { margin-top: auto; display: flex; flex-direction: column; gap: 4px; padding: 0 10px; font-size: 12.5px; }
  .main { min-width: 0; overflow: auto; }
  .toasts { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 8px; z-index: 50; }
  .toast {
    padding: 9px 14px; border-radius: var(--radius); background: var(--raise); border: 1px solid var(--line);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); max-width: 420px;
  }
  .toast.error { border-color: rgba(255, 122, 122, 0.4); color: var(--danger); }
</style>
