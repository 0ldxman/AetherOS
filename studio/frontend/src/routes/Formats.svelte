<script lang="ts">
  // Форматы файлов: как выглядит формат (расширение, байты, устройство) и что вводится у объекта этого формата.
  import { onMount } from "svelte";
  import DraftState from "../lib/DraftState.svelte";
  import { SharedForm } from "../lib/shared.svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Hint from "../lib/Hint.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  type Form = Schemas["FmtIn"];
  let { name }: { name: string | null } = $props();

  const KINDS: [string, string, string][] = [
    ["signature", "Сигнатура и тело", "Первые байты, дальше тело как есть: pdf, png, mp3."],
    ["text", "Текстовый шаблон", "Файл читается как текст по шаблону с подстановками."],
    ["chunks", "Блоки с метками", "Сигнатура и блоки «длина, метка, данные», как в PNG."],
    ["package", "Пакет частей с таблицей", "Сигнатура, число частей и таблица (имя, смещение, размер)."],
    ["zip", "Zip-контейнер", "Настоящий zip без сжатия: части это файлы внутри (docx, xlsx)."],
  ];
  const CONTENTS: [string, string][] = [
    ["text", "Текст"], ["text_asset", "Текст или файл из хранилища"], ["asset", "Файл из хранилища"], ["link_asset", "Ссылка или файл"],
    ["scene", "Сцена карты"], ["none", "Без содержимого"],
  ];
  const SOURCES: [string, string][] = [
    ["body", "Текст источника"], ["image", "Картинка источника"], ["template", "Текст-шаблон"], ["hex", "Постоянные байты (hex)"],
    ["noise", "Шум (длина в значении)"], ["confidence", "Байт уверенности (70–99)"],
  ];
  const kindLabel = (code: string) => KINDS.find((k) => k[0] === code)?.[1] ?? code;
  const PLACEHOLDERS = "{body} {body_html} {who} {when} {ref} {src} {at} {title} {hash} {sender} {recipients} {subject} {date} {id} {host}";

  let rows = $state<Schemas["FmtRow"][]>([]);
  let found = $state<Schemas["FmtDetail"] | null>(null);
  let form = $state<Form>(blank(""));
  let saved = $state("");
  let base = $state<Form | null>(null);                    // сохранённое: им наполняется общий черновик
  let errors = $state<Record<string, string[]>>({});
  let query = $state("");
  let dialog = $state<null | "new">(null);
  let newName = $state("");
  let busy = $state(false);

  function blank(value: string): Form {
    return { name: value, title: "", extension: "", aliases: "", kind: "signature", magic: "", template: "", content: "text_asset", markup: false, editable: false, part_list: [] };
  }

  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);      // в совместном режиме черновик на сервере
  const shown = $derived(rows.filter((row) => !query.trim() || `${row.name} ${row.title} ${row.extension} ${row.aliases}`.toLowerCase().includes(query.trim().toLowerCase())));
  const current = $derived(name ?? rows[0]?.name ?? null);
  const hasMagic = $derived(["signature", "chunks", "package"].includes(form.kind));
  const hasParts = $derived(["chunks", "package", "zip"].includes(form.kind));

  async function list() {
    rows = (await api.GET("/studio/api/file-formats")).data ?? [];
  }
  async function load(target: string | null) {
    found = null;
    base = null;
    errors = {};
    if (!target) return;
    const { data } = await api.GET("/studio/api/file-formats/{name}", { params: { path: { name: target } } });
    if (!data) return;
    found = data;
    const { used: _used, ...fields } = data;
    form = fields;
    saved = JSON.stringify(form);
    base = JSON.parse(saved);
  }
  // общий черновик формата; кто-то сохранил: перечитать сохранённое, черновик не трогается
  const share = new SharedForm({
    room: () => `file-formats/${current}`,
    texts: ["title", "template", "magic", "aliases"],
    draft: () => form,
    base: () => base,
    onRemoteSave: async () => {
      if (!current) return;
      const { data } = await api.GET("/studio/api/file-formats/{name}", { params: { path: { name: current } } });
      if (!data) return;
      found = data;
      const { used: _used, ...fields } = data;
      saved = JSON.stringify(fields);
      base = JSON.parse(saved);
      list();
    },
  });
  onMount(list);
  $effect(() => { load(current); });

  async function save() {
    if (!found) return;
    errors = {};
    busy = true;
    const { data, error } = await api.PUT("/studio/api/file-formats/{name}", { params: { path: { name: found.name } }, body: $state.snapshot(form) });
    busy = false;
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    share.markSaved();
    toast(data.name !== found.name && found.used ? `Формат переименован, объектов обновлено: ${found.used}.` : "Формат сохранён.");
    await list();
    if (data.name !== found.name) go(`/formats/${data.name}`);
    else await load(data.name);
  }

  async function create() {
    busy = true;
    const { data, error } = await api.POST("/studio/api/file-formats", { body: blank(newName.trim()) });
    busy = false;
    if (error || !data) {
      const fields = (error as { fields?: Record<string, string[]> }).fields;
      return toast(fields ? Object.values(fields).flat().join(" ") : problem(error, "Не создался."), "error");
    }
    dialog = null;
    newName = "";
    await list();
    go(`/formats/${data.name}`);
  }

  async function remove() {
    if (!found) return;
    if (!(await ask(`Удалить формат «${found.name}»?`, "Формат пропадёт из списка. Игроки больше не смогут конвертировать в него.", "Удалить"))) return;
    const { error } = await api.DELETE("/studio/api/file-formats/{name}", { params: { path: { name: found.name } } });
    if (error) return toast(problem(error), "error");
    toast("Формат удалён.");
    await list();
    go("/formats");
  }

  function addPart() { form.part_list = [...form.part_list, { name: "", source: "body", value: "" }]; }
  function dropPart(index: number) { form.part_list = form.part_list.filter((_, i) => i !== index); }
  function movePart(index: number, step: number) {
    const next = [...form.part_list];
    const to = index + step;
    if (to < 0 || to >= next.length) return;
    [next[index], next[to]] = [next[to], next[index]];
    form.part_list = next;
  }
