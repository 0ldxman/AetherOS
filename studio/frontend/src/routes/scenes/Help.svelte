<script lang="ts">
  // Справка по языку сцен в широком окне: вкладка «Синтаксис» (всё, что умеет язык, с примерами, которые играют сами)
  // и вкладка «Подстановки» (какие {имена} есть у каждого события ОС).
  import Icon from "../../lib/Icon.svelte";
  import type { Schemas } from "../../lib/api";
  import { GROUPS, SNIPPETS } from "../../lib/scene/catalog";
  import Example from "./Example.svelte";

  let { slots, samples, onclose, onsnippet, ontext }: {
    slots: Schemas["SlotInfo"][]; samples: Record<string, string>;
    onclose: () => void; onsnippet: (template: string) => void; ontext: (text: string) => void;
  } = $props();

  let box: HTMLDialogElement | undefined = $state();
  let tab = $state<"syntax" | "params">("syntax");
  let query = $state("");

  $effect(() => { box?.showModal(); });

  const shown = $derived(SNIPPETS.filter((item) => !query.trim() || `${item.title} ${item.code} ${item.doc} ${item.args}`.toLowerCase().includes(query.trim().toLowerCase())));
  const anchor = (group: string) => `grp-${GROUPS.indexOf(group as (typeof GROUPS)[number])}`;

  function jump(group: string) {
    box?.querySelector(`#${anchor(group)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function insert(template: string) {
    box?.close();
    onsnippet(template);
  }
  function put(text: string) {
    box?.close();
    ontext(text);
  }
</script>

<dialog bind:this={box} aria-labelledby="scene-help-title" onclose={onclose} onclick={(event) => event.target === box && box.close()}>
  <header>
    <h2 id="scene-help-title"><Icon name="guide" size={18} />Язык сцен</h2>
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected={tab === "syntax"} class:on={tab === "syntax"} onclick={() => (tab = "syntax")}>Синтаксис</button>
      <button role="tab" aria-selected={tab === "params"} class:on={tab === "params"} onclick={() => (tab = "params")}>Подстановки</button>
    </div>
    <button class="close" onclick={() => box?.close()} aria-label="Закрыть"><Icon name="close" size={16} /></button>
  </header>

  {#if tab === "syntax"}
    <div class="body">
      <nav class="toc" aria-label="Разделы">
        <label class="find"><Icon name="search" size={14} /><input placeholder="Найти шаг или тег" bind:value={query} aria-label="Поиск по справке" /></label>
        {#each GROUPS as group}
          <button onclick={() => jump(group)}>{group}</button>
        {/each}
      </nav>
      <div class="content">
        {#if !query.trim()}
          <section class="intro">
            <h3>Как устроен текст сцены</h3>
            <ul>
              <li>Обычная строка выводится на экран как есть. В ней работает разметка: цвета <code>&lt;success&gt;…&lt;/success&gt;</code>, <code>&lt;warning&gt;</code>, <code>&lt;error&gt;</code>, <code>&lt;dim&gt;</code> и подстановки <code>{"{host}"}</code>.</li>
              <li>Строка со знаком <code>@</code> в начале это шаг: пауза, полоса прогресса, глитч. Части шага разделяются <code>|</code>.</li>
              <li>Время пишут числом (<code>450</code>, миллисекунды) или диапазоном (<code>200-450</code>): диапазон выбирается заново при каждом показе, поэтому две загрузки подряд не совпадают.</li>
              <li>Блоки (<code>@rows</code>, <code>@bars</code>, <code>@burst</code>) принимают строки с отступом в два пробела.</li>
              <li>Скобки и знаки: <code>{"{{"}</code> и <code>{"}}"}</code> дают <code>{"{"}</code> и <code>{"}"}</code>, <code>&amp;lt;</code> и <code>&amp;gt;</code> дают <code>&lt;</code> и <code>&gt;</code>, <code>&amp;pipe;</code> знак <code>|</code> внутри таблицы. Строка, которая должна начинаться с <code>@</code>, <code>~</code> или <code>#</code>, пишется с обратной косой чертой: <code>\@</code>.</li>
              <li>Неизвестный шаг, подстановка или тег это ошибка: строка подчёркивается в тексте, а у игрока сцена не соберётся, и сыграет встроенная.</li>
            </ul>
          </section>
        {/if}

        {#each GROUPS as group}
          {@const items = shown.filter((item) => item.group === group)}
          {#if items.length}
            <section id={anchor(group)}>
              <h3 class="group">{group}</h3>
              {#each items as item (item.title)}
                <article>
                  <div class="head">
                    <h4>{item.title}</h4>
                    <code class="code">{item.code}</code>
                    <span class="spacer"></span>
                    <button class="put" onclick={() => insert(item.template)} title="Вставить шаблон в текст сцены"><Icon name="plus" size={13} />Вставить</button>
                  </div>
                  {#if item.args}<p class="args">{item.code.startsWith("@") ? item.code : ""} {item.args}</p>{/if}
                  <p class="doc">{item.doc}</p>
                  <Example code={item.example} play={item.play} />
                </article>
              {/each}
            </section>
          {/if}
        {/each}
        {#if !shown.length}<p class="muted none">Ничего не нашлось.</p>{/if}
      </div>
    </div>
  {:else}
    <div class="content params">
      <p class="lead">Подстановка <code>{"{имя}"}</code> заменяется значением при показе сцены игроку. У каждого события ОС свой набор имён. Использовать можно только имена выбранного события, иначе будет ошибка. Щелчок по имени вставляет его в текст.</p>
      {#each slots as item (item.slot)}
        <section class="slot">
          <h4>{item.label}<code>{item.slot}</code></h4>
          {#if item.params.length}
            <div class="chips">
              {#each item.params as name (name)}
                <button class="chip" onclick={() => put(`{${name}}`)} title="Вставить в текст"><code>{"{"}{name}{"}"}</code><span>{samples[name] ?? ""}</span></button>
              {/each}
            </div>
          {:else}
            <p class="muted none">У этого события подстановок нет.</p>
          {/if}
        </section>
      {/each}
      <p class="muted note">Показанные значения условные: в игре подставляются настоящие данные машины, учётки и мира.</p>
    </div>
  {/if}
</dialog>

<style>
  dialog { width: min(1080px, calc(100vw - 32px)); height: min(820px, calc(100vh - 40px)); padding: 0; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); color: var(--text); box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5); overflow: hidden; }
  dialog[open] { display: flex; flex-direction: column; }
  dialog::backdrop { background: rgba(5, 6, 8, 0.6); backdrop-filter: blur(2px); }
  header { flex: none; display: flex; align-items: center; gap: 20px; padding: 12px 16px 0 20px; border-bottom: 1px solid var(--line-soft); }
  h2 { display: inline-flex; align-items: center; gap: 8px; margin: 0 0 12px; font-size: 16px; font-weight: 650; }
  .tabs { display: flex; gap: 4px; margin-right: auto; align-self: flex-end; }
  .tabs button { padding: 8px 14px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); font: inherit; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .close { display: grid; place-items: center; width: 30px; height: 30px; margin-bottom: 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--muted); cursor: pointer; }
  .close:hover { background: var(--panel-2); color: var(--text); }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

  .body { flex: 1; min-height: 0; display: grid; grid-template-columns: 190px minmax(0, 1fr); }
  .toc { display: flex; flex-direction: column; gap: 2px; padding: 14px 10px; border-right: 1px solid var(--line-soft); overflow-y: auto; }
  .toc button { padding: 6px 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; text-align: left; cursor: pointer; }
  .toc button:hover { background: var(--panel-2); color: var(--text); }
  .find { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; padding: 0 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .content { min-width: 0; overflow-y: auto; padding: 16px 22px 28px; }
  .content.params { flex: 1; }
  .intro { margin-bottom: 8px; padding: 12px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg); }
  .intro h3 { margin: 0 0 6px; font-size: 14px; }
  .intro ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 5px; font-size: 13px; color: var(--muted); }
  code { font-family: var(--mono); font-size: 12px; padding: 0 4px; border-radius: 4px; background: var(--panel-2); color: var(--text); }
  .group { margin: 22px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--line-soft); font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); }
  article { display: flex; flex-direction: column; gap: 6px; padding: 12px 0; border-bottom: 1px solid var(--line-soft); }
  article:last-child { border-bottom: 0; }
  .head { display: flex; align-items: center; gap: 10px; }
  h4 { margin: 0; font-size: 14px; font-weight: 650; }
  .code { color: var(--accent); }
  .spacer { flex: 1; }
  .put { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
  .put:hover { border-color: var(--accent); color: var(--text); }
  .args { margin: 0; font: 12px var(--mono); color: var(--accent); }
  .doc { margin: 0; color: var(--muted); font-size: 13px; }
  .none, .note { margin: 12px 0 0; font-size: 12.5px; }
  .lead { margin: 0 0 12px; color: var(--muted); font-size: 13px; max-width: 720px; }
  .slot { margin-bottom: 14px; padding: 12px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg); }
  .slot h4 { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; flex-direction: column; align-items: flex-start; gap: 1px; padding: 5px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel); color: var(--text); font: inherit; cursor: pointer; text-align: left; }
  .chip:hover { border-color: var(--accent); }
  .chip span { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--muted); }
  @media (max-width: 800px) { .body { grid-template-columns: 1fr; } .toc { flex-direction: row; flex-wrap: wrap; border-right: 0; border-bottom: 1px solid var(--line-soft); } .find { display: none; } }
</style>
