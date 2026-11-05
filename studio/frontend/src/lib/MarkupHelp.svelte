<script lang="ts">
  /** Краткая справка по разметке под редактором: разворачивается по клику, запоминается в браузере. */
  let open = $state(read());

  function read(): boolean {
    try {
      return localStorage.getItem("studio.markupHelp") === "1";
    } catch {
      return false;
    }
  }
  function toggle(event: Event) {
    open = (event.currentTarget as HTMLDetailsElement).open;
    try {
      localStorage.setItem("studio.markupHelp", open ? "1" : "0");
    } catch {}
  }
</script>

<details class="help" {open} ontoggle={toggle}>
  <summary>Справка: разметка и клавиши</summary>
  <div class="cols">
    <div>
      <h4>Текст</h4>
      <p>Обычный Markdown: <code># Заголовок</code>, <code>**жирный**</code>, <code>*курсив*</code>, <code>- список</code>, <code>[ссылка](адрес)</code>.</p>
      <h4>Скрыть от игрока без ключа</h4>
      <p>Абзацем: <code>::spoiler ключ_a and (ключ_b or not ключ_c)</code>, дальше текст, закрывается строкой <code>::</code>.</p>
      <p>В строке: <code>[текст]&#123;ключ_a&#125;</code>. Пока ключа нет, игрок видит замазку <code>███</code>. Условие: слаги ключей, <code>and</code>, <code>or</code>, <code>not</code>, скобки.</p>
    </div>
    <div>
      <h4>Оформление</h4>
      <p><code>::section 01 | Заголовок</code> раздел; <code>::box border center big</code> рамка; <code>::grid cols=3</code> сетка, ячейки разделяет строка <code>--</code>; <code>::fold Название</code> сворачиваемый блок. Все закрываются строкой <code>::</code>.</p>
      <p><code>::page подпись · стр. &#123;n&#125;/&#123;total&#125;</code> конец листа. <code>::stamp СЕКРЕТНО tone=red</code> штамп и другие виджеты одной строкой.</p>
      <h4>Врезка</h4>
      <p>Отдельный блок справа от статьи (карточка с краткими данными). Пишется той же разметкой на вкладке «Врезка».</p>
      <h4>Клавиши</h4>
      <p><kbd>Ctrl</kbd>+<kbd>S</kbd> сохранить. Замечания разметки появляются под предпросмотром со строкой «стр. N».</p>
    </div>
  </div>
</details>

<style>
  .help { border-top: 1px solid var(--line-soft); background: var(--panel); font-size: 12.5px; }
  summary { padding: 7px 12px; color: var(--muted); cursor: pointer; user-select: none; }
  summary:hover { color: var(--text); }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; max-height: 240px; overflow: auto; padding: 0 12px 10px; color: var(--muted); line-height: 1.45; }
  h4 { margin: 8px 0 2px; color: var(--text); font-size: 12px; font-weight: 600; }
  p { margin: 0 0 4px; }
  code, kbd { padding: 0 4px; border-radius: 3px; background: var(--bg); color: var(--text); font-family: var(--mono, monospace); font-size: 11.5px; }
</style>
