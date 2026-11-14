<script lang="ts">
  // Вариант ответа игрока: подпись, текст для набора с предпросмотром, когда открыт, что приложить, сколько попыток и исходы.
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import type { Schemas } from "../../lib/api";
  import Actions from "./Actions.svelte";
  import { socketLabel, socketsOf, type Action, type VariantDraft } from "./doc";

  let { variant, steps, picks, onchange, onremove, onmove, open = $bindable(false), index, count }: {
    variant: VariantDraft; steps: string[]; picks: Schemas["MlPicks"] | null; index: number; count: number; open?: boolean;
    onchange: (next: VariantDraft) => void; onremove: () => void; onmove: (by: number) => void;
  } = $props();

  const set = (patch: Partial<VariantDraft>) => onchange({ ...variant, ...patch });
  const sockets = $derived(socketsOf(variant));
  const letters = $derived((picks?.items ?? []).filter((i) => i.format === "msg"));

  type Piece = { text?: string; hidden?: number; choices?: string[] };
  const preview = $derived.by(() => {
    const out: Piece[] = [];
    const text = variant.text ?? "";
    let last = 0;
    for (const found of text.matchAll(/\{\{(.+?)\}\}|\[\[(.+?)\]\]/gs)) {
      if (found.index! > last) out.push({ text: text.slice(last, found.index) });
      if (found[1] !== undefined) out.push({ hidden: found[1].length });
      else out.push({ choices: found[2].split("|").map((o) => o.trim()).filter(Boolean) });
      last = found.index! + found[0].length;
    }
    if (last < text.length) out.push({ text: text.slice(last) });
    return out;
  });

  const flags = (value: string) => value.split(",").map((f) => f.trim()).filter(Boolean);
  function setOutcome(socket: string, actions: Action[]) {
    const outcomes = { ...variant.outcomes };
    if (actions.length) outcomes[socket] = actions;
    else delete outcomes[socket];
    set({ outcomes });
  }
  const summary = (socket: string) => (variant.outcomes?.[socket] ?? []).length;
</script>

