<script lang="ts">
  import { api, problem, type Schemas } from "../../lib/api";
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
</script>

<div class="grid">
  <div class="col">
    {#if machine.warnings.length}
      <section class="card">
        <h2>Обратите внимание</h2>
        {#each machine.warnings as item}
          <p class="warn {item.level}">
            {item.text}
            {#if item.account}<a href="#/machines/{machine.id}/accounts/{item.account}">открыть учётку</a>{/if}
          </p>
        {/each}
      </section>
    {/if}

    <section class="card">
      <h2>Сейчас на машине</h2>
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
      {:else}
        <p class="muted">Никого: за последние две минуты здесь не работал ни один игрок.</p>
      {/each}
    </section>

    <section class="card">
      <h2>Последние события <a class="more" href="#/machines/{machine.id}/journal">весь журнал →</a></h2>
      {#each machine.events as event (event.id)}
        <div class="event">
          <span class="when mono">{when(event.at)}</span>
          <span class="kind {KIND_TONE[event.kind] ?? 'bad'}">{event.label}</span>
          <span class="who">
            <span class="mono">{event.login}</span>
            {#if event.player}<span>· {event.player}</span>{/if}
            {#if event.source}<span class="muted">с {event.source}</span>{/if}
          </span>
        </div>
      {:else}
        <p class="muted">Входов ещё не было.</p>
      {/each}
    </section>
  </div>

  <section class="card props">
    <h2>Свойства</h2>
    <label><span class="label">Хост</span><input class="field mono" bind:value={form.hostname} class:bad={errors.hostname} /></label>
    {#if errors.hostname}<p class="err">{errors.hostname.join(" ")}</p>{/if}
    <label><span class="label">Название</span><input class="field" bind:value={form.name} /></label>
    <div class="pair">
      <label><span class="label">Тип системы</span>
        <select class="field" bind:value={form.system}>{#each machine.systems as code}<option>{code}</option>{/each}</select>
      </label>
      <label><span class="label">Статус</span>
        <select class="field" bind:value={form.status}>{#each machine.statuses as code}<option>{code}</option>{/each}</select>
      </label>
    </div>
    <div class="pair">
      <label><span class="label">Включена с</span><input class="field" type="datetime-local" bind:value={form.booted_at} /></label>
    </div>
    <label><span class="label">Заметка</span><textarea class="field" rows="3" bind:value={form.note}></textarea></label>
    <p class="muted small">Заметка и «включена с» попадают в приветствие ОС как <code>{"{note}"}</code> и <code>{"{uptime}"}</code>.</p>
    <h3 class="sub">Идентичность</h3>
    <p class="muted small">Пустое поле: значение выводится из hid. Можно вписать своё или сгенерировать. Одинаковый hid у двух машин нормален: так клон выглядит той же машиной.</p>
    <div class="idrow">
      <label><span class="label">hid</span><input class="field mono" bind:value={form.hid} class:bad={errors.hid} /></label>
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
    <label><span class="label">Политика входа машины</span>
      <select class="field" bind:value={form.entry_policy}>
        <option value={null}>от типа системы</option>
        {#each machine.policies as policy}<option value={policy.id}>{policy.name}</option>{/each}
      </select>
    </label>
    <p class="muted small">Учётка со своей политикой её перекрывает. Что действует для каждой учётки, видно на вкладке «Доступ».</p>
    <button class="btn primary" disabled={!dirty || saving} onclick={save}>Сохранить</button>
    <div class="more-acts">
      <button class="btn ghost" onclick={() => (dialog = "copy")}>Новая машина по образцу этой</button>
      {#if !machine.is_system}<button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить машину</button>{/if}
    </div>
  </section>
</div>

{#if dialog === "delete"}
  <Dialog title="Удалить {machine.hostname || machine.name}?" confirm="Удалить" danger onsubmit={remove} onclose={() => (dialog = null)}>
    <p class="muted">Удалятся учётки, их сессии и журнал, монтирования, экспорты, свои группы и пути машины. Тома останутся: они могут быть
      нужны другим машинам, лишние удалите в «Томах».</p>
  </Dialog>
{:else if dialog === "copy"}
  <NewMachine machines={[{ id: machine.id, hostname: machine.hostname, name: machine.name, system: machine.system, status: machine.status,
                           is_system: machine.is_system, accounts: 0, online: 0, refusals: 0 }]} like={machine.id} onclose={() => (dialog = null)} />
{/if}

<style>
  .idrow { display: grid; grid-template-columns: 1fr max-content; gap: 8px; align-items: end; }
  .sub { margin: 8px 0 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .art { margin: 0; padding: 8px 10px; border-radius: var(--radius-s); background: #0b0d10; color: var(--muted); font-size: 12px; line-height: 1.15; overflow: auto; }
  .grid { display: grid; grid-template-columns: 1fr 340px; gap: 16px; padding: 16px 20px 24px; align-items: start; }
  .col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .card { border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  h2 { display: flex; align-items: baseline; margin: 0 0 10px; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .more { margin-left: auto; font-size: 12px; text-transform: none; letter-spacing: 0; }
  .warn { margin: 0 0 6px; padding: 7px 10px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.08); border-left: 3px solid var(--warn); }
  .warn.info { background: var(--panel-2); border-left-color: var(--accent); }
  .warn a { margin-left: 6px; }
  .online { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .online:last-child { border-bottom: 0; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); }
  .spacer { flex: 1; }
  .small { font-size: 12px; }
  .chip.bad { background: var(--danger-soft); color: var(--danger); }
  .event { display: grid; grid-template-columns: 96px 150px 1fr; gap: 10px; padding: 4px 0; align-items: center; }
  .when { color: var(--faint); }
  .who { display: flex; gap: 6px; align-items: baseline; }
  .kind { font-size: 12.5px; }
  .kind.ok { color: var(--ok); }
  .kind.bad { color: var(--danger); }
  .kind.info { color: var(--accent); }
  .props { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 16px; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .field.bad { border-color: var(--danger); }
  .err { margin: -6px 0 0; color: var(--danger); font-size: 12px; }
  .more-acts { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding-top: 8px; border-top: 1px solid var(--line-soft); }
</style>
