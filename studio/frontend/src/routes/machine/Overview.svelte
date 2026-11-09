<script lang="ts">
  import { untrack } from "svelte";
  import Hint from "../../lib/Hint.svelte";
  import { STATUS } from "../../lib/labels";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { plural } from "../../lib/labels";
  import { ago, span, when } from "../../lib/time";
  import Dialog from "../../lib/Dialog.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import NewMachine from "./NewMachine.svelte";

  let { machine, onchange }: { machine: Schemas["Overview"]; onchange: () => void } = $props();

  let form = $state({ hostname: "", name: "", system: "", status: "", hid: "", address: "", serial: "", host_key: "", note: "", booted_at: "", entry_policy: null as number | null });
  let saving = $state(false);
  let errors = $state<Record<string, string[]>>({});
  let dialog = $state<null | "delete" | "copy">(null);

  async function remove() {
    const { error } = await api.DELETE("/studio/api/machines/{machine_id}", { params: { path: { machine_id: machine.id } } });
    dialog = null;
    if (error) return toast(problem(error), "error");
    toast("Машина удалена.");
    go("/machines");
  }

  // datetime-local хочет «ГГГГ-ММ-ДДTЧЧ:ММ» по местному времени
  function local(iso: string | null) {
    if (!iso) return "";
    const date = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  $effect(() => {
    form = {
      hostname: machine.hostname, name: machine.name, system: machine.system, status: machine.status, hid: machine.hid, address: machine.address, serial: machine.serial, host_key: machine.host_key,
      note: machine.note, booted_at: local(machine.booted_at ?? null), entry_policy: machine.policy?.id ?? null,
    };
  });
  const dirty = $derived(
    form.hostname !== machine.hostname || form.name !== machine.name || form.system !== machine.system ||
      form.status !== machine.status || form.entry_policy !== (machine.policy?.id ?? null) || form.hid !== machine.hid || form.address !== machine.address || form.serial !== machine.serial || form.host_key !== machine.host_key ||
      form.note !== machine.note || form.booted_at !== local(machine.booted_at ?? null),
  );
  guardUnsaved(() => dirty);

  let art = $state<{ valid: boolean; lines: string[] }>({ valid: true, lines: [] });
  let artTimer: ReturnType<typeof setTimeout>;

  // картинка отпечатка следует за тем, что в поле (пусто: за ключом, который выводится из hid)
  $effect(() => {
    const key = form.host_key.trim() || machine.auto_host_key;
    clearTimeout(artTimer);
    artTimer = setTimeout(async () => {
      const { data } = await api.POST("/studio/api/machines/randomart", { body: { host_key: key } });
      if (data) art = { valid: data.valid || !form.host_key.trim(), lines: data.lines };
    }, 200);
    return () => clearTimeout(artTimer);
  });

  async function generate(field: "hid" | "address" | "serial" | "host_key") {
    const { data } = await api.POST("/studio/api/machines/generate", { body: { field, system: form.system } });
    if (data) form[field] = data.value;
  }

  async function save() {
    saving = true;
    errors = {};
    const { error } = await api.PUT("/studio/api/machines/{machine_id}", { params: { path: { machine_id: machine.id } }, body: { ...form, booted_at: form.booted_at ? new Date(form.booted_at).toISOString() : null } });
    saving = false;
    if (error) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    toast("Сохранено.");
    onchange();
  }

  async function act(kind: "unlock" | "kick", row: Schemas["Online"]) {
    const path = kind === "unlock" ? "/studio/api/machines/{machine_id}/unlock" : "/studio/api/machines/{machine_id}/kick";
    const { error } = await api.POST(path, { params: { path: { machine_id: machine.id } }, body: { account: row.account, player: row.player } });
    if (error) return toast(problem(error), "error");
    toast(kind === "unlock" ? `${row.player} разблокирован.` : `${row.player} будет выкинут при следующем действии.`);
    onchange();
  }

  const KIND_TONE: Record<string, string> = { ok: "ok", unlocked: "info", kicked: "info", locked: "bad" };

  // «Сейчас на машине»: число и всплывающий список с действиями. Открывается по наведению и фокусу, остаётся, пока на нём курсор или фокус,
  // закрывается по Esc; на касании открывается нажатием.
  let pop = $state(false);
  let popTimer: ReturnType<typeof setTimeout>;
  const openPop = () => { clearTimeout(popTimer); pop = true; };
  const closePop = () => { clearTimeout(popTimer); popTimer = setTimeout(() => (pop = false), 150); };

  let idOpen = $state(false);
  let greetOpen = $state(untrack(() => !!(machine.note || machine.booted_at)));
  $effect(() => { if (errors.host_key || errors.hid || errors.address || errors.serial) idOpen = true; });
</script>

{#if machine.warnings.length}
  <div class="alerts" role="status">
    {#each machine.warnings as item}
      <p class="warn {item.level}">
        {item.text}
        {#if item.account}<a href="#/machines/{machine.id}/accounts/{item.account}">открыть учётку</a>{/if}
      </p>
    {/each}
  </div>
{/if}

<div class="savebar" class:dirty>
  <span class="state">{#if dirty}<span class="dot"></span>Не сохранено{:else}<span class="muted">Изменений нет</span>{/if}</span>
  <button class="btn primary" disabled={!dirty || saving} onclick={save}>{saving ? "Сохраняю…" : "Сохранить"}</button>
</div>

<svelte:window onkeydown={(event) => event.key === "Escape" && (pop = false)} />

<div class="grid">
  <div class="main">
    <section class="card">
      <h2>Основное</h2>
      <div class="pair">
        <label><span class="label">Хост</span><input class="field mono" bind:value={form.hostname} class:bad={errors.hostname} />
          {#if errors.hostname}<span class="err">{errors.hostname.join(" ")}</span>{/if}</label>
        <label><span class="label">Название</span><input class="field" bind:value={form.name} /></label>
      </div>
      <div class="pair">
        <label><span class="label">ОС</span>
          <select class="field" bind:value={form.system}>{#each machine.systems as code}<option>{code}</option>{/each}</select>
        </label>
        <label><span class="label">Статус</span>
          <select class="field" bind:value={form.status}>{#each machine.statuses as code}<option value={code}>{STATUS[code] ?? code}</option>{/each}</select>
        </label>
      </div>
      <label><span class="label">Политика входа машины<Hint text="Как проверяется вход на эту машину. Учётка со своей политикой её перекрывает. Что действует для каждой учётки, видно на вкладке «Проверка входа»." /></span>
        <select class="field" bind:value={form.entry_policy}>
          <option value={null}>от ОС</option>
          {#each machine.policies as policy}<option value={policy.id}>{policy.name}</option>{/each}
        </select>
      </label>
    </section>

    <section class="card">
      <details bind:open={idOpen}>
        <summary>Идентичность <span class="muted small">hid, адрес, серийный номер, ключ узла</span></summary>
        <p class="muted small lead">Пустое поле: значение выводится из hid. Можно вписать своё или сгенерировать. Одинаковый hid у двух машин нормален: так клон выглядит той же машиной.</p>
        <div class="idrow">
          <label><span class="label">hid<Hint text="Аппаратный идентификатор машины. Одинаковый hid у двух машин значит, что одна из них клон другой." /></span><input class="field mono" bind:value={form.hid} class:bad={errors.hid} /></label>
          <button class="btn ghost" onclick={() => generate("hid")}>Сгенерировать</button>
        </div>
        <div class="idrow">
          <label><span class="label">Адрес (частота МГц или сетевой)</span><input class="field mono" placeholder={machine.auto_address} bind:value={form.address} /></label>
          <button class="btn ghost" onclick={() => generate("address")}>Сгенерировать</button>
        </div>
        <div class="idrow">
          <label><span class="label">Серийный номер</span><input class="field mono" placeholder={machine.auto_serial} bind:value={form.serial} /></label>
          <button class="btn ghost" onclick={() => generate("serial")}>Сгенерировать</button>
        </div>
        <div class="idrow">
          <label><span class="label">Ключ узла (host key)</span><input class="field mono" placeholder={machine.auto_host_key} bind:value={form.host_key} class:bad={errors.host_key || !art.valid} /></label>
          <button class="btn ghost" onclick={() => generate("host_key")}>Перегенерировать</button>
        </div>
        {#if errors.host_key}<p class="err">{errors.host_key.join(" ")}</p>{:else if form.host_key && !art.valid}<p class="err">Отпечаток выглядит так: SHA256: и 43 символа base64.</p>{/if}
        <pre class="art mono">{art.lines.join("\n")}</pre>
      </details>
    </section>
    <section class="card">
      <details bind:open={greetOpen}>
        <summary>Для приветствия ОС <span class="muted small">включена с, заметка</span></summary>
        <p class="muted small lead">Попадает в приветствие ОС как <code>{"{note}"}</code> и <code>{"{uptime}"}</code>.</p>
        <div class="pair">
          <label><span class="label">Включена с</span><input class="field" type="datetime-local" bind:value={form.booted_at} /></label>
        </div>
        <label><span class="label">Заметка</span><textarea class="field" rows="3" bind:value={form.note}></textarea></label>
      </details>
    </section>

    <div class="more-acts">
      <button class="btn ghost" onclick={() => (dialog = "copy")}>Новая машина по образцу этой</button>
      {#if !machine.is_system}<button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить машину</button>{/if}
    </div>
  </div>

  <aside class="side">
    <section class="card now" role="group" aria-label="Сейчас на машине" onmouseenter={openPop} onmouseleave={closePop} onfocusin={openPop}
             onfocusout={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) closePop(); }}>
      <button class="nowbtn" aria-haspopup="true" aria-expanded={pop && machine.online.length > 0} disabled={!machine.online.length}
              onclick={() => (pop = !pop)}>
        <span class="big" class:live={machine.online.length > 0}>{machine.online.length}</span>
        <span class="lbl">{plural(machine.online.length, "игрок", "игрока", "игроков")} на машине<br />
          <span class="muted small">{machine.online.length ? "наведите, чтобы увидеть, кто" : "за последние две минуты никого"}</span></span>
        {#if machine.online.length}<span class="live-dot"></span>{/if}
      </button>
      {#if pop && machine.online.length}
        <div class="pop" role="region" aria-label="Кто сейчас на машине">
          {#each machine.online as row (row.session)}
            <div class="online">
              <span class="live-dot"></span>
              <span><b>{row.player}</b> <span class="muted">как</span> <a href="#/machines/{machine.id}/accounts/{row.account}" class="mono">{row.login}</a></span>
              <span class="muted small">{ago(row.seen_at)}</span>
              {#if row.locked}<span class="chip bad">блок {span(row.locked)}</span>{/if}
              <span class="spacer"></span>
              {#if row.locked}<button class="btn ghost" onclick={() => act("unlock", row)}>Разблокировать</button>{/if}
              <button class="btn ghost danger" onclick={() => act("kick", row)}>Выкинуть</button>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <section class="card">
      <h2>Последние события <a class="more" href="#/machines/{machine.id}/journal">весь журнал →</a></h2>
      {#each machine.events.slice(0, 6) as event (event.id)}
        <div class="event">
          <span class="line1"><span class="kind {KIND_TONE[event.kind] ?? 'bad'}">{event.label}</span><span class="when mono">{when(event.at)}</span></span>
          <span class="who muted">
            <span class="mono">{event.login}</span>{#if event.player}{" "}· {event.player}{/if}{#if event.source}{" "}· с {event.source}{/if}
          </span>
        </div>
      {:else}
        <p class="muted">Входов ещё не было.</p>
      {/each}
    </section>
  </aside>
</div>

{#if dialog === "delete"}
  <Dialog title="Удалить {machine.hostname || machine.name}?" confirm="Удалить" danger onsubmit={remove} onclose={() => (dialog = null)}>
    <p class="muted">Удалятся учётки, их сессии и журнал, монтирования, экспорты, свои группы и пути машины. Диски останутся: они могут быть
      нужны другим машинам, лишние удалите в «Дисках».</p>
  </Dialog>
{:else if dialog === "copy"}
  <NewMachine machines={[{ id: machine.id, hostname: machine.hostname, name: machine.name, system: machine.system, status: machine.status,
                           is_system: machine.is_system, accounts: 0, online: 0, refusals: 0, last_login: null, warnings: 0 }]} like={machine.id} onclose={() => (dialog = null)} />
{/if}

<style>
  .idrow { display: grid; grid-template-columns: 1fr max-content; gap: 8px; align-items: end; margin-top: 10px; }
  summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  summary .small { text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 8px; }
  details[open] summary { margin-bottom: 8px; }
  .lead { margin: 0 0 10px; }
  .art { margin: 10px 0 0; padding: 8px 10px; border-radius: var(--radius-s); background: #0b0d10; color: var(--muted); font-size: 12px; line-height: 1.15; overflow: auto; }
  .alerts { padding: 12px 20px 0; }
  .savebar { position: sticky; top: 0; z-index: 3; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 20px; background: var(--bg); border-bottom: 1px solid var(--line-soft); }
  .savebar.dirty { background: color-mix(in srgb, var(--warn) 7%, var(--bg)); }
  .state { display: inline-flex; align-items: center; gap: 8px; font-size: 12.5px; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  .grid { display: grid; grid-template-columns: 1fr 340px; gap: 16px; padding: 16px 20px 24px; align-items: start; }
  .main, .side { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .card { border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
  h2 { display: flex; align-items: baseline; margin: 0; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .more { margin-left: auto; font-size: 12px; text-transform: none; letter-spacing: 0; }
  .warn { margin: 0 0 6px; padding: 7px 10px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.08); border-left: 3px solid var(--warn); }
  .warn.info { background: var(--panel-2); border-left-color: var(--accent); }
  .warn a { margin-left: 6px; }
  .now { position: relative; padding: 10px 12px; }
  .nowbtn { display: flex; align-items: center; gap: 12px; width: 100%; padding: 0; border: 0; background: none; text-align: left; cursor: pointer; }
  .nowbtn:disabled { cursor: default; }
  .big { font-size: 30px; font-weight: 650; line-height: 1; min-width: 32px; text-align: center; color: var(--muted); }
  .big.live { color: var(--ok); }
  .lbl { line-height: 1.3; }
  .pop { position: absolute; z-index: 5; top: calc(100% + 4px); left: 0; right: 0; padding: 8px 10px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); box-shadow: 0 10px 28px rgba(0, 0, 0, 0.5); }
  .online { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .online:last-child { border-bottom: 0; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); flex: none; margin-left: auto; }
  .online .live-dot { margin-left: 0; }
  .spacer { flex: 1; }
  .small { font-size: 12px; }
  .chip.bad { background: var(--danger-soft); color: var(--danger); }
  .event { display: flex; flex-direction: column; padding: 4px 0; border-bottom: 1px solid var(--line-soft); }
  .event:last-child { border-bottom: 0; }
  .line1 { display: flex; justify-content: space-between; gap: 8px; }
  .when { color: var(--faint); font-size: 12px; }
  .who { font-size: 12.5px; }
  .kind { font-size: 12.5px; }
  .kind.ok { color: var(--ok); }
  .kind.bad { color: var(--danger); }
  .kind.info { color: var(--accent); }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .field.bad { border-color: var(--danger); }
  .err { color: var(--danger); font-size: 12px; }
  .more-acts { display: flex; flex-wrap: wrap; gap: 4px; padding-top: 4px; }
  @media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } .side { order: -1; } }
</style>
