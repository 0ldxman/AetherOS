<script lang="ts">
  // Песочница: пройти сценарий как игрок по черновику, ничего не меняя в мире. Ключи, метки и учётка задаются вручную;
  // переход на шаг, метки и ключи из исходов применяются здесь же, так можно пройти цепочку до конца.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { toast } from "../../lib/toast.svelte";
  import { describe, socketLabel, type Action, type StepDraft, type VariantDraft } from "./doc";

  let { steps, current = $bindable(""), picks }: { steps: StepDraft[]; current: string; picks: Schemas["MlPicks"] | null } = $props();

  let allKeys = $state<Schemas["Key"][]>([]);
  let keys = $state<string[]>([]);
  let flags = $state<string[]>([]);
  let account = $state<number | null>(null);
  let used = $state<Record<string, number>>({});
  let pick = $state<number | null>(null);
  let typed = $state("");
  let attachment = $state("");
  let offers = $state<Schemas["MlOffer"][]>([]);
  let result = $state<Schemas["MlResult"] | null>(null);
  let log = $state<{ step: string; text: string; kind: string }[]>([]);
  let newFlag = $state("");

  onMount(async () => {
    allKeys = (await api.GET("/studio/api/keys")).data ?? [];
  });

  const step = $derived(steps.find((s) => s.key === current) ?? steps[0]);
  const variants = $derived<VariantDraft[]>(step?.variants ?? []);
  const plain = (list: VariantDraft[]) => list.map(({ key: _k, ...v }) => v);
  const usedOf = (index: number) => used[`${step?.key}:${index}`] ?? 0;

  async function run(withPick: number | null) {
    if (!step) return;
    const { data, error } = await api.POST("/studio/api/mail/try", { body: {
      variants: plain($state.snapshot(variants) as VariantDraft[]), keys, flags, account, pick: withPick, typed, used: withPick === null ? 0 : usedOf(withPick),
      attachment: attachment || null,
    } });
    if (error || !data) return toast(problem(error, "Песочница не ответила."), "error");
    offers = data.offers;
    return data.result;
  }

  // варианты пересчитываются при любой правке шага, ключей и меток
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    JSON.stringify(variants);
    keys.length; flags.length; account;
    clearTimeout(timer);
    timer = setTimeout(() => run(null), 250);
  });

  function choose(index: number) {
    pick = index;
    typed = "";
    attachment = "";
    result = null;
  }

  async function send() {
    if (pick === null || !step) return;
    const index = pick;
    const res = await run(index);
    if (!res) return;
    result = res;
    log = [{ step: step.name, text: `${variants[index]?.title}: ${typed || "(без текста)"}`, kind: res.kind }, ...log].slice(0, 20);
    if (res.kind === "wrong" || res.kind === "exhausted") used = { ...used, [`${step.key}:${index}`]: usedOf(index) + 1 };
  }

  function apply(actions: Action[]) {
    for (const action of actions) {
      if (action.do === "flag" && action.name && !flags.includes(action.name)) flags = [...flags, action.name];
      if (action.do === "unflag") flags = flags.filter((f) => f !== action.name);
      if (action.do === "key" && action.slug && !keys.includes(action.slug)) keys = [...keys, action.slug];
    }
    const go = actions.find((a) => a.do === "goto");
    const target = go && steps.find((s) => s.name === go.step);
    if (target) {
      current = target.key;
      used = Object.fromEntries(Object.entries(used).filter(([k]) => !k.startsWith(`${target.key}:`)));
    }
    pick = null;
    result = null;
    typed = "";
  }

  function toggleKey(slug: string) {
    keys = keys.includes(slug) ? keys.filter((k) => k !== slug) : [...keys, slug];
  }
  function addFlag() {
    const name = newFlag.trim();
    if (name && !flags.includes(name)) flags = [...flags, name];
    newFlag = "";
  }
  function reset() {
    used = {};
    log = [];
    pick = null;
    result = null;
    current = (steps.find((s) => s.opening) ?? steps[0])?.key ?? "";
  }

  const KIND: Record<string, string> = { ok: "Верно", wrong: "Неверно", exhausted: "Попытки кончились", mismatch: "Набран не тот текст", closed: "Вариант закрыт" };
  const layoutText = (layout: Schemas["MlOffer"]["layout"]) =>
    layout.map((p) => ("text" in p ? p.text : "hidden" in p ? "•".repeat(p.hidden as number) : `[${(p.choices as string[]).join(" / ")}]`)).join("");
