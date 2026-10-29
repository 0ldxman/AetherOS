<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import Overview from "./machine/Overview.svelte";
  import Accounts from "./machine/Accounts.svelte";
  import Access from "./machine/Access.svelte";
  import Journal from "./machine/Journal.svelte";
  import Groups from "./machine/Groups.svelte";
  import Disks from "./machine/Disks.svelte";

  let { id, tab, sub }: { id: number; tab: string; sub: number | null } = $props();

  let machine = $state<Schemas["Overview"] | null>(null);

  export async function reload() {
    const { data, error } = await api.GET("/studio/api/machines/{machine_id}", { params: { path: { machine_id: id } } });
    if (error || !data) return toast("Машина не найдена.", "error");
    machine = data;
  }

  onMount(reload);

  const TABS = [
    { key: "overview", label: "Обзор" },
    { key: "accounts", label: "Учётки" },
    { key: "access", label: "Доступ" },
    { key: "journal", label: "Журнал" },
    { key: "groups", label: "Группы" },
    { key: "disks", label: "Диски" },
  ];
  const STATUS: Record<string, string> = { ONLINE: "online", OFFLINE: "offline", MAINTENANCE: "обслуживание" };
</script>

{#if !machine}
  <p class="muted loading">Загрузка…</p>
{:else}
  <div class="machine">
    <header class="head">
      <button class="btn ghost" onclick={() => go("/machines")}>←</button>
      <span class="dot {machine.status.toLowerCase()}"></span>
      <h1 class="mono">{machine.hostname || "без хоста"}</h1>
      <span class="muted">{machine.name}</span>
      <span class="chip">{machine.system}</span>
      <span class="chip">{STATUS[machine.status] ?? machine.status}</span>
      {#if machine.hid}<span class="chip mono">hid {machine.hid}</span>{/if}
      <span class="spacer"></span>
      <button class="btn" onclick={() => go(`/machines/${id}/access`)}>Проверить вход</button>
    </header>

    <nav class="tabs">
      {#each TABS as item}
        <a class="tab" class:on={tab === item.key} href="#/machines/{id}/{item.key}">
            {item.label}
            {#if item.key === "accounts"}<span class="count">{machine.accounts.length}</span>{/if}
            {#if item.key === "overview" && machine.online.length}<span class="count live">{machine.online.length}</span>{/if}
          </a>
      {/each}
    </nav>

    <section class="body">
      {#if tab === "accounts"}
        <Accounts {machine} selected={sub} onchange={reload} />
      {:else if tab === "access"}
        <Access {machine} account={sub} />
      {:else if tab === "groups"}
        <Groups {machine} onchange={reload} />
      {:else if tab === "disks"}
        <Disks {machine} />
      {:else if tab === "journal"}
        <Journal {machine} account={sub} />
      {:else}
        <Overview {machine} onchange={reload} />
      {/if}
    </section>
  </div>
{/if}

<style>
  .loading { padding: 32px; }
  .machine { display: flex; flex-direction: column; height: 100%; }
  .head { display: flex; align-items: center; gap: 10px; padding: 14px 20px 10px; }
  h1 { margin: 0; font-size: 18px; font-weight: 650; }
  .spacer { flex: 1; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--faint); }
  .dot.online { background: var(--ok); box-shadow: 0 0 0 3px rgba(95, 208, 160, 0.15); }
  .dot.maintenance { background: var(--warn); }
  .tabs { display: flex; gap: 2px; padding: 0 20px; border-bottom: 1px solid var(--line-soft); }
  .tab { display: flex; align-items: center; gap: 6px; padding: 9px 12px; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .count { padding: 0 6px; border-radius: 999px; background: var(--raise); font-size: 11px; color: var(--muted); }
  .count.live { background: rgba(95, 208, 160, 0.15); color: var(--ok); }
  .body { flex: 1; min-height: 0; overflow: auto; }
</style>
