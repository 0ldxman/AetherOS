<script lang="ts">
  // Боковое меню: группы разделов со значками. Группу можно свернуть; выбор запоминается в браузере.
  import Icon from "./Icon.svelte";
  import { GROUPS } from "./nav";
  import { level } from "./me.svelte";
  import { notes } from "./notes.svelte";

  let { page }: { page: string } = $props();

  const KEY = "studio.nav.closed";
  function restore(): string[] {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
      return Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [];
    } catch { return []; }
  }
  let closed = $state<string[]>(restore());

  function remember() {
    try { localStorage.setItem(KEY, JSON.stringify($state.snapshot(closed))); } catch {}
  }
  function toggle(id: string) {
    closed = closed.includes(id) ? closed.filter((x) => x !== id) : [...closed, id];
    remember();
  }

  const holds = (group: (typeof GROUPS)[number]) => group.items.some((item) => item.section.includes(page));
  // перешли в раздел свёрнутой группы (ссылкой, поиском, «назад»): группа раскрывается
  $effect(() => {
    const open = GROUPS.find((group) => group.title && holds(group));
    if (open && closed.includes(open.id)) {
      closed = closed.filter((x) => x !== open.id);
      remember();
    }
  });
</script>

<nav aria-label="Разделы Студии">
  {#each GROUPS as group (group.id)}
    {@const shut = !!group.title && closed.includes(group.id)}
    <div class="group">
      {#if group.title}
        <button class="head" aria-expanded={!shut} aria-controls={`nav-${group.id}`} onclick={() => toggle(group.id)}>
          <span class="chev" class:shut><Icon name="chevron" size={12} /></span>
          <span>{group.title}</span>
          {#if shut && holds(group)}<span class="here" title="Вы в этой группе"></span>{/if}
        </button>
      {/if}
      {#if !shut}
        <div class="items" id={`nav-${group.id}`}>
          {#each group.items as item (item.href)}
            {#if level(item.right) === "none"}
              <span class="nav off" title="Нет прав на этот раздел"><Icon name={item.icon} /><span class="label">{item.label}</span></span>
            {:else}
              <a class="nav" class:on={item.section.includes(page)} href={item.href} aria-current={item.section.includes(page) ? "page" : undefined}>
                <Icon name={item.icon} /><span class="label">{item.label}</span>
                {#if item.href === "#/home" && notes.unread}<span class="badge" title="Непрочитанные уведомления">{notes.unread}</span>{/if}
              </a>
            {/if}
          {/each}
        </div>
      {/if}
    </div>
  {/each}
</nav>

<style>
  nav { display: flex; flex-direction: column; gap: 8px; min-height: 0; overflow-y: auto; margin: 0 -4px; padding: 0 4px; }
  .group, .items { display: flex; flex-direction: column; gap: 1px; }
  .head {
    display: flex; align-items: center; gap: 4px; padding: 4px 10px 4px 6px; border: 0; border-radius: var(--radius-s); background: none;
    color: var(--faint); font: inherit; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; cursor: pointer; text-align: left;
  }
  .head:hover { color: var(--text); }
  .chev { display: inline-flex; transition: transform 0.15s ease-out; }
  .chev.shut { transform: rotate(-90deg); }
  .here { width: 6px; height: 6px; margin-left: auto; border-radius: 50%; background: var(--accent); }
  .nav { display: flex; align-items: center; gap: 10px; padding: 5px 10px; border-radius: var(--radius-s); color: var(--muted); }
  .nav :global(svg) { flex: none; }
  .label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  a.nav:hover { background: var(--panel-2); color: var(--text); text-decoration: none; }
  .nav.on { background: var(--accent-soft); color: var(--text); }
  .nav.on :global(svg) { color: var(--accent); }
  .nav.off { color: var(--faint); cursor: not-allowed; }
  .badge { margin-left: auto; padding: 0 6px; border-radius: 999px; background: var(--accent); color: var(--bg, #111); font-size: 11px; font-weight: 700; }
  .head:focus-visible, .nav:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  @media (prefers-reduced-motion: reduce) { .chev { transition: none; } }
</style>
