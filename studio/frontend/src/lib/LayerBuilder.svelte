<script lang="ts">
  // Конструктор слоёв защиты. Текст стека (value) остаётся источником правды: конструктор правит заголовки слоёв,
  // а ответы и события слоя (всё, что под заголовком) показывает и хранит текстом. Если текст разобрать нельзя, открывается «Текст».
  import { onMount, untrack } from "svelte";
  import { api, type Schemas } from "./api";
  import CodeEditor from "./CodeEditor.svelte";
  import Hint from "./Hint.svelte";

  let { value = $bindable("") }: { value: string } = $props();

  type Kind = Schemas["StackKind"];
  type Layer = Schemas["StackLayer"];

  let kinds = $state<Kind[]>([]);
  let keys = $state<Schemas["Key"][]>([]);
  let mode = $state<"build" | "text">("build");
  let model = $state<{ preamble: string; layers: Layer[] } | null>(null);
  let info = $state({ editable: true, unsupported: "", problems: [] as Schemas["StackProblem"][] });
  let adding = $state(false);
  let shown = $state<Record<number, boolean>>({});

  let lastBuilt = value ?? "";
  let sequence = 0;
  let timer: ReturnType<typeof setTimeout>;

  const kindOf = (name: string) => kinds.find((kind) => kind.name === name);

  onMount(async () => {
    kinds = (await api.GET("/studio/api/layers/catalog")).data ?? [];
    keys = (await api.GET("/studio/api/keys")).data ?? [];
  });

  async function parse(text: string) {
    const mine = ++sequence;
    const { data } = await api.POST("/studio/api/layers/outline", { body: { text } });
    if (!data || mine !== sequence) return;
    info = { editable: data.editable, unsupported: data.unsupported, problems: data.problems };
    model = data.editable ? { preamble: data.preamble, layers: data.layers } : null;
    lastBuilt = text;
    if (!data.editable) mode = "text";
  }

  // текст изменился снаружи (режим «Текст», загрузка): разбираем заново
  $effect(() => {
    const text = value ?? "";
    if (text === lastBuilt && model) return;
    untrack(() => {
      clearTimeout(timer);
      timer = setTimeout(() => parse(text), model ? 250 : 0);
    });
  });

  // изменили в конструкторе: собираем текст
  async function push() {
    if (!model) return;
    const mine = ++sequence;
    const body = $state.snapshot(model);
    const { data } = await api.POST("/studio/api/layers/build", { body });
    if (!data || mine !== sequence) return;
    lastBuilt = data.text;
    value = data.text;
  }

  function setValue(layer: Layer, name: string, text: string) {
    if (text === "") delete layer.values[name];
    else layer.values[name] = text;
    push();
  }

  function setMove(layer: Layer, kind: string) {
    layer.move = kind ? { kind, target: layer.move?.target ?? "" } : null;
    push();
  }

  function add(kind: Kind) {
    model?.layers.unshift({ name: kind.name, values: {}, move: null, body: "" });
    adding = false;
    push();
  }

  function shift(index: number, by: number) {
    if (!model) return;
    const to = index + by;
    if (to < 0 || to >= model.layers.length) return;
    [model.layers[index], model.layers[to]] = [model.layers[to], model.layers[index]];
    push();
  }

  function remove(index: number) {
    model?.layers.splice(index, 1);
    push();
  }
</script>

