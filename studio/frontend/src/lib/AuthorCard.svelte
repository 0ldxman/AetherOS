<script lang="ts">
  // Карточка автора внизу бокового меню: кто вошёл, роль и меню — уведомления, команда, игра, выход.
  import { onMount } from "svelte";
  import Icon from "./Icon.svelte";
  import { me } from "./me.svelte";
  import { notes } from "./notes.svelte";

  let open = $state(false);
  let root = $state<HTMLElement>();

  const name = $derived(me.data?.username ?? "");
  const role = $derived(me.data?.superuser ? "Суперадмин" : me.data?.role || "Автор");
  // цвет значка из имени: один и тот же у человека везде
  const hue = $derived([...name].reduce((sum, ch) => (sum * 31 + ch.charCodeAt(0)) % 360, 7));

  function outside(event: MouseEvent) {
    if (open && !root?.contains(event.target as Node)) open = false;
  }
  function keys(event: KeyboardEvent) {
    if (event.key === "Escape" && open) {
      open = false;
      root?.querySelector<HTMLElement>(".card")?.focus();
    }
  }
  onMount(() => {
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  });

  async function leave() {
    const csrf = document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1] ?? "";
    const prefix = window.STUDIO.api.replace(/studio\/api\/?$/, "");
    try {
      await fetch(`${prefix}auth/logout/`, { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" });
    } finally {
      location.href = window.STUDIO.site;
    }
  }
</script>

<svelte:window onkeydown={keys} />

{#if name}
  <div class="wrap" bind:this={root}>
    {#if open}
      <div class="menu" role="menu">
        <a role="menuitem" href="#/home" onclick={() => (open = false)}>
          <Icon name="bell" /><span>Уведомления</span>{#if notes.unread}<span class="badge">{notes.unread}</span>{/if}
        </a>
        <a role="menuitem" href="#/team" onclick={() => (open = false)}><Icon name="team" /><span>Команда и роли</span></a>
        <a role="menuitem" href={window.STUDIO.site} target="_blank" rel="noopener"><Icon name="play" /><span>Открыть игру</span></a>
        <hr />
        <button role="menuitem" onclick={leave}><Icon name="logout" /><span>Выйти</span></button>
      </div>
    {/if}
    <button class="card" aria-haspopup="menu" aria-expanded={open} onclick={() => (open = !open)}>
      <span class="avatar" style="--hue: {hue}" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
      <span class="who"><b>{name}</b><span class="role">{role}</span></span>
      {#if notes.unread && !open}<span class="dot" title="Есть непрочитанные уведомления"></span>{/if}
      <Icon name="updown" size={14} />
    </button>
  </div>
{/if}

<style>
  .wrap { position: relative; }
  .card {
    display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius);
    background: var(--panel-2); color: var(--muted); font: inherit; cursor: pointer; text-align: left;
  }
  .card:hover, .card[aria-expanded="true"] { border-color: var(--line); color: var(--text); }
  .card:focus-visible, .menu a:focus-visible, .menu button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .avatar {
    flex: none; display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%;
    background: hsl(var(--hue) 42% 32%); color: #fff; font-weight: 650; font-size: 13px;
  }
  .who { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.25; }
  .who b { color: var(--text); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .role { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex: none; }
  .menu {
    position: absolute; left: 0; right: 0; bottom: calc(100% + 6px); display: flex; flex-direction: column; padding: 4px;
    border: 1px solid var(--line); border-radius: var(--radius); background: var(--raise); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); z-index: 20;
  }
  .menu a, .menu button {
    display: flex; align-items: center; gap: 10px; padding: 7px 10px; border: 0; border-radius: var(--radius-s); background: none;
    color: var(--text); font: inherit; cursor: pointer; text-align: left; text-decoration: none;
  }
  .menu a:hover, .menu button:hover { background: var(--accent-soft); text-decoration: none; }
  .menu hr { width: 100%; margin: 4px 0; border: 0; border-top: 1px solid var(--line-soft); }
  .badge { margin-left: auto; padding: 0 6px; border-radius: 999px; background: var(--accent); color: var(--bg, #111); font-size: 11px; font-weight: 700; }
</style>
