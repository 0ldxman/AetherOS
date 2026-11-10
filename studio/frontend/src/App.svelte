<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "./lib/api";
  import { match, route } from "./lib/router.svelte";
  import ConfirmHost from "./lib/ConfirmHost.svelte";
  import { dismiss, toasts } from "./lib/toast.svelte";
  import Volumes from "./routes/Volumes.svelte";
  import Volume from "./routes/Volume.svelte";
  import TextFile from "./routes/TextFile.svelte";
  import Item from "./routes/Item.svelte";
  import Items from "./routes/Items.svelte";
  import Machines from "./routes/Machines.svelte";
  import Machine from "./routes/Machine.svelte";
  import Policies from "./routes/Policies.svelte";
  import Systems from "./routes/Systems.svelte";
  import World from "./routes/World.svelte";
  import Scenes from "./routes/Scenes.svelte";
  import Formats from "./routes/Formats.svelte";
  import Encodings from "./routes/Encodings.svelte";
  import Team from "./routes/Team.svelte";
  import Dashboard from "./routes/Dashboard.svelte";
  import { level, loadMe, me } from "./lib/me.svelte";

  const user = $derived(me.data?.username ?? "");

  onMount(loadMe);

  type Page =
    | { name: "volumes" }
    | { name: "volume"; id: number; folder: number | null }
    | { name: "text"; volume: number; id: number }
    | { name: "item"; id: number; view: string }
    | { name: "items" }
    | { name: "machines" }
    | { name: "machine"; id: number; tab: string; sub: number | null }
    | { name: "policies"; id: number | null }
    | { name: "systems"; code: string | null; tab: string }
    | { name: "world" }
    | { name: "formats"; id: string | null }
    | { name: "encodings"; id: string | null }
    | { name: "map"; tab: string; id: number | null }
    | { name: "scenes"; slug: string | null }
    | { name: "team"; role: number | null }
    | { name: "home" };

  const page: Page = $derived.by((): Page => {
    let found;
    if ((found = match("/volumes/:id/text/:pid", route.path))) return { name: "text", volume: +found.id, id: +found.pid };
    if ((found = match("/volumes/:id/:folder", route.path))) return { name: "volume", id: +found.id, folder: +found.folder || null };
    if ((found = match("/volumes/:id", route.path))) return { name: "volume", id: +found.id, folder: null };
    if ((found = match("/items/:id/:view", route.path))) return { name: "item", id: +found.id, view: found.view };
    if ((found = match("/items/:id", route.path))) return { name: "item", id: +found.id, view: "content" };
    if (match("/items", route.path)) return { name: "items" };
    if ((found = match("/machines/:id/:tab/:sub", route.path))) return { name: "machine", id: +found.id, tab: found.tab, sub: +found.sub || null };
    if ((found = match("/machines/:id/:tab", route.path))) return { name: "machine", id: +found.id, tab: found.tab, sub: null };
    if ((found = match("/machines/:id", route.path))) return { name: "machine", id: +found.id, tab: "overview", sub: null };
    if (match("/machines", route.path)) return { name: "machines" };
    if ((found = match("/policies/:id", route.path))) return { name: "policies", id: +found.id };
    if (match("/policies", route.path)) return { name: "policies", id: null };
    if (match("/world", route.path)) return { name: "world" };
    if ((found = match("/formats/:id", route.path))) return { name: "formats", id: decodeURIComponent(found.id) };
    if (match("/formats", route.path)) return { name: "formats", id: null };
    if ((found = match("/encodings/:id", route.path))) return { name: "encodings", id: decodeURIComponent(found.id) };
    if (match("/encodings", route.path)) return { name: "encodings", id: null };
    if ((found = match("/map/:tab/:id", route.path))) return { name: "map", tab: found.tab, id: +found.id || null };
    if ((found = match("/map/:tab", route.path))) return { name: "map", tab: found.tab, id: null };
    if (match("/map", route.path)) return { name: "map", tab: "territory", id: null };
    if (match("/home", route.path)) return { name: "home" };
    if (match("/volumes", route.path)) return { name: "volumes" };
    if ((found = match("/team/roles/:id", route.path))) return { name: "team", role: +found.id };
    if (match("/team", route.path)) return { name: "team", role: null };
    if ((found = match("/scenes/:slug", route.path))) return { name: "scenes", slug: found.slug };
    if (match("/scenes", route.path)) return { name: "scenes", slug: null };
    if ((found = match("/systems/:code/:tab", route.path))) return { name: "systems", code: found.code, tab: found.tab };
    if ((found = match("/systems/:code", route.path))) return { name: "systems", code: found.code, tab: "overview" };
    if (match("/systems", route.path)) return { name: "systems", code: null, tab: "overview" };
    return { name: "home" };
  });

  const NAV = [
    { href: "#/home", label: "Главная", section: ["home"], right: "" },
    { href: "#/volumes", label: "Диски и файлы", section: ["volumes", "volume", "text"], right: "disks" },
    { href: "#/items", label: "Объекты", section: ["items", "item"], right: "items" },
    { href: "#/machines", label: "Машины", section: ["machines", "machine"], right: "machines" },
    { href: "#/formats", label: "Форматы", section: ["formats", "encodings"], right: "formats" },
    { href: "#/policies", label: "Политики входа", section: ["policies"], right: "policies" },
    { href: "#/systems", label: "Операционные системы", section: ["systems"], right: "systems" },
    { href: "#/scenes", label: "Сцены", section: ["scenes"], right: "scenes" },
    { href: "#/world", label: "Мир", section: ["world"], right: "world" },
    { href: "#/map", label: "Карта", section: ["map"], right: "map" },
  ];

  const current = $derived(NAV.find((item) => item.section.includes(page.name)) ?? null);

  let toastBox: HTMLElement;
  $effect(() => {
    if (!toasts.length) return;
    try { toastBox.hidePopover(); } catch {}
    try { toastBox.showPopover(); } catch {}
  });
