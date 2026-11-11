<script lang="ts">
  import { untrack } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import DraftState from "../../lib/DraftState.svelte";
  import { SharedForm } from "../../lib/shared.svelte";
  import { tileUrl, WALL_MODES, WALL_PATTERNS, WALLPAPER_DEFAULT, type Wallpaper } from "../../lib/wallpaper";
  import WallpaperPicker from "./WallpaperPicker.svelte";

  type System = Schemas["SystemOut"];
  type Done = (data: System | undefined, error: unknown, text: string) => void;

  let { system, errors, done, onstate }: { system: System; errors: Record<string, string[]>; done: Done; onstate: (state: { dirty: boolean; share: typeof share; save: () => unknown } | null) => void } = $props();

  let look = $state({ style: "aether", tokens: {} as Record<string, string>, wallpaper: { ...WALLPAPER_DEFAULT } as Wallpaper });
  let picking = $state(false);
  let lookSaved = $state("");
  let base = $state<typeof look | null>(null);                  // сохранённое: им наполняется общий черновик
  const share = new SharedForm({ room: () => `systems/${system.code}`, scope: () => "style", draft: () => look, base: () => base });
  const lookDirty = $derived(JSON.stringify(look) !== lookSaved);
  const groups = $derived([...new Set(system.token_info.map((t) => t.group))]);
  const HEX6 = /^#[0-9a-fA-F]{6}$/;

  async function saveLook() {
    const { data, error } = await api.PUT("/studio/api/systems/{code}/style", { params: { path: { code: system.code } }, body: look });
    if (data) share.markSaved();
    done(data, error, "Стиль сохранён.");
  }

  function setToken(name: string, value: string) {
    look.tokens = value.trim() ? { ...look.tokens, [name]: value } : Object.fromEntries(Object.entries(look.tokens).filter(([key]) => key !== name));
  }

  // предпросмотр: настоящий рабочий стол в рамке, адрес с несохранёнными стилем и токенами; перезагружается с паузой, чтобы не мигать
  const PV_KEY = "studio.styleDeskPreview";
  let deskPreview = $state((() => { try { return localStorage.getItem(PV_KEY) !== "off"; } catch { return true; } })());
  function toggleDeskPreview() {
    deskPreview = !deskPreview;
    try { localStorage.setItem(PV_KEY, deskPreview ? "on" : "off"); } catch { /* память браузера может быть закрыта */ }
  }
  let previewSrc = $state("");
  let previewWidth = $state(0);
  let deskTimer: ReturnType<typeof setTimeout>;
  const PREVIEW_W = 1100;
  const PREVIEW_H = 640;

  $effect(() => {
    if (!deskPreview) return;
    const url = `${system.preview_url}?preview_os=${encodeURIComponent(system.code)}&preview_style=${encodeURIComponent(look.style)}&preview_tokens=${encodeURIComponent(JSON.stringify(look.tokens))}&preview_wall=${encodeURIComponent(JSON.stringify(look.wallpaper))}`;
    clearTimeout(deskTimer);
    deskTimer = setTimeout(() => (previewSrc = url), 350);
    return () => clearTimeout(deskTimer);
  });

  // значения токенов у выбранного (а не сохранённого) стиля: у каждого стиля свои
  const styleDefaults = $derived(system.style_defaults[look.style] ?? {});
  const def = (token: Schemas["TokenInfo"]) => styleDefaults[token.name] ?? token.default;
  const pickerValue = (token: Schemas["TokenInfo"]) => (HEX6.test(look.tokens[token.name] ?? "") ? look.tokens[token.name] : HEX6.test(def(token)) ? def(token) : "#000000");
  // картинка рабочего стола: сотрудник видит и ещё не сохранённый файл (?file=)
  const wallUrl = (fileId: string) => `${(window as unknown as { STUDIO: { site: string } }).STUDIO.site}wallpaper/${encodeURIComponent(system.code)}/?file=${encodeURIComponent(fileId)}`;
  const desktopUrl = $derived(`${(window as unknown as { STUDIO: { site: string } }).STUDIO.site}?preview_os=${system.code}`);

  // сервер вернул ОС заново (после сохранения): берём значения оттуда
  $effect(() => {
    const data = system;
    untrack(() => {
      const next = { style: data.style, tokens: { ...data.style_tokens }, wallpaper: { ...WALLPAPER_DEFAULT, ...data.wallpaper } };
      if (!share.ready) look = { style: next.style, tokens: { ...next.tokens }, wallpaper: { ...next.wallpaper } };
      lookSaved = JSON.stringify(next);
      base = next;
    });
  });

  // кнопка «Сохранить» живёт в шапке ОС: вкладка сообщает ей своё состояние
  $effect(() => {
    onstate({ dirty: lookDirty, share, save: saveLook });
    return () => onstate(null);
  });

  guardUnsaved(() => !share.ready && lookSaved !== "" && lookDirty);
