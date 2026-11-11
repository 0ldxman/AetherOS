<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "./lib/api";
  import { match, route } from "./lib/router.svelte";
  import ConfirmHost from "./lib/ConfirmHost.svelte";
  import SandboxHost from "./lib/SandboxHost.svelte";
  import { loadSandbox } from "./lib/sandbox.svelte";
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
  import Players from "./routes/Players.svelte";
  import Tasks from "./routes/Tasks.svelte";
  import Task from "./routes/Task.svelte";
  import Mail from "./routes/Mail.svelte";
  import News from "./routes/News.svelte";
  import Guide from "./routes/Guide.svelte";
  import Support from "./routes/Support.svelte";
  import { level, loadMe, me } from "./lib/me.svelte";
  import Discussion from "./lib/Discussion.svelte";
  import { discussion, targetOf } from "./lib/discussion.svelte";
  import { claimed, enter, presence } from "./lib/collab.svelte";
  import PresenceMarks from "./lib/PresenceMarks.svelte";
  import { checkNotes, notes, watchNotes } from "./lib/notes.svelte";
  import { labelOfKey } from "./lib/marks.svelte";
  import AuthorCard from "./lib/AuthorCard.svelte";
  import Icon from "./lib/Icon.svelte";
  import { NAV } from "./lib/nav";
  import SideNav from "./lib/SideNav.svelte";

  onMount(loadMe);
  onMount(loadSandbox);

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
    | { name: "home" }
    | { name: "players"; id: number | null }
    | { name: "boards"; id: number | null }
    | { name: "tasks" }
    | { name: "task"; id: number }
    | { name: "mail"; id: number | null }
    | { name: "talk"; id: number }
    | { name: "news"; id: number | null }
    | { name: "support"; id: number | null }
    | { name: "guide"; slug: string | null };

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
    if ((found = match("/mail/personas/:id", route.path))) return { name: "mail", id: +found.id };
    if ((found = match("/mail/:id", route.path))) return { name: "talk", id: +found.id };
    if (match("/mail", route.path)) return { name: "mail", id: null };
    if ((found = match("/news/:id", route.path))) return { name: "news", id: +found.id };
    if (match("/news", route.path)) return { name: "news", id: null };
    if ((found = match("/guide/:slug", route.path))) return { name: "guide", slug: found.slug };
    if (match("/guide", route.path)) return { name: "guide", slug: null };
    if ((found = match("/support/:id", route.path))) return { name: "support", id: +found.id };
    if (match("/support", route.path)) return { name: "support", id: null };
    if ((found = match("/tasks/:id", route.path))) return { name: "task", id: +found.id };
    if (match("/tasks", route.path)) return { name: "tasks" };
    if ((found = match("/boards/:id", route.path))) return { name: "boards", id: +found.id };
    if (match("/boards", route.path)) return { name: "boards", id: null };
    if ((found = match("/players/:id", route.path))) return { name: "players", id: +found.id };
    if (match("/players", route.path)) return { name: "players", id: null };
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

  const current = $derived(NAV.find((item) => item.section.includes(page.name)) ?? null);

  // обсуждение сущности, на которой автор сейчас: число открытых веток на кнопке
  const target = $derived(claimed.room || targetOf(route.path));
  let talks = $state(0);
  // непрочитанные уведомления на кнопке «Главная»
  const unread = $derived(notes.unread);
  $effect(() => { route.path; checkNotes(); });
  onMount(watchNotes);
  // комната совместной правки той же сущности: кто ещё здесь
  $effect(() => { enter(target, me.data?.username ?? ""); });
  $effect(() => {
    const now = target;
    talks = 0;
    if (!now) return;
    api.GET("/studio/api/comments/counts", { params: { query: { targets: now } } }).then(({ data }) => {
      if (now === target) talks = data?.[now] ?? 0;
    });
  });

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
    <SideNav page={page.name} />

    <AuthorCard />

  </aside>

  <div class="col">
  {#if target}
    <div class="collab">
      {#if presence.peers.length}
        <div class="here" aria-label="Кто ещё на этой странице">
          <span class="muted">Здесь ещё:</span>
          {#each presence.peers.slice(0, 4) as peer (peer.id)}
            <span class="peer" style="--peer: {peer.color}" title={peer.field ? `${peer.name}: в поле «${labelOfKey(peer.field)}»` : peer.name}>{peer.name}</span>
          {/each}
          {#if presence.peers.length > 4}<span class="muted" title={presence.peers.slice(4).map((peer) => peer.name).join(", ")}>и ещё {presence.peers.length - 4}</span>{/if}
        </div>
      {/if}
      <button class="talk" class:on={discussion.open} aria-pressed={discussion.open} onclick={() => (discussion.open = !discussion.open)}>
        <span class="talk-name"><Icon name="chat" />Обсуждение</span>{#if talks}<span class="count">{talks}</span>{/if}
      </button>
    </div>
  {/if}
  <main class="main">
    {#if current && level(current.right) === "read"}
      <div class="readonly" role="status">Только просмотр: у вашей роли нет права править раздел «{current.label}».</div>
    {/if}
    {#if current && level(current.right) === "none"}
      <p class="muted" style="padding: 20px">У вашей роли нет доступа к разделу «{current.label}».</p>
    {:else if page.name === "tasks"}
      <Tasks />
    {:else if page.name === "task"}
      {#key page.id}<Task id={page.id} />{/key}
    {:else if page.name === "boards"}
      {#await import("./routes/Board.svelte")}
        <p class="muted" style="padding: 20px">Загрузка доски…</p>
      {:then loaded}
        {#key page.id}<loaded.default id={page.id} />{/key}
      {:catch}
        <p class="muted" style="padding: 20px">Доска не загрузилась. Обновите страницу.</p>
      {/await}
    {:else if page.name === "news"}
      {#key page.id}<News id={page.id} />{/key}
    {:else if page.name === "support"}
      {#key page.id}<Support id={page.id} />{/key}
    {:else if page.name === "guide"}
      {#key page.slug}<Guide slug={page.slug} />{/key}
    {:else if page.name === "mail"}
      {#key page.id}<Mail id={page.id} />{/key}
    {:else if page.name === "talk"}
      {#await import("./routes/mail/Talk.svelte")}
        <p class="muted" style="padding: 20px">Загрузка сценария…</p>
      {:then loaded}
        {#key page.id}<loaded.default id={page.id} />{/key}
      {:catch}
        <p class="muted" style="padding: 20px">Редактор сценария не загрузился. Обновите страницу.</p>
      {/await}
    {:else if page.name === "players"}
      <Players id={page.id} />
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
</div>

{#if discussion.open && target}
  {#key target}<Discussion {target} onchange={(open) => (talks = open)} />{/key}
{/if}

<PresenceMarks />
<ConfirmHost />
<SandboxHost />

<div class="toasts" popover="manual" bind:this={toastBox} aria-live="polite">
  {#each toasts as item (item.id)}
    <div class="toast" class:error={item.kind === "error"}>
      <span>{item.text}</span>
      {#if item.action}<button class="toast-action" onclick={() => { const act = item.action; dismiss(item.id); act?.run(); }}>{item.action.label}</button>{/if}
    </div>
  {/each}
</div>

<style>
  /* поле, которое только что изменил другой автор */
  :global(.remote-changed) { animation: remote-changed 1.4s ease-out; }
  @keyframes -global-remote-changed { from { box-shadow: 0 0 0 3px rgba(122, 162, 255, 0.55); background-color: rgba(122, 162, 255, 0.14); } to { box-shadow: 0 0 0 3px transparent; } }
  @media (prefers-reduced-motion: reduce) { :global(.remote-changed) { animation: none; outline: 2px solid rgba(122, 162, 255, 0.55); } }
  .shell { display: grid; grid-template-columns: 220px 1fr; height: 100%; }
  .side {
    display: flex; flex-direction: column; gap: 14px; min-height: 0;
    padding: 16px 12px; border-right: 1px solid var(--line-soft); background: var(--panel);
  }
  .brand { display: flex; align-items: center; gap: 8px; padding: 0 8px; font-weight: 650; letter-spacing: 0.2px; }
  .mark { color: var(--accent); }
  .readonly { padding: 6px 32px; background: var(--accent-soft); color: var(--muted); font-size: 12.5px; border-bottom: 1px solid var(--line-soft); }
  .talk { display: inline-flex; align-items: center; gap: 8px; padding: 4px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--text); cursor: pointer; font: inherit; font-size: 12.5px; }
  .talk:hover, .talk.on { background: var(--accent-soft); }
  .count { min-width: 18px; padding: 0 6px; border-radius: 999px; background: var(--accent); color: var(--bg, #111); font-size: 11.5px; font-weight: 700; text-align: center; }
  .talk-name { display: inline-flex; align-items: center; gap: 10px; }
  .col { display: flex; flex-direction: column; min-width: 0; min-height: 0; height: 100%; }
  .collab { flex: none; display: flex; align-items: center; justify-content: flex-end; gap: 16px; padding: 6px 20px; border-bottom: 1px solid var(--line-soft); background: var(--bg); }
  .here { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; font-size: 12px; }
  .peer { display: inline-flex; align-items: center; gap: 5px; padding: 1px 8px 1px 6px; border-radius: 999px; border: 1px solid var(--peer); }
  .peer::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--peer); }
  .main { flex: 1; min-width: 0; min-height: 0; overflow: auto; }
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