<div class="builder">
  <div class="bar">
    <div class="seg" role="tablist">
      <button class:on={mode === "build"} disabled={!info.editable} title={info.editable ? "" : info.unsupported || "В тексте есть ошибки"} onclick={() => (mode = "build")}>Конструктор</button>
      <button class:on={mode === "text"} onclick={() => (mode = "text")}>Текст</button>
    </div>
    {#if mode === "build" && model}
      <div class="add">
        <button class="btn" onclick={() => (adding = !adding)}>+ Слой</button>
        {#if adding}
          <div class="palette">
            {#each kinds as kind (kind.name)}
              <button class="kind" onclick={() => add(kind)}><b>{kind.title}</b><span class="muted small">{kind.summary}</span></button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  {#if !info.editable && (info.unsupported || info.problems.length)}
    <p class="warn small">
      Конструктор недоступен: {info.unsupported || `в тексте ошибки (${info.problems.map((row) => `стр. ${row.line}`).join(", ")})`}.
      Поправьте текст, и он снова включится.
    </p>
  {/if}

  {#if mode === "text" || !model}
    <div class="editor"><CodeEditor bind:value /></div>
  {:else}
    <p class="muted small first">Слои идут сверху вниз: верхний игрок снимает первым.</p>
    {#each model.layers as layer, index (index)}
      {@const kind = kindOf(layer.name)}
      {@const open = shown[index] ?? !!layer.body.trim()}
      <section class="layer">
        <header>
          <span class="num">{index + 1}</span>
          <b>{kind?.title ?? layer.name}</b>
          <span class="spacer"></span>
          <button class="icon" aria-label="Выше" disabled={index === 0} onclick={() => shift(index, -1)}>↑</button>
          <button class="icon" aria-label="Ниже" disabled={index === model.layers.length - 1} onclick={() => shift(index, 1)}>↓</button>
          <button class="icon danger" aria-label="Убрать слой" onclick={() => remove(index)}>✕</button>
        </header>
        {#if kind?.summary}<p class="muted small">{kind.summary}</p>{/if}
        {#if kind?.params.length}
          <div class="fields">
            {#each kind.params as param (param.name)}
              <label>
                <span class="label">{param.label}{param.required ? " *" : ""}{#if param.help}<Hint text={param.help} />{/if}</span>
                <input
                  class="field" class:mono={param.type === "str"} type={param.type === "int" || param.type === "float" ? "number" : "text"}
                  list={param.name === "key" ? "layer-keys" : undefined} placeholder={param.default ? `по умолчанию ${param.default}` : ""}
                  value={layer.values[param.name] ?? ""} oninput={(event) => setValue(layer, param.name, event.currentTarget.value)}
                />
              </label>
            {/each}
          </div>
        {/if}
        <div class="move">
          <label>
            <span class="label">После снятия слоя файл<Hint text="Файл можно переименовать или оставить копию под новым именем: игрок увидит результат сразу после снятия." /></span>
            <select class="field" value={layer.move?.kind ?? ""} onchange={(event) => setMove(layer, event.currentTarget.value)}>
              <option value="">остаётся как есть</option>
              <option value="rename">переименуется в…</option>
              <option value="copy">скопируется в…</option>
            </select>
          </label>
          {#if layer.move}
            <label>
              <span class="label">Новый путь</span>
              <input class="field mono" placeholder="data.bin или /home/data.bin" value={layer.move.target} oninput={(event) => { layer.move!.target = event.currentTarget.value; push(); }} />
            </label>
          {/if}
        </div>
        <button class="more" onclick={() => (shown[index] = !open)}>
          {open ? "▾" : "▸"} Ответы и события{layer.body.trim() ? " (заполнено)" : ""}
        </button>
        {#if open}
          <textarea
            class="field mono body" rows="5" spellcheck="false" value={layer.body}
            placeholder={'file: Header checksum mismatch\non remove: say "Готово"'}
            oninput={(event) => { layer.body = event.currentTarget.value; push(); }}
          ></textarea>
          <p class="muted small">Своя реплика слоя на команду (<span class="mono">file: текст</span>) и хуки (<span class="mono">on remove:</span>, <span class="mono">on fail:</span>…). Пока пишется текстом.</p>
        {/if}
      </section>
    {:else}
      <p class="muted empty">Слоёв нет: файл открыт игроку целиком. Добавьте первый слой кнопкой «+ Слой».</p>
    {/each}
    {#if model.preamble.trim()}
      <p class="muted small">Комментарии перед слоями сохраняются в тексте: <span class="mono">{model.preamble.split("\n")[0]}</span>{model.preamble.includes("\n") ? "…" : ""}</p>
    {/if}
  {/if}
  <datalist id="layer-keys">{#each keys as key (key.slug)}<option value={key.slug}>{key.description}</option>{/each}</datalist>
</div>

<style>
  .builder { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
  .bar { display: flex; align-items: center; gap: 10px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: var(--radius-s); overflow: hidden; }
  .seg button { padding: 4px 12px; border: 0; background: none; color: var(--muted); cursor: pointer; }
  .seg button.on { background: var(--panel-2); color: var(--text); }
  .seg button:disabled { opacity: 0.45; cursor: not-allowed; }
  .add { position: relative; margin-left: auto; }
  .palette { position: absolute; right: 0; top: 100%; z-index: 20; width: 360px; max-height: 60vh; overflow-y: auto; margin-top: 4px; padding: 4px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
  .kind { display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 8px 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); text-align: left; cursor: pointer; }
  .kind:hover { background: var(--panel); }
  .warn { margin: 0; color: var(--warn); }
  .first { margin: 0; }
  .editor { min-height: 220px; }
  .layer { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel-2); }
  .layer header { display: flex; align-items: center; gap: 8px; }
  .layer p { margin: 0; }
  .num { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: var(--panel); color: var(--muted); font-size: 11px; }
  .spacer { flex: 1; }
  .icon { width: 26px; height: 26px; border: 1px solid var(--line); border-radius: var(--radius-s); background: none; color: var(--muted); cursor: pointer; }
  .icon:hover:not(:disabled) { color: var(--text); border-color: var(--accent); }
  .icon:disabled { opacity: 0.35; cursor: default; }
  .icon.danger:hover { color: var(--danger); border-color: var(--danger); }
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
  .move { display: grid; grid-template-columns: 220px 1fr; gap: 10px; }
  .more { align-self: flex-start; padding: 0; border: 0; background: none; color: var(--muted); cursor: pointer; }
  .more:hover { color: var(--text); }
  .body { width: 100%; resize: vertical; }
  .empty { padding: 12px 0; }
</style>