</script>

  <div class="stylegrid" class:nopv={!deskPreview}>
  <div class="stylemain">
  <div class="block">
    <h3>Стиль рабочего стола и окон <a class="more" href={desktopUrl} target="_blank" rel="noopener">посмотреть на рабочем столе →</a>
      {#if !deskPreview}<button class="btn ghost small" onclick={toggleDeskPreview}>Показать предпросмотр</button>{/if}</h3>
    <p class="muted small">Стиль задаёт раскладку и вид элементов: панель, окна, кнопки, иконки. Стили готовятся в коде, здесь выбирается один из них. Токены ниже переназначают цвета, шрифты и форму поверх выбранного стиля.</p>
    <div class="styles">
      {#each system.styles as item}
        <label class="stylecard" class:on={look.style === item.slug}>
          <input type="radio" name="style" value={item.slug} bind:group={look.style} />
          <b>{item.label}</b>
          <span class="muted small">{item.description}</span>
        </label>
      {/each}
    </div>
  </div>

  <div class="block">
    <h3>Картинка и узор</h3>
    <p class="muted small">Лежат под окнами и значками, не зависят от выбранного стиля. Цвет под ними это токен «Фон рабочего стола» ниже.</p>
    <div class="wall">
      <div class="wallrow">
        <div class="wthumb" class:empty={!look.wallpaper.file_id}>
          {#if look.wallpaper.file_id}<img src={wallUrl(look.wallpaper.file_id)} alt="" />{:else}<span class="muted small">нет</span>{/if}
        </div>
        <div class="wmeta">
          <b>{look.wallpaper.file_id ? look.wallpaper.file_name || "Файл выбран" : "Картинка не выбрана"}</b>
          <span class="muted small">Файл из хранилища (Nextcloud, папка AETHER). Игрок видит его без проверки ключей.</span>
          <div class="wacts">
            <button class="btn" onclick={() => (picking = true)}>{look.wallpaper.file_id ? "Заменить…" : "Выбрать из Nextcloud…"}</button>
            {#if look.wallpaper.file_id}<button class="btn ghost" onclick={() => { look.wallpaper.file_id = ""; look.wallpaper.file_name = ""; }}>Убрать</button>{/if}
          </div>
        </div>
      </div>
      {#if look.wallpaper.file_id}
        <div class="wctl">
          <span class="wlabel">Режим</span>
          <div class="seg" role="radiogroup" aria-label="Режим картинки">
            {#each WALL_MODES as item (item.key)}
              <button type="button" role="radio" aria-checked={look.wallpaper.mode === item.key} class:on={look.wallpaper.mode === item.key} title={item.hint} onclick={() => (look.wallpaper.mode = item.key)}>{item.label}</button>
            {/each}
          </div>
          <span class="wlabel">Прозрачность</span>
          <div class="range"><input type="range" min="0" max="100" step="5" bind:value={look.wallpaper.opacity} aria-label="Прозрачность картинки" /><output>{look.wallpaper.opacity}%</output></div>
        </div>
      {/if}

      <div class="wctl">
        <span class="wlabel">Узор</span>
        <div class="patterns" role="radiogroup" aria-label="Узор поверх картинки">
          {#each WALL_PATTERNS as item (item.key)}
            <button type="button" role="radio" aria-checked={look.wallpaper.pattern === item.key} class="pat" class:on={look.wallpaper.pattern === item.key} onclick={() => (look.wallpaper.pattern = item.key)}>
              <span class="swatchpat" style:background-image={item.key === "none" ? "none" : `url("${tileUrl(item.key, "#b0b0b0", 16)}")`}></span>{item.label}
            </button>
          {/each}
        </div>
        {#if look.wallpaper.pattern !== "none"}
          <span class="wlabel">Цвет</span>
          <input class="picker" type="color" bind:value={look.wallpaper.pattern_color} aria-label="Цвет узора" />
          <span class="wlabel">Шаг</span>
          <div class="range"><input type="range" min="8" max="120" step="2" bind:value={look.wallpaper.pattern_size} aria-label="Шаг узора" /><output>{look.wallpaper.pattern_size} px</output></div>
          <span class="wlabel">Прозрачность</span>
          <div class="range"><input type="range" min="0" max="100" step="5" bind:value={look.wallpaper.pattern_opacity} aria-label="Прозрачность узора" /><output>{look.wallpaper.pattern_opacity}%</output></div>
        {/if}
      </div>
      {#if errors.wallpaper}{#each errors.wallpaper as text}<p class="warn small">{text}</p>{/each}{/if}
    </div>
  </div>

  {#each groups as group}
    <div class="block">
      <h3>{group}</h3>
      <div class="tokens">
        {#each system.token_info.filter((t) => t.group === group) as token (token.name)}
          <div class="token" class:own={look.tokens[token.name]}>
            <span>{token.label}<span class="mono muted small"> {token.name}</span></span>
            {#if token.kind === "font"}
              <select class="field" value={look.tokens[token.name] ?? ""} onchange={(e) => setToken(token.name, e.currentTarget.value)}>
                <option value="">как в стиле ({def(token)})</option>
                {#each system.fonts as font}<option value={font.value}>{font.label}</option>{/each}
              </select>
            {:else}
              <div class="tokeninput">
                {#if token.kind === "color"}
                  <span class="swatch" style:background={def(token)} title="В стиле: {def(token)}"></span>
                  <span class="arrow" class:dim={!look.tokens[token.name]}>→</span>
                  <input class="picker" type="color" value={pickerValue(token)} oninput={(e) => setToken(token.name, e.currentTarget.value)} title={look.tokens[token.name] ? `Свой: ${look.tokens[token.name]}` : "В стиле такой же, как слева"} />
                {/if}
                <input class="field mono" placeholder={def(token)} value={look.tokens[token.name] ?? ""} oninput={(e) => setToken(token.name, e.currentTarget.value)} class:bad={errors.style} />
              </div>
            {/if}
            <button class="btn ghost" disabled={!look.tokens[token.name]} onclick={() => setToken(token.name, "")} title="Как в стиле">×</button>
          </div>
        {/each}
      </div>
    </div>
  {/each}
  {#if errors.style}{#each errors.style as text}<p class="warn small">{text}</p>{/each}{/if}
  </div>
  {#if deskPreview}
  <aside class="stylepreview">
    <div class="block">
      <h3>Предпросмотр <span class="muted small">с несохранёнными изменениями</span> <button class="btn ghost small hidepv" onclick={toggleDeskPreview}>Скрыть</button></h3>
      <div class="pvframe" bind:clientWidth={previewWidth} style:height="{(previewWidth * PREVIEW_H) / PREVIEW_W}px">
        {#if previewSrc}
          <iframe title="Предпросмотр рабочего стола" src={previewSrc} style:width="{PREVIEW_W}px" style:height="{PREVIEW_H}px" style:transform="scale({previewWidth / PREVIEW_W})"></iframe>
        {/if}
      </div>
      <p class="muted small">Настоящий рабочий стол с тестовыми приложениями. Внутри можно пользоваться меню и открывать окна.</p>
    </div>
  </aside>
  {/if}
  </div>

{#if picking}
  <WallpaperPicker current={look.wallpaper.file_id} previewUrl={wallUrl} onclose={() => (picking = false)}
    onpick={(fileId, name) => { look.wallpaper.file_id = fileId; look.wallpaper.file_name = name; picking = false; }} />
{/if}

<style>
  .small { font-size: 12px; margin: 0; }
  .warn { color: var(--warn); margin: 0; }
  .more { margin-left: auto; font-size: 12px; text-transform: none; letter-spacing: 0; }
  .hidepv { margin-left: auto; text-transform: none; letter-spacing: 0; }
  .styles { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
  .stylecard { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); cursor: pointer; }
  .stylecard.on { border-color: var(--accent); background: var(--accent-soft); }
  .stylecard input { display: none; }
  .tokens { display: flex; flex-direction: column; gap: 6px; }
  .token { display: grid; grid-template-columns: minmax(0, 1fr) max-content; gap: 4px 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .token:last-child { border-bottom: 0; }
  .token > span:first-child { grid-column: 1 / -1; }
  .token.own > span:first-child { color: var(--accent); }
  .token select { width: 100%; min-width: 0; }
  .tokeninput { display: flex; gap: 6px; align-items: center; min-width: 0; }
  .tokeninput .field { flex: 1; min-width: 0; }
  .stylegrid.nopv { grid-template-columns: minmax(0, 1fr); }
  .stylegrid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 560px); gap: 16px; align-items: start; }
  .stylemain { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .stylepreview { position: sticky; top: 8px; }
  .pvframe { position: relative; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius-s); background: #000; }
  .pvframe iframe { position: absolute; top: 0; left: 0; border: 0; transform-origin: 0 0; }
  .swatch { flex: none; width: 22px; height: 22px; border: 1px solid var(--line); border-radius: var(--radius-s); background-clip: padding-box; }
  .arrow { color: var(--muted); font-size: 0.8rem; }
  .arrow.dim { opacity: 0.35; }
  .picker { width: 34px; height: 32px; padding: 0; border: 1px solid var(--line); border-radius: var(--radius-s); background: none; cursor: pointer; }
  .field.bad { border-color: var(--danger); }
  .wall { display: flex; flex-direction: column; gap: 12px; }
  .wallrow { display: grid; grid-template-columns: auto 1fr; gap: 14px; align-items: center; }
  .wthumb { width: 120px; height: 76px; display: grid; place-items: center; overflow: hidden; border-radius: var(--radius-s); border: 1px solid var(--line-soft); background: repeating-conic-gradient(var(--panel-2) 0 25%, var(--bg) 0 50%) 0 0 / 14px 14px; }
  .wthumb.empty { border-style: dashed; }
  .wthumb img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .wmeta { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .wmeta b { overflow-wrap: anywhere; }
  .wacts { display: flex; gap: 8px; margin-top: 4px; }
  .wctl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 8px 14px; align-items: center; }
  .wlabel { color: var(--muted); font-size: 12px; }
  .seg { display: inline-flex; width: max-content; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 4px 14px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .range { display: flex; align-items: center; gap: 10px; }
  .range input { flex: 1; max-width: 280px; accent-color: var(--accent); }
  .range output { min-width: 52px; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12.5px; }
  .patterns { display: flex; gap: 8px; flex-wrap: wrap; }
  .pat { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
  .pat:hover { color: var(--text); border-color: var(--line); }
  .pat.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .swatchpat { width: 48px; height: 32px; border-radius: 4px; background-color: var(--bg); background-size: 16px 16px; border: 1px solid var(--line-soft); }
  @media (max-width: 1280px) { .stylegrid { grid-template-columns: minmax(0, 1fr); } .stylepreview { position: static; } }
</style>
