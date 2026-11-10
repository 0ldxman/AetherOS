<script lang="ts">
  // Кодировки слоя binary: во что завёрнут настоящий текст. Игрок называет кодировку в cvt по имени.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Hint from "../lib/Hint.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  type Form = Schemas["EncIn"];
  let { name }: { name: string | null } = $props();

  const KINDS: [string, string, string][] = [
    ["codec", "Кодек Python", "Имя кодека: utf-16-le, cp500…"],
    ["hex", "Байты как hex-текст", "Разделитель (по умолчанию пробел)"],
    ["rot", "Сдвиг букв", "Сдвиг: 13"],
    ["xor", "XOR с байтом", "Байт: 0x5a или 90"],
    ["gzip", "gzip", ""], ["morse", "Азбука Морзе", ""], ["reverse", "Байты задом наперёд", ""], ["base32", "base32", ""],
    ["rot47", "rot47 (все печатные символы)", ""], ["bin", "Текст из нулей и единиц", ""], ["dec", "Коды символов десятичными числами", ""],
    ["oct", "Коды символов восьмеричными числами", ""], ["url", "Процентная запись (%D0%9F)", ""], ["base85", "base85", ""],
    ["uu", "uuencode", ""], ["atbash", "Атбаш (алфавит наоборот)", ""], ["base64", "base64", "url (алфавит для URL, без «=»), nowrap (одной строкой)"],
  ];
  const kindLabel = (code: string) => KINDS.find((k) => k[0] === code)?.[1] ?? code;

  let rows = $state<Schemas["EncRow"][]>([]);
  let form = $state<Form>({ name: "", title: "", kind: "codec", param: "" });
  let saved = $state("");
  let errors = $state<Record<string, string[]>>({});
  let query = $state("");
  let dialog = $state<null | "new">(null);
  let newName = $state("");
  let busy = $state(false);

  const current = $derived(name ?? rows[0]?.name ?? null);
  const row = $derived(rows.find((r) => r.name === current) ?? null);
  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty);
  const shown = $derived(rows.filter((r) => !query.trim() || `${r.name} ${r.title}`.toLowerCase().includes(query.trim().toLowerCase())));
  const hint = $derived(KINDS.find((k) => k[0] === form.kind)?.[2] ?? "");

  async function list() { rows = (await api.GET("/studio/api/file-encodings")).data ?? []; }
  onMount(list);
  $effect(() => {
    if (row) {
      const next = { name: row.name, title: row.title, kind: row.kind, param: row.param };
      form = next;
      saved = JSON.stringify(next);
      errors = {};
    }
  });

  async function save() {
    if (!row) return;
    errors = {};
    busy = true;
    const { error } = await api.PUT("/studio/api/file-encodings/{name}", { params: { path: { name: row.name } }, body: $state.snapshot(form) });
    busy = false;
    if (error) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    toast("Кодировка сохранена.");
    await list();
  }

  async function create() {
    busy = true;
    const { data, error } = await api.POST("/studio/api/file-encodings", { body: { name: newName.trim(), title: "", kind: "codec", param: "utf-8" } });
    busy = false;
    if (error || !data) {
      const fields = (error as { fields?: Record<string, string[]> }).fields;
      return toast(fields ? Object.values(fields).flat().join(" ") : problem(error, "Не создалась."), "error");
    }
    dialog = null;
    newName = "";
    await list();
    go(`/encodings/${data.name}`);
  }

  async function remove() {
    if (!row) return;
    if (!(await ask(`Удалить кодировку «${row.name}»?`, "Слои, в которых игрок её называл, перестанут разбираться.", "Удалить"))) return;
    const { error } = await api.DELETE("/studio/api/file-encodings/{name}", { params: { path: { name: row.name } } });
    if (error) return toast(problem(error), "error");
    toast("Кодировка удалена.");
    await list();
    go("/encodings");
  }
</script>

<ListDetail title="Кодировки">
  {#snippet list()}
    <nav class="sub"><a href="#/formats">Форматы</a><a class="on" href="#/encodings">Кодировки</a></nav>
    <input class="field find" placeholder="Поиск" bind:value={query} aria-label="Поиск кодировки" />
    {#each shown as item (item.name)}
      <a class="item" class:on={item.name === current} href="#/encodings/{item.name}">
        <b class="mono">{item.name}</b>
        <span class="muted small">{kindLabel(item.kind)}{item.param ? ` · ${item.param}` : ""}</span>
      </a>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn add" onclick={() => (dialog = "new")}>+ Кодировка</button>
  {/snippet}

  {#if row}
    <section class="editor">
      <header class="top">
        <b class="mono big">{row.name}</b>
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={remove}>Удалить</button>
        <button class="btn primary" disabled={!dirty || busy} onclick={save}>Сохранить</button>
      </header>
      <div class="block">
        <p class="muted small">Имя не меняется: игроки называют кодировку в командах и слоях.</p>
        <label><span class="label">Название</span><input class="field" bind:value={form.title} /></label>
        <label><span class="label">Вид</span>
          <select class="field" bind:value={form.kind}>{#each KINDS as [code, text]}<option value={code}>{text}</option>{/each}</select></label>
        <label><span class="label">Параметр{#if hint}<Hint text={hint} />{/if}</span>
          <input class="field mono" bind:value={form.param} class:bad={errors.param} placeholder={hint} />
          {#if errors.param}<span class="err">{errors.param.join(" ")}</span>{/if}</label>
      </div>
    </section>
  {:else}
    <p class="muted empty">{rows.length ? "Загрузка…" : "Кодировок пока нет."}</p>
  {/if}
</ListDetail>

{#if dialog === "new"}
  <Dialog title="Новая кодировка" confirm="Создать" {busy} disabled={!newName.trim()} onsubmit={create} onclose={() => (dialog = null)}>
    <label><span class="label">Имя (так её назовёт игрок)</span><input class="field mono" placeholder="utf16" bind:value={newName} /></label>
  </Dialog>
{/if}

<style>
  .sub { display: flex; gap: 4px; margin: 0 10px 8px; }
  .sub a { padding: 3px 10px; border-radius: 999px; color: var(--muted); }
  .sub a.on { background: var(--accent-soft); color: var(--text); }
  .sub a:hover { text-decoration: none; }
  .find { margin: 0 8px 8px; width: auto; }
  .small { font-size: 12px; margin: 0; }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; max-width: 640px; }
  .top { display: flex; align-items: center; gap: 12px; }
  .big { font-size: 18px; }
  .spacer { flex: 1; }
  .block { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .field.bad { border-color: var(--danger); }
  .err { color: var(--danger); font-size: 12px; }
  .empty { padding: 24px; }
</style>