<div class="variant" class:open>
  <div class="bar">
    <button class="toggle" onclick={() => (open = !open)} aria-expanded={open}>
      <span class="chev">{open ? "▾" : "▸"}</span>
      <span class="name">{variant.title || "Новый вариант"}</span>
      {#if variant.condition || variant.need_flags.length || variant.deny_flags.length || variant.account}<span class="lock" title="Открывается по условию; закрытый {variant.closed === "hidden" ? "скрыт" : "виден как ???"}">условие</span>{/if}
    </button>
    <button class="icon" disabled={index === 0} onclick={() => onmove(-1)} aria-label="Выше" title="Выше">↑</button>
    <button class="icon" disabled={index === count - 1} onclick={() => onmove(1)} aria-label="Ниже" title="Ниже">↓</button>
    <button class="icon danger" onclick={onremove} aria-label="Удалить вариант" title="Удалить вариант">✕</button>
  </div>

  {#if open}
    <div class="body">
      <label><span class="label">Подпись в списке ответов</span>
        <input class="field" value={variant.title} oninput={(e) => set({ title: e.currentTarget.value })} placeholder="Назвать пароль" /></label>

      <div class="seg" role="radiogroup" aria-label="Режим">
        <label class:on={variant.mode === "reply"}><input type="radio" checked={variant.mode === "reply"} onchange={() => set({ mode: "reply", forward_of: null })} />Ответ или новое письмо</label>
        <label class:on={variant.mode === "forward"}><input type="radio" checked={variant.mode === "forward"} onchange={() => set({ mode: "forward" })} />Пересылка письма</label>
      </div>
      {#if variant.mode === "forward"}
        <label><span class="label">Какое письмо игрок пересылает</span>
          <select class="field" value={variant.forward_of ?? ""} onchange={(e) => set({ forward_of: e.currentTarget.value || null })}>
            <option value="">— письмо —</option>
            {#if variant.forward_of && !letters.some((l) => l.slug === variant.forward_of)}<option value={variant.forward_of}>{variant.forward_of}</option>{/if}
            {#each letters as l (l.slug)}<option value={l.slug}>{l.slug} · {l.subject}</option>{/each}
          </select></label>
      {/if}

      <label><span class="label">Текст, который игрок набирает</span>
        <textarea class="field mono" rows="3" value={variant.text} oninput={(e) => set({ text: e.currentTarget.value })}
                  placeholder={"Password: {{hunter2}}. Dock [[7|9]], please."}></textarea></label>
      <p class="hint muted">{"{{секрет}}"}: игрок видит только длину и должен знать сам. {"[[a|b]]"}: выбор слова, у каждого слова свой выход. Пустой текст: вариант отправляется сразу.</p>
      {#if preview.length}
        <div class="preview" aria-label="Как увидит игрок">
          {#each preview as piece, i (i)}
            {#if piece.text !== undefined}<span>{piece.text}</span>
            {:else if piece.hidden !== undefined}<span class="secret" title="Секрет: {piece.hidden} знаков">{"•".repeat(piece.hidden)}</span>
            {:else}<span class="choice">{piece.choices?.join(" / ")}</span>{/if}
          {/each}
        </div>
      {/if}

      <details>
        <summary>Когда доступен{#if variant.condition || variant.need_flags.length || variant.deny_flags.length || variant.account}<span class="dot"></span>{/if}</summary>
        <div class="group">
          <div><span class="label">Условие по ключам</span><AccessBuilder bind:value={() => variant.condition ?? "", (next) => { if (next !== (variant.condition ?? "")) set({ condition: next }); }} /></div>
          <label><span class="label">Нужны метки (через запятую)</span>
            <input class="field" value={variant.need_flags.join(", ")} onchange={(e) => set({ need_flags: flags(e.currentTarget.value) })} list="mail-flags" /></label>
          <label><span class="label">Мешают метки</span>
            <input class="field" value={variant.deny_flags.join(", ")} onchange={(e) => set({ deny_flags: flags(e.currentTarget.value) })} list="mail-flags" /></label>
          <label><span class="label">Только если пишет с учётки</span>
            <select class="field" value={variant.account ?? ""} onchange={(e) => set({ account: +e.currentTarget.value || null })}>
              <option value="">с любой</option>
              {#each picks?.accounts ?? [] as a (a.id)}<option value={a.id}>{a.label}</option>{/each}
            </select></label>
          <div class="seg" role="radiogroup" aria-label="Если недоступен">
            <label class:on={variant.closed === "mystery"}><input type="radio" checked={variant.closed === "mystery"} onchange={() => set({ closed: "mystery" })} />Закрытый виден как «???»</label>
            <label class:on={variant.closed === "hidden"}><input type="radio" checked={variant.closed === "hidden"} onchange={() => set({ closed: "hidden" })} />Скрыт</label>
          </div>
        </div>
      </details>

      <details>
        <summary>Вложение и попытки{#if variant.attachment?.kind || variant.max_attempts}<span class="dot"></span>{/if}</summary>
        <div class="group">
          <div class="row">
            <select class="field" value={variant.attachment?.kind ?? ""} onchange={(e) => set({ attachment: { kind: e.currentTarget.value, slug: variant.attachment?.slug ?? "" } })} aria-label="Что приложить">
              <option value="">ничего прикладывать не нужно</option>
              <option value="item">этот объект</option>
              <option value="key">этот ключ</option>
              <option value="signed">документ, подписанный ключом</option>
            </select>
            {#if variant.attachment?.kind}
              <input class="field" list={variant.attachment.kind === "item" ? undefined : "mail-keys"} value={variant.attachment.slug}
                     oninput={(e) => set({ attachment: { kind: variant.attachment.kind, slug: e.currentTarget.value.trim() } })} placeholder="слаг" aria-label="Слаг" />
            {/if}
          </div>
          <label class="inline"><span class="label">Попыток</span>
            <input class="field num" type="number" min="0" value={variant.max_attempts} oninput={(e) => set({ max_attempts: Math.max(0, +e.currentTarget.value || 0) })} />
            <span class="muted small">0: без ограничения</span></label>
        </div>
      </details>

      <div class="outcomes">
        <span class="label">Исходы</span>
        {#each sockets as socket (socket)}
          <div class="outcome" class:bad={socket === "wrong" || socket === "exhausted"}>
            <div class="socket">{socketLabel(socket)}{#if socket === "ok" && sockets.some((s) => s.startsWith("word:"))}<span class="muted small"> · если у слова нет своих</span>{/if}
              {#if socket === "exhausted" && !summary("exhausted")}<span class="muted small"> · без своих действий берёт «неверно»</span>{/if}</div>
            <Actions {steps} bind:actions={() => variant.outcomes?.[socket] ?? [], (next) => setOutcome(socket, next)} />
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .variant { border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel); }
  .variant.open { border-color: var(--line); }
  .bar { display: flex; align-items: center; gap: 2px; padding: 2px 4px; }
  .toggle { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; padding: 6px 4px; border: 0; background: none; color: var(--text); cursor: pointer; font: inherit; text-align: left; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chev { color: var(--muted); width: 10px; }
  .lock { color: var(--warn); font-size: 11.5px; white-space: nowrap; }
  .icon { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 2px 6px; border-radius: 4px; }
  .icon:hover:not(:disabled) { color: var(--text); background: var(--panel-2); }
  .icon.danger:hover { color: var(--danger); }
  .icon:disabled { opacity: 0.35; cursor: default; }
  .body { display: flex; flex-direction: column; gap: 10px; padding: 4px 10px 12px; }
  label { display: flex; flex-direction: column; gap: 4px; }
  label.inline { flex-direction: row; align-items: center; gap: 8px; }
  .num { width: 70px; }
  textarea { resize: vertical; }
  .mono { font-family: var(--mono); font-size: 12.5px; }
  .hint { margin: -4px 0 0; font-size: 11.5px; }
  .preview { padding: 8px 10px; border-radius: var(--radius-s); background: var(--bg); font-family: var(--mono); font-size: 12.5px; color: var(--faint); white-space: pre-wrap; line-height: 1.7; }
  .secret { letter-spacing: 2px; color: var(--muted); }
  .choice { padding: 1px 6px; border: 1px dashed var(--accent); border-radius: 4px; color: var(--accent); }
  .seg { display: flex; flex-wrap: wrap; gap: 4px; }
  .seg label { flex-direction: row; align-items: center; padding: 4px 10px; border: 1px solid var(--line-soft); border-radius: 999px; color: var(--muted); cursor: pointer; font-size: 12.5px; }
  .seg label.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .seg input { position: absolute; opacity: 0; pointer-events: none; }
  .seg label:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  details { border-top: 1px solid var(--line-soft); padding-top: 8px; }
  summary { cursor: pointer; color: var(--muted); font-size: 12.5px; display: flex; align-items: center; gap: 6px; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); }
  .group { display: flex; flex-direction: column; gap: 8px; padding-top: 8px; }
  .row { display: flex; gap: 6px; }
  .row .field { flex: 1; min-width: 0; }
  .outcomes { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--line-soft); padding-top: 8px; }
  .outcome { display: flex; flex-direction: column; gap: 5px; padding-left: 8px; border-left: 2px solid var(--accent); }
  .outcome.bad { border-left-color: var(--danger); }
  .socket { font-size: 12.5px; font-weight: 600; }
  .small { font-size: 11.5px; font-weight: 400; }
</style>