</script>

<ListDetail title="Форматы">
  {#snippet list()}
    <nav class="sub"><a class="on" href="#/formats">Форматы</a><a href="#/encodings">Кодировки</a></nav>
    <input class="field find" placeholder="Поиск" bind:value={query} aria-label="Поиск формата" />
    {#each shown as row (row.name)}
      <a class="item" class:on={row.name === current} href="#/formats/{row.name}">
        <b>{row.name}{#if row.extension}<span class="muted mono ext"> {row.extension}</span>{/if}</b>
        <span class="muted small">{kindLabel(row.kind)} · объектов {row.used}</span>
      </a>
    {:else}
      <p class="muted small pad">Ничего не нашлось.</p>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn add" onclick={() => (dialog = "new")}>+ Формат</button>
  {/snippet}

  {#if found}
    <section class="editor">
      <header class="top">
        <b class="mono big">{found.name}</b>
        <span class="muted small">объектов с этим форматом: {found.used}</span>
        <span class="spacer"></span>
        <button class="btn ghost danger" disabled={found.used > 0} title={found.used ? "Формат есть у объектов: сначала смените им формат" : ""} onclick={remove}>Удалить</button>
        <DraftState {share} {dirty} saved="" />
        <button class="btn primary" disabled={!dirty || busy} onclick={save}>Сохранить</button>
      </header>
      {#if errors.__all__}<p class="err">{errors.__all__.join(" ")}</p>{/if}

      <div class="cols">
        <div class="block">
          <h3>Основное</h3>
          <label><span class="label">Имя<Hint text="Как игрок называет формат в cvt: строчными буквами. При переименовании имя поменяется у всех объектов с этим форматом." /></span>
            <input class="field mono" bind:value={form.name} class:bad={errors.name} />
            {#if form.name !== found.name && found.used}<span class="warn small">Переименование заденет объектов: {found.used}.</span>{/if}
            {#if errors.name}<span class="err">{errors.name.join(" ")}</span>{/if}</label>
          <label><span class="label">Название</span><input class="field" bind:value={form.title} placeholder="SCAN: картинка + OCR" /></label>
          <div class="two">
            <label><span class="label">Расширение</span><input class="field mono" bind:value={form.extension} placeholder=".scan" class:bad={errors.extension} />
              {#if errors.extension}<span class="err">{errors.extension.join(" ")}</span>{/if}</label>
            <label><span class="label">Другие расширения<Hint text="Через запятую: jpeg, jpe у формата jpg. cvt и тип записи вики находят формат и по ним." /></span>
              <input class="field mono" bind:value={form.aliases} placeholder="jpeg, jpe" class:bad={errors.aliases} />
              {#if errors.aliases}<span class="err">{errors.aliases.join(" ")}</span>{/if}</label>
          </div>
          <h3>Что вводится у объекта</h3>
          <label><span class="label">Содержимое</span>
            <select class="field" bind:value={form.content}>{#each CONTENTS as [code, text]}<option value={code}>{text}</option>{/each}</select></label>
          <label class="check"><input type="checkbox" bind:checked={form.markup} /> Разбирать текст разметкой<Hint text="Текст записан разметкой (::map, ::section, врезка): парсер рисует виджеты страницы, а в байтах файла превращает их в то, что есть у формата." /></label>
          <label class="check"><input type="checkbox" bind:checked={form.editable} /> Игрок может править<Hint text="Файлы этого формата игрок правит командой edt. Выключено у форматов вроде PDF." /></label>
        </div>

        <div class="block">
          <h3>Устройство файла</h3>
          <label><span class="label">Вид</span>
            <select class="field" bind:value={form.kind}>{#each KINDS as [code, text]}<option value={code}>{text}</option>{/each}</select>
            <span class="muted small">{KINDS.find((k) => k[0] === form.kind)?.[2]}</span></label>
          {#if hasMagic}
            <label><span class="label">Сигнатура<Hint text="Первые байты файла в hex через пробел: 9e 53 43 41 4e 0d 0a 1b." /></span>
              <input class="field mono" bind:value={form.magic} placeholder="89 50 4e 47" class:bad={errors.magic} />
              {#if errors.magic}<span class="err">{errors.magic.join(" ")}</span>{/if}</label>
          {/if}
          {#if form.kind === "text"}
            <label><span class="label">Шаблон<Hint text="Подстановки: {PLACEHOLDERS}. Фигурные скобки самого текста удваиваются: {'{{ }}'}." /></span>
              <textarea class="field area mono" rows="6" bind:value={form.template} class:bad={errors.template}></textarea>
              {#if errors.template}<span class="err">{errors.template.join(" ")}</span>{/if}</label>
          {/if}
          {#if hasParts}
            <h3>Части</h3>
            {#if errors.parts}<ul class="errs">{#each errors.parts as message}<li>{message}</li>{/each}</ul>{/if}
            <div class="parts">
              {#each form.part_list as part, index (index)}
                <div class="part">
                  <input class="field mono" bind:value={part.name} placeholder={form.kind === "chunks" ? "IHDR" : form.kind === "zip" ? "word/document.xml" : "имя"} aria-label="Имя части {index + 1}" />
                  <select class="field" bind:value={part.source} aria-label="Источник части {index + 1}">{#each SOURCES as [code, text]}<option value={code}>{text}</option>{/each}</select>
                  <input class="field mono" bind:value={part.value} placeholder="значение" aria-label="Значение части {index + 1}" disabled={!["hex", "template", "noise"].includes(part.source)} />
                  <button class="btn ghost" aria-label="Выше" disabled={index === 0} onclick={() => movePart(index, -1)}>↑</button>
                  <button class="btn ghost" aria-label="Ниже" disabled={index === form.part_list.length - 1} onclick={() => movePart(index, 1)}>↓</button>
                  <button class="btn ghost danger" aria-label="Убрать часть {index + 1}" onclick={() => dropPart(index)}>×</button>
                </div>
              {:else}
                <p class="muted small">Частей нет. Для этого вида нужна хотя бы одна.</p>
              {/each}
            </div>
            <button class="btn" onclick={addPart}>+ Часть</button>
          {/if}
        </div>
      </div>
    </section>
  {:else}
    <p class="muted empty">{rows.length ? "Загрузка…" : "Форматов пока нет."}</p>
  {/if}
</ListDetail>

{#if dialog === "new"}
  <Dialog title="Новый формат" confirm="Создать" {busy} disabled={!newName.trim()} onsubmit={create} onclose={() => (dialog = null)}>
    <label><span class="label">Имя</span><input class="field mono" placeholder="scan" bind:value={newName} /></label>
    <p class="muted small">Остальное задаётся в карточке. Новый формат создаётся как «сигнатура и тело» с пустой сигнатурой; для него нужна сигнатура, поэтому лучше сначала выбрать вид.</p>
  </Dialog>
{/if}

<style>
  .sub { display: flex; gap: 4px; margin: 0 10px 8px; }
  .sub a { padding: 3px 10px; border-radius: 999px; color: var(--muted); }
  .sub a.on { background: var(--accent-soft); color: var(--text); }
  .sub a:hover { text-decoration: none; }
  .find { margin: 0 8px 8px; width: auto; }
  .ext { font-weight: 400; }
  .small { font-size: 12px; }
  .pad { padding: 0 10px; }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 12px; }
  .big { font-size: 18px; }
  .spacer { flex: 1; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
  .block { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); min-width: 0; }
  h3 { margin: 6px 0 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3:first-child { margin-top: 0; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .check { display: flex; align-items: center; gap: 8px; }
  .area { height: auto; min-height: 90px; padding: 8px 10px; resize: vertical; }
  .field.bad { border-color: var(--danger); }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
  .warn { color: var(--warn); }
  .errs { margin: 0; padding-left: 16px; color: var(--danger); font-size: 12px; }
  .parts { display: flex; flex-direction: column; gap: 6px; }
  .part { display: grid; grid-template-columns: minmax(80px, 1fr) minmax(120px, 1.2fr) minmax(80px, 1fr) auto auto auto; gap: 6px; align-items: center; }
  .part .btn { padding: 0 8px; height: 30px; }
  .empty { padding: 24px; }
</style>
