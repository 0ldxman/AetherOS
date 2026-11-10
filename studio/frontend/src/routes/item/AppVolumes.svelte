<script lang="ts">
  // Разделы вики приложения: строки «volume хост:/путь as Название user=запись» файла .app. Блок читает и пишет эти строки в тексте,
  // а проверка показывает автору, откроется ли раздел у игрока (игрок причину отказа не видит).
  import { onMount, untrack } from "svelte";
  import { api, type Schemas } from "../../lib/api";

  let { body = $bindable() }: { body: string } = $props();

  type Row = { host: string; path: string; title: string; user: string };
  const VOLUME = /^(?:([^:\s/]+):)?(\/\S*)(?:\s+as\s+(.+?))?(?:\s+user=(\S+))?$/;
  const LINES = /^volume[ \t]+(.*)$/gim;

  function parse(text: string): { rows: Row[]; raw: string[] } {
    const rows: Row[] = [];
    const raw: string[] = [];
    for (const found of text.matchAll(LINES)) {
      const match = VOLUME.exec(found[1].trim());
      if (match) rows.push({ host: match[1] ?? "", path: match[2], title: (match[3] ?? "").trim(), user: match[4] ?? "" });
      else raw.push(found[1].trim());
    }
    return { rows, raw };
  }
  const line = (row: Row) => `${row.host ? `${row.host}:` : ""}${row.path || "/"}${row.title.trim() ? ` as ${row.title.trim()}` : ""}${row.user ? ` user=${row.user}` : ""}`;

  const isWiki = $derived(/^path[ \t]+\/apps\/wiki(\/|\s|$)/im.test(body));
  let rows = $state<Row[]>(parse(body).rows);
  let raw = $state<string[]>(parse(body).raw);
  let hosts = $state<Schemas["WvHost"][]>([]);
  let machines = $state<Schemas["MachineRow"][]>([]);
  let machine = $state<number | null>(null);
  let results = $state<Schemas["WvResult"][]>([]);
  let checking = $state(false);

  onMount(async () => {
    hosts = (await api.GET("/studio/api/wiki-volumes/hosts")).data ?? [];
    machines = (await api.GET("/studio/api/machines")).data ?? [];
  });

  // текст изменили руками: строки пересобираются из него
  $effect(() => {
    const parsed = parse(body);
    if (parsed.rows.map(line).join("\n") !== untrack(() => rows.map(line).join("\n"))) rows = parsed.rows;
    raw = parsed.raw;
  });

  function write() {
    const rest = body.replace(/^volume[ \t].*\n?/gim, "").replace(/\s+$/, "");
    const lines = [...rows.map((row) => `volume ${line(row)}`), ...raw.map((text) => `volume ${text}`)];
    body = `${rest}\n${lines.join("\n")}${lines.length ? "\n" : ""}`;
  }
  function add() { rows = [...rows, { host: hosts[0]?.hostname ?? "", path: "", title: "", user: "" }]; write(); }
  function drop(index: number) { rows = rows.filter((_, i) => i !== index); write(); }
  function move(index: number, step: number) {
    const to = index + step;
    if (to < 0 || to >= rows.length) return;
    const next = [...rows];
    [next[index], next[to]] = [next[to], next[index]];
    rows = next;
    write();
  }
  function pickHost(row: Row, host: string) {
    row.host = host;
    row.user = "";
    row.path = hosts.find((h) => h.hostname === host)?.exports[0] ?? row.path;
    write();
  }
  const dropRaw = (index: number) => { raw = raw.filter((_, i) => i !== index); write(); };

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const snapshot = $state.snapshot(rows);
    const chosen = machine;
    clearTimeout(timer);
    if (!snapshot.length) { results = []; return; }
    timer = setTimeout(async () => {
      checking = true;
      const { data } = await api.POST("/studio/api/wiki-volumes/check", { body: { lines: snapshot, machine: chosen } });
      checking = false;
      results = data ?? [];
    }, 400);
  });

  const hostOf = (name: string) => hosts.find((h) => h.hostname === name);
  const hasOwn = $derived(rows.some((row) => !row.host));
</script>