</script>

<div class="sandbox">
  <p class="muted small">Проверяет черновик, в мир ничего не пишет. Исходы с переходом, метками и ключами можно применить и идти дальше.</p>

  <div class="row">
    <label class="grow"><span class="label">Игрок стоит на шаге</span>
      <select class="field" bind:value={current}>
        {#each steps as s (s.key)}<option value={s.key}>{s.name}{s.opening ? " · начало" : ""}</option>{/each}
      </select></label>
    <button class="btn ghost" onclick={reset} title="Попытки и журнал с начала">С начала</button>
  </div>

  <details open={keys.length > 0 || flags.length > 0}>
    <summary>Что есть у игрока: ключей {keys.length}, меток {flags.length}</summary>
    <div class="group">
      <span class="label">Ключи</span>
      <div class="chips">
        {#each allKeys as k (k.slug)}<button type="button" class="chip" class:on={keys.includes(k.slug)} aria-pressed={keys.includes(k.slug)} onclick={() => toggleKey(k.slug)} title={k.description}>{k.slug}</button>{/each}
      </div>
      <span class="label">Метки</span>
      <div class="chips">
        {#each flags as f (f)}<span class="chip on">{f}<button class="x" onclick={() => (flags = flags.filter((x) => x !== f))} aria-label="Снять метку {f}">✕</button></span>{/each}
        <input class="field small-field" list="mail-flags" bind:value={newFlag} placeholder="метка, Enter" onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); addFlag(); } }} aria-label="Новая метка" />
      </div>
      <label><span class="label">Пишет с учётки</span>
        <select class="field" value={account ?? ""} onchange={(e) => (account = +e.currentTarget.value || null)}>
          <option value="">не важно</option>
          {#each picks?.accounts ?? [] as a (a.id)}<option value={a.id}>{a.label}</option>{/each}
        </select></label>
    </div>
  </details>

  {#if step?.letter?.subject || step?.letter?.text}
    <div class="letter"><b>✉ {step.letter.subject || "(без темы)"}</b><pre>{step.letter.text}</pre></div>
  {/if}

  <div class="offers">
    <span class="label">Что видит игрок в ответе</span>
    {#each offers as offer (offer.index)}
      {#if offer.shown === "hidden"}
        <div class="offer hidden" title="Скрыт от игрока: условие не выполнено">скрыт: {offer.title}</div>
      {:else if offer.shown === "mystery"}
        <div class="offer mystery" title="Закрыт: {offer.title}">???</div>
      {:else}
        <button class="offer" class:on={pick === offer.index} onclick={() => choose(offer.index)}>
          <b>{offer.title}</b>
          {#if offer.layout.length}<span class="layout">{layoutText(offer.layout)}</span>{/if}
          {#if variants[offer.index]?.max_attempts}<span class="muted small">попыток потрачено {usedOf(offer.index)} из {variants[offer.index].max_attempts}</span>{/if}
        </button>
      {/if}
    {:else}
      <p class="muted small">На этом шаге вариантов нет.</p>
    {/each}
  </div>

  {#if pick !== null}
    <div class="type">
      <textarea class="field mono" rows="2" bind:value={typed} placeholder="Что набирает игрок" aria-label="Набранный текст"
                onkeydown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }}></textarea>
      {#if variants[pick]?.attachment?.kind}
        <input class="field" bind:value={attachment} placeholder="слаг приложенного объекта" aria-label="Вложение" />
      {/if}
      <button class="btn primary" onclick={send}>Отправить</button>
    </div>
  {/if}

  {#if result}
    <div class="result {result.kind}">
      <b>{KIND[result.kind] ?? result.kind}</b>
      {#if result.words.length}<span> · выбрано: {result.words.join(", ")}</span>{/if}
      {#if result.left !== null && result.left !== undefined}<span> · осталось попыток {result.left}</span>{/if}
      {#if result.sockets.length}<div class="muted small">Сработал исход: {result.sockets.map(socketLabel).join(", ")}</div>{/if}
      {#each result.actions as a, i (i)}<div class="act">{describe(a as Action)}</div>{:else}{#if result.kind !== "mismatch" && result.kind !== "closed"}<div class="muted small">Действий нет.</div>{/if}{/each}
      {#if result.actions.length}<button class="btn ghost tiny" onclick={() => apply(result!.actions as Action[])}>Применить и идти дальше</button>{/if}
    </div>
  {/if}

  {#if log.length}
    <div class="log">
      <span class="label">Журнал</span>
      {#each log as entry, i (i)}<div class="entry"><span class="mono">{entry.step}</span> {entry.text} <span class="k {entry.kind}">{KIND[entry.kind] ?? entry.kind}</span></div>{/each}
    </div>
  {/if}
</div>

<style>
  .sandbox { display: flex; flex-direction: column; gap: 12px; }
  .row { display: flex; gap: 8px; align-items: flex-end; }
  .grow { flex: 1; min-width: 0; }
  label { display: flex; flex-direction: column; gap: 4px; }
  .small { font-size: 12px; margin: 0; }
  details summary { cursor: pointer; color: var(--muted); font-size: 12.5px; }
  .group { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; }
  .chips { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); cursor: pointer; font: inherit; font-size: 12.5px; }
  .chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 0 2px; font-size: 11px; }
  .small-field { width: 130px; padding: 3px 8px; font-size: 12.5px; }
  .letter { padding: 8px 10px; border-left: 2px solid var(--accent); background: var(--bg); border-radius: 0 var(--radius-s) var(--radius-s) 0; }
  .letter pre { margin: 4px 0 0; white-space: pre-wrap; font: inherit; color: var(--muted); font-size: 12.5px; }
  .offers { display: flex; flex-direction: column; gap: 5px; }
  .offer { display: flex; flex-direction: column; gap: 3px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel); color: var(--text); text-align: left; font: inherit; cursor: pointer; }
  .offer.on { border-color: var(--accent); background: var(--accent-soft); }
  .offer.mystery { color: var(--muted); cursor: default; font-family: var(--mono); }
  .offer.hidden { color: var(--faint); cursor: default; border-style: dashed; font-size: 12px; }
  .layout { font-family: var(--mono); font-size: 12px; color: var(--faint); white-space: pre-wrap; }
  .type { display: flex; flex-direction: column; gap: 6px; }
  .mono { font-family: var(--mono); font-size: 12.5px; }
  textarea { resize: vertical; }
  .type .btn { align-self: flex-start; }
  .result { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: var(--radius-s); background: var(--panel-2); border-left: 3px solid var(--muted); }
  .result.ok { border-left-color: var(--ok); }
  .result.wrong, .result.exhausted { border-left-color: var(--danger); }
  .result.mismatch, .result.closed { border-left-color: var(--warn); }
  .act { font-size: 12.5px; }
  .tiny { padding: 3px 10px; font-size: 12.5px; align-self: flex-start; }
  .log { display: flex; flex-direction: column; gap: 3px; font-size: 12px; }
  .entry { color: var(--muted); }
  .k.ok { color: var(--ok); }
  .k.wrong, .k.exhausted { color: var(--danger); }
  .k.mismatch, .k.closed { color: var(--warn); }
</style>