</script>

<div class="shell">
  <aside class="side">
    <div class="brand">
      <span class="mark">◆</span>
      <span>Студия</span>
    </div>
    <nav>
      {#each NAV as item}
        {#if level(item.right) === "none"}
          <span class="nav off" title="Нет прав на этот раздел">{item.label}</span>
        {:else}
          <a class="nav" class:on={item.section.includes(page.name)} href={item.href}>{item.label}</a>
        {/if}
      {/each}
      <span class="nav soon">Почта</span>
      <a class="nav team" class:on={page.name === "team"} href="#/team">Команда</a>
    </nav>
    <div class="foot">
      <a href={window.STUDIO.admin}>Старая админка</a>
      <a href={window.STUDIO.site}>Игра</a>
      {#if user}<span class="muted">{user}</span>{/if}
    </div>
  </aside>

  <main class="main">
    {#if current && level(current.right) === "read"}
      <div class="readonly" role="status">Только просмотр: у вашей роли нет права править раздел «{current.label}».</div>
    {/if}
    {#if current && level(current.right) === "none"}
      <p class="muted" style="padding: 20px">У вашей роли нет доступа к разделу «{current.label}».</p>
    {:else if page.name === "home"}
      <Dashboard />
    {:else if page.name === "team"}
      <Team role={page.role} />
    {:else if page.name === "volume"}
      {#key page.id}<Volume id={page.id} folder={page.folder} />{/key}
    {:else if page.name === "text"}
      {#key page.id}<TextFile volume={page.volume} id={page.id} />{/key}
    {:else if page.name === "item"}
      {#key page.id}<Item id={page.id} view={page.view} />{/key}
    {:else if page.name === "items"}
      <Items />
    {:else if page.name === "scenes"}
      {#key page.slug}<Scenes slug={page.slug} />{/key}
    {:else if page.name === "world"}
      <World />
    {:else if page.name === "formats"}
      <Formats name={page.id} />
    {:else if page.name === "encodings"}
      <Encodings name={page.id} />
    {:else if page.name === "map"}
      {#await import("./routes/Map.svelte")}
        <p class="muted" style="padding: 20px">Загрузка карты…</p>
      {:then loaded}
        <loaded.default tab={page.tab} id={page.id} />
      {:catch}
        <p class="muted" style="padding: 20px">Карта не загрузилась. Обновите страницу.</p>
      {/await}
    {:else if page.name === "systems"}
      {#key page.code}<Systems code={page.code} tab={page.tab} />{/key}
    {:else if page.name === "policies"}
      <Policies id={page.id} />
    {:else if page.name === "machines"}
      <Machines />
    {:else if page.name === "machine"}
      {#key page.id}<Machine id={page.id} tab={page.tab} sub={page.sub} />{/key}
    {:else}
      <Volumes />
    {/if}
  </main>
</div>

<ConfirmHost />

<div class="toasts" popover="manual" bind:this={toastBox} aria-live="polite">
  {#each toasts as item (item.id)}
    <div class="toast" class:error={item.kind === "error"}>
      <span>{item.text}</span>
      {#if item.action}<button class="toast-action" onclick={() => { const act = item.action; dismiss(item.id); act?.run(); }}>{item.action.label}</button>{/if}
    </div>
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
  .nav.off { color: var(--faint); cursor: not-allowed; }
  .nav.team { margin-top: 10px; }
  .readonly { padding: 6px 32px; background: var(--accent-soft); color: var(--muted); font-size: 12.5px; border-bottom: 1px solid var(--line-soft); }
  .nav.soon::after { content: " · скоро"; font-size: 11px; }
  .foot { margin-top: auto; display: flex; flex-direction: column; gap: 4px; padding: 0 10px; font-size: 12.5px; }
  .main { min-width: 0; overflow: auto; }
  .toasts { position: fixed; inset: auto 16px 16px auto; margin: 0; padding: 0; border: 0; background: none; overflow: visible; width: max-content; display: flex; flex-direction: column; gap: 8px; z-index: 50; }
  .toasts:not(:popover-open) { display: none; }
  .toast {
    padding: 9px 14px; border-radius: var(--radius); background: var(--raise); border: 1px solid var(--line);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); max-width: 420px;
  }
  .toast { display: flex; align-items: center; gap: 14px; }
  .toast-action { padding: 2px 10px; border: 1px solid var(--accent); border-radius: var(--radius-s); background: none; color: var(--accent); cursor: pointer; font-weight: 600; }
  .toast-action:hover { background: var(--accent-soft); }
  .toast.error { border-color: rgba(255, 122, 122, 0.4); color: var(--danger); }
</style>