{#if isWiki}
  <section class="vols" aria-label="Разделы вики">
    <header>
      <b>Разделы вики</b>
      <span class="muted small">Каждая строка подключает папку к вики: своей машины или другого хоста.</span>
      <span class="spacer"></span>
      {#if hasOwn}
        <label class="muted small">Свои папки проверять на
          <select class="field" bind:value={machine} aria-label="Машина для проверки">
            <option value={null}>не выбрана</option>
            {#each machines as m (m.id)}<option value={m.id}>{m.hostname}</option>{/each}
          </select></label>
      {/if}
    </header>

    {#each rows as row, index (index)}
      {@const result = results[index]}
      <div class="row">
        <select class="field" value={row.host} aria-label="Откуда, раздел {index + 1}" onchange={(e) => pickHost(row, (e.currentTarget as HTMLSelectElement).value)}>
          <option value="">Эта машина</option>
          {#each hosts as host (host.hostname)}<option value={host.hostname}>{host.hostname}</option>{/each}
          {#if row.host && !hostOf(row.host)}<option value={row.host}>{row.host} (нет такого)</option>{/if}
        </select>
        <input class="field mono" bind:value={row.path} oninput={write} list="exports-{index}" placeholder="/srv/harbor" aria-label="Путь, раздел {index + 1}" />
        <datalist id="exports-{index}">{#each hostOf(row.host)?.exports ?? [] as path}<option value={path}></option>{/each}</datalist>
        {#if row.host}
          <select class="field" bind:value={row.user} onchange={write} aria-label="Учётка, раздел {index + 1}">
            <option value="">guest (по умолчанию)</option>
            {#each hostOf(row.host)?.accounts ?? [] as account}<option value={account.login}>{account.login}</option>{/each}
            {#if row.user && !hostOf(row.host)?.accounts.some((a) => a.login === row.user)}<option value={row.user}>{row.user} (нет такой)</option>{/if}
          </select>
        {:else}<span class="muted small own">права игрока</span>{/if}
        <input class="field" bind:value={row.title} oninput={write} placeholder={result?.title ?? "название"} aria-label="Название, раздел {index + 1}" />
        <span class="acts">
          <button class="btn ghost" aria-label="Выше" disabled={index === 0} onclick={() => move(index, -1)}>↑</button>
          <button class="btn ghost" aria-label="Ниже" disabled={index === rows.length - 1} onclick={() => move(index, 1)}>↓</button>
          <button class="btn ghost danger" aria-label="Убрать раздел {index + 1}" onclick={() => drop(index)}>×</button>
        </span>
        <p class="state" role="status">
          {#if !result}<span class="muted">{checking ? "Проверка…" : ""}</span>
          {:else if result.ok}<span class="ok">Откроется: страниц {result.pages}{result.closed ? `, закрыто правами: ${result.closed}` : ""}.</span>
          {:else}<span class="bad">{result.message}</span>{/if}
          {#if result?.duplicate}<span class="warn"> Название совпадает с другим разделом: у игрока останется один.</span>{/if}
        </p>
      </div>
    {:else}
      <p class="muted small">Разделов нет: у игрока вики будет пустой.</p>
    {/each}

    {#each raw as text, index (index)}
      <div class="rawrow"><span class="bad mono">volume {text}</span><span class="bad small">строка не разобрана: файл с ней не сохранится</span><button class="btn ghost danger" onclick={() => dropRaw(index)}>Убрать</button></div>
    {/each}

    <div class="foot">
      <button class="btn" onclick={add}>+ Раздел</button>
      <span class="muted small">Проверка идёт за выбранную учётку; страницы, закрытые ключами игрока, в ней не считаются.</span>
    </div>
  </section>
{/if}

<style>
  .vols { display: flex; flex-direction: column; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--line-soft); background: var(--panel); }
  header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .spacer { flex: 1; }
  .small { font-size: 12px; }
  .row { display: grid; grid-template-columns: minmax(110px, 0.9fr) minmax(120px, 1.2fr) minmax(110px, 0.9fr) minmax(90px, 0.8fr) auto; gap: 6px; align-items: center; }
  .row select, .row input { min-width: 0; }
  .own { padding: 0 4px; }
  .acts { display: flex; gap: 2px; }
  .acts .btn { padding: 0 8px; height: 30px; }
  .state { grid-column: 1 / -1; margin: -2px 0 4px; font-size: 12px; min-height: 16px; }
  .ok { color: var(--ok); }
  .bad { color: var(--danger); }
  .warn { color: var(--warn); }
  .rawrow { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .foot { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  @media (max-width: 900px) { .row { grid-template-columns: 1fr 1fr; } }
</style>
