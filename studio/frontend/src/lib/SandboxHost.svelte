<script lang="ts">
  // Окно песочницы: настоящий рабочий стол песочного игрока поверх Студии. Свернуть: плашка в углу, Студией можно пользоваться.
  import Icon from "./Icon.svelte";
  import { closeSandbox, resetSandbox, sandbox, sandboxUrl, showSandbox } from "./sandbox.svelte";
  import { toast } from "./toast.svelte";

  async function copyHint() {
    try { await navigator.clipboard.writeText(sandbox.hint); toast("Скопировано."); } catch { /* буфер может быть закрыт */ }
  }
  function key(event: KeyboardEvent) {
    if (event.key === "Escape" && sandbox.shown) showSandbox(false);
  }
</script>

<svelte:window onkeydown={key} />

{#if sandbox.open}
  {#if sandbox.shown}
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div class="shade" onclick={() => showSandbox(false)}></div>
  {/if}
  <div class="sbx" class:hidden={!sandbox.shown} role="dialog" aria-label="Песочница" aria-hidden={!sandbox.shown}>
    <header class="bar">
      <span class="tag"><Icon name="run" size={12} />Песочница</span>
      <span class="who mono" title="Песочный игрок: виден только вам, его состояние не трогает мир">{sandbox.player}</span>
      {#if sandbox.title}<span class="what">{sandbox.title}</span>{/if}
      {#if sandbox.hint}
        <button class="hint mono" onclick={copyHint} title="Введите это в терминале песочницы. Щелчок копирует."><Icon name="terminal" size={13} />{sandbox.hint}<Icon name="copy" size={12} /></button>
      {/if}
      <span class="grow"></span>
      <button class="btn ghost" onclick={resetSandbox} title="Стереть всё, что сделал песочный игрок"><Icon name="redo" size={14} />Начать заново</button>
      <button class="icon" onclick={() => showSandbox(false)} title="Свернуть (Esc): песочница подождёт" aria-label="Свернуть"><Icon name="minus" size={16} /></button>
      <button class="icon" onclick={closeSandbox} title="Закрыть песочницу. Состояние игрока сохранится до «Начать заново»" aria-label="Закрыть"><Icon name="close" size={16} /></button>
    </header>
    {#key sandbox.nonce}<iframe title="Рабочий стол песочного игрока" src={sandboxUrl()}></iframe>{/key}
  </div>
  {#if !sandbox.shown}
    <div class="pill" role="status">
      <button class="pillopen" onclick={() => showSandbox(true)} title="Развернуть песочницу"><Icon name="run" size={12} />Песочница{#if sandbox.title}<span class="muted"> · {sandbox.title}</span>{/if}</button>
      <button class="pillx" onclick={closeSandbox} aria-label="Закрыть песочницу" title="Закрыть песочницу"><Icon name="close" size={13} /></button>
    </div>
  {/if}
{/if}

<style>
  .shade { position: fixed; inset: 0; z-index: 900; background: rgba(0, 0, 0, 0.35); }
  .sbx { position: fixed; top: 0; right: 0; bottom: 0; z-index: 901; width: min(1280px, calc(100vw - 72px)); display: flex; flex-direction: column;
         background: var(--bg); border-left: 1px solid var(--line); box-shadow: -12px 0 40px rgba(0, 0, 0, 0.45); }
  .sbx.hidden { visibility: hidden; pointer-events: none; }            /* свёрнута, но рабочий стол живёт: окна и терминал не теряются */
  .bar { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--line-soft); background: var(--panel); min-width: 0; }
  .tag { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--text); font-size: 12.5px; font-weight: 600; flex: none; }
  .who { color: var(--muted); font-size: 12px; flex: none; }
  .what { color: var(--text); font-size: 13px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hint { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border: 1px dashed var(--line); border-radius: var(--radius-s); background: var(--bg); color: var(--text); font-size: 12.5px; cursor: pointer; min-width: 0; }
  .hint:hover { border-color: var(--accent); }
  .grow { flex: 1; }
  .icon { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); color: var(--text); cursor: pointer; flex: none; }
  .icon:hover { border-color: var(--line); background: var(--raise); }
  .icon:focus-visible, .hint:focus-visible, .pill button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  iframe { flex: 1; width: 100%; border: 0; background: #000; }
  .pill { position: fixed; right: 16px; bottom: 16px; z-index: 899; display: flex; align-items: center; border: 1px solid var(--accent); border-radius: 999px; background: var(--panel); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4); overflow: hidden; }
  .pill button { border: 0; background: none; color: var(--text); font: inherit; font-size: 13px; cursor: pointer; }
  .pillopen { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px 7px 14px; max-width: 360px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pillopen:hover, .pillx:hover { background: var(--panel-2); }
  .pillx { display: grid; place-items: center; padding: 7px 12px 7px 8px; border-left: 1px solid var(--line-soft) !important; }
  .mono { font-family: var(--mono); }
  .muted { color: var(--muted); }
</style>
