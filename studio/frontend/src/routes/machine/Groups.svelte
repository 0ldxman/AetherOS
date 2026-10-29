<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { toast } from "../../lib/toast.svelte";

  type Row = Schemas["GroupRow"];

  let { machine, onchange }: { machine: Schemas["Overview"]; onchange: () => void } = $props();

  let table = $state<Schemas["GroupTable"] | null>(null);
  let adding = $state(false);
  let newName = $state("");

  const path = $derived({ machine_id: machine.id });

  async function load() {
    table = (await api.GET("/studio/api/machines/{machine_id}/groups", { params: { path } })).data ?? null;
  }
  onMount(load);

  function done(data: Schemas["GroupTable"] | undefined, error: unknown, text: string) {
    if (error || !data) return toast(problem(error), "error");
    table = data;
    toast(text);
    onchange();
  }

  async function put(row: Row, privileges: string[], everyone: boolean) {
    const { data, error } = await api.PUT("/studio/api/machines/{machine_id}/groups/{name}", {
      params: { path: { ...path, name: row.name } }, body: { privileges, everyone },
    });
    done(data, error, row.source === "system" ? `Группа ${row.name} переопределена на этой машине.` : "Сохранено.");
  }

  function toggle(row: Row, code: string) {
    if (row.disabled) return;
    const next = row.privileges.includes(code) ? row.privileges.filter((p) => p !== code) : [...row.privileges, code];
    put(row, next, row.everyone);
  }

  async function revert(row: Row) {
    const { data, error } = await api.DELETE("/studio/api/machines/{machine_id}/groups/{name}", { params: { path: { ...path, name: row.name } } });
    done(data, error, row.overrides || row.disabled ? `Группа ${row.name} снова как у типа системы.` : `Группа ${row.name} удалена.`);
  }

  async function disable(row: Row) {
    const { data, error } = await api.POST("/studio/api/machines/{machine_id}/groups/{name}/disable", { params: { path: { ...path, name: row.name } } });
    done(data, error, `Группа ${row.name} на этой машине не действует.`);
  }

  async function create() {
    const name = newName.trim();
    const { data, error } = await api.PUT("/studio/api/machines/{machine_id}/groups/{name}", {
      params: { path: { ...path, name } }, body: { privileges: [], everyone: false },
    });
    adding = false;
    newName = "";
    done(data, error, `Группа ${name} создана.`);
  }

  const SOURCE: Record<string, string> = { system: "от типа", machine: "своя", default: "по умолчанию" };
</script>

{#if table}
  <div class="wrap">
    <p class="muted lead">
      Привилегии учётки складываются по её группам; у root есть всё. Клик по клетке группы типа системы переопределяет её на этой машине
      (у остальных машин типа она не меняется).
    </p>
    <div class="matrix" style:--cols={table.privileges.length}>
      <div class="cell head name">Группа</div>
      {#each table.privileges as privilege}<div class="cell head priv" title={privilege.label}>{privilege.code}<small>{privilege.label}</small></div>{/each}
      <div class="cell head">Все учётки</div>
      <div class="cell head">Кто в группе</div>
      <div class="cell head"></div>

      {#each table.groups as row (row.name)}
        <div class="cell name" class:off={row.disabled}>
          <b class="mono">{row.name}</b>
          <span class="chip {row.source}">{row.disabled ? "отключена" : row.overrides ? "переопределена" : SOURCE[row.source]}</span>
        </div>
        {#each table.privileges as privilege}
          <button class="cell tick" class:on={row.privileges.includes(privilege.code)} class:off={row.disabled} disabled={row.disabled}
                  title={privilege.label} onclick={() => toggle(row, privilege.code)}>
            {row.privileges.includes(privilege.code) ? "●" : "·"}
          </button>
        {/each}
        <button class="cell tick" class:on={row.everyone} disabled={row.disabled} onclick={() => put(row, row.privileges, !row.everyone)}>
          {row.everyone ? "да" : "—"}
        </button>
        <div class="cell members">
          {#each row.members as login}<a class="mono" href="#/machines/{machine.id}/accounts/{machine.accounts.find((a) => a.login === login)?.id ?? ''}">{login}</a>{/each}
          {#if !row.members.length}<span class="muted">никого</span>{/if}
        </div>
        <div class="cell acts">
          {#if row.overrides || row.disabled}<button class="btn ghost" onclick={() => revert(row)}>Как у типа</button>{/if}
          {#if row.source === "system" && !row.disabled}<button class="btn ghost" onclick={() => disable(row)}>Отключить</button>{/if}
          {#if row.source === "machine" && !row.overrides}<button class="btn ghost danger" onclick={() => revert(row)}>Удалить</button>{/if}
        </div>
      {/each}
    </div>
    <button class="btn add" onclick={() => (adding = true)}>+ Группа машины</button>
  </div>
{:else}
  <p class="muted wrap">Загрузка…</p>
{/if}

{#if adding}
  <Dialog title="Новая группа машины" confirm="Создать" onsubmit={create} onclose={() => (adding = false)}>
    <input class="field mono" placeholder="имя (латиницей)" bind:value={newName} />
  </Dialog>
{/if}

<style>
  .wrap { padding: 16px 20px 24px; }
  .lead { margin: 0 0 14px; max-width: 760px; }
  .matrix {
    display: grid; grid-template-columns: 220px repeat(var(--cols), minmax(74px, 1fr)) 90px minmax(160px, 1.2fr) 190px;
    border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; background: var(--panel);
  }
  .cell { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-bottom: 1px solid var(--line-soft); min-height: 44px; }
  .cell.head { flex-direction: column; align-items: flex-start; justify-content: flex-end; gap: 2px; color: var(--muted); font-size: 12px; background: var(--panel-2); }
  .cell.head.priv { font-family: var(--mono); color: var(--text); }
  .cell.head small { font-family: var(--font); color: var(--faint); font-size: 10.5px; line-height: 1.25; }
  .name { justify-content: space-between; }
  .name.off b { color: var(--faint); text-decoration: line-through; }
  .tick { justify-content: center; border: 0; border-bottom: 1px solid var(--line-soft); background: none; cursor: pointer; color: var(--faint); font-size: 15px; }
  .tick:hover:not(:disabled) { background: var(--panel-2); }
  .tick.on { color: var(--ok); }
  .tick.off { opacity: 0.35; cursor: default; }
  .members { flex-wrap: wrap; gap: 6px; }
  .acts { justify-content: flex-end; gap: 4px; }
  .chip.machine { background: var(--accent-soft); color: var(--accent); }
  .add { margin-top: 12px; }
</style>
