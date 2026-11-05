<script lang="ts">
  import { api, type Schemas } from "../../lib/api";

  type System = Schemas["SystemOut"];
  type Done = (data: System | undefined, error: unknown, text: string) => void;

  let { system, done }: { system: System; done: Done } = $props();

  async function chooseScene(slot: string, script: string) {
    const { data, error } = await api.PUT("/studio/api/systems/{code}/scenes/{slot}", { params: { path: { code: system.code, slot } }, body: { script: script || null } });
    done(data, error, script ? "Сцена назначена." : "Играет встроенная сцена.");
  }
</script>

  <div class="block">
    <h3>Сцены событий <a class="more" href="#/scenes">библиотека →</a></h3>
    <p class="muted small">Что играет в терминале на событии этой ОС. «Встроенная»: сцена движка. Свою пишут в разделе «Сцены».</p>
    {#each system.scenes as row (row.slot)}
      <div class="slotrow" class:own={row.script}>
        <div class="slotinfo">
          <b>{row.label}</b>
          <span class="mono muted small">{row.slot}</span>
          <span class="params">{#each row.params as name}<code>{"{"}{name}{"}"}</code>{/each}</span>
        </div>
        <div class="slotpick">
          <select class="field" value={row.script ?? ""} onchange={(e) => chooseScene(row.slot, e.currentTarget.value)}>
            <option value="">Встроенная (движок)</option>
            {#each system.scene_library as item}<option value={item.slug}>{item.title ? `${item.title} · ${item.slug}` : item.slug}</option>{/each}
          </select>
          {#if row.script}<a class="btn ghost" href="#/scenes/{row.script}">Открыть</a>{/if}
        </div>
      </div>
    {/each}
  </div>

<style>
  .small { font-size: 12px; margin: 0; }
  .slotrow { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(260px, 420px); gap: 16px; align-items: center; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .slotrow.own { border-color: var(--accent); background: var(--accent-soft); }
  .slotinfo { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .params { display: flex; flex-wrap: wrap; gap: 4px; }
  .params code { padding: 0 5px; border-radius: 4px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .slotpick { display: flex; gap: 8px; align-items: center; }
  .slotpick select { flex: 1; min-width: 0; }
  .more { margin-left: auto; font-size: 12px; text-transform: none; letter-spacing: 0; }
</style>
