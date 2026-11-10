<script lang="ts">
  import { untrack } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import DraftState from "../../lib/DraftState.svelte";
  import { SharedForm } from "../../lib/shared.svelte";

  type System = Schemas["SystemOut"];
  type Done = (data: System | undefined, error: unknown, text: string) => void;

  let { system, errors, done }: { system: System; errors: Record<string, string[]>; done: Done } = $props();

  let look = $state({ style: "aether", tokens: {} as Record<string, string> });
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
    const url = `${system.preview_url}?preview_os=${encodeURIComponent(system.code)}&preview_style=${encodeURIComponent(look.style)}&preview_tokens=${encodeURIComponent(JSON.stringify(look.tokens))}`;
    clearTimeout(deskTimer);
    deskTimer = setTimeout(() => (previewSrc = url), 350);
    return () => clearTimeout(deskTimer);
  });

  // значения токенов у выбранного (а не сохранённого) стиля: у каждого стиля свои
  const styleDefaults = $derived(system.style_defaults[look.style] ?? {});
  const def = (token: Schemas["TokenInfo"]) => styleDefaults[token.name] ?? token.default;
  const pickerValue = (token: Schemas["TokenInfo"]) => (HEX6.test(look.tokens[token.name] ?? "") ? look.tokens[token.name] : HEX6.test(def(token)) ? def(token) : "#000000");
  const desktopUrl = $derived(`${(window as unknown as { STUDIO: { site: string } }).STUDIO.site}?preview_os=${system.code}`);

  // сервер вернул ОС заново (после сохранения): берём значения оттуда
  $effect(() => {
    const data = system;
    untrack(() => {
      const next = { style: data.style, tokens: { ...data.style_tokens } };
      if (!share.ready) look = { style: next.style, tokens: { ...next.tokens } };
      lookSaved = JSON.stringify(next);
      base = next;
    });
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
  <div class="saverow"><DraftState {share} dirty={lookDirty} saved="" /><button class="btn primary" disabled={!lookDirty} onclick={saveLook}>Сохранить стиль</button></div>
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

<style>
  .saverow { display: flex; align-items: center; justify-content: flex-end; gap: 12px; }
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
  @media (max-width: 1280px) { .stylegrid { grid-template-columns: minmax(0, 1fr); } .stylepreview { position: static; } }
</style>
