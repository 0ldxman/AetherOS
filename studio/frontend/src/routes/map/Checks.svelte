<script lang="ts">
  // Проверка данных карты: что выглядит неправильно. Каждая находка ведёт к месту, где её чинят.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../../lib/api";

  let checks = $state<Schemas["MapCheck"][] | null>(null);
  let busy = $state(false);

  async function run() {
    busy = true;
    checks = (await api.GET("/studio/api/map/checks")).data ?? [];
    busy = false;
  }
  onMount(run);

  const LEVEL: Record<string, string> = { error: "ошибка", warning: "стоит проверить", info: "к сведению" };
  const HINT: Record<string, string> = {
    "no-owner": "Такие провинции на карте серые. Отдайте их стране на вкладке «Территории» или удалите, если они не нужны.",
    "outside-life": "Запись стоит на дату, когда страны ещё нет или уже нет. Поправьте дату записи или годы жизни страны.",
    "same-day": "Две страны владеют одной провинцией с одной даты: на карте победит случайная. Удалите лишнюю запись.",
    "dead-owner": "Страна закончилась, а провинция так и осталась за ней. Передайте её наследнику с даты окончания.",
    "idle-country": "Страна нигде не используется. Можно удалить или отдать ей провинции.",
    "no-label": "У страны есть земли, но на карте нет её названия. Добавьте подпись.",
  };

  function link(item: Schemas["MapCheckItem"]): string {
    if (item.kind === "province") return `#/map/provinces/${item.id}`;
    if (item.kind === "country") return `#/map/countries/${item.id}`;
    return "#/map/ownerships";
  }
</script>

<div class="screen">
  <header class="head">
    <div>
      <h2>Проверка данных</h2>
      <p class="muted">Поиск противоречий в провинциях, странах и владениях. Ничего не меняет.</p>
    </div>
    <button class="btn" onclick={run} disabled={busy}>{busy ? "Проверяю…" : "Проверить снова"}</button>
  </header>

  {#if checks === null}
    <p class="muted">Загрузка…</p>
  {:else if !checks.length}
    <p class="ok">Всё в порядке: замечаний нет.</p>
  {:else}
    {#each checks as check (check.code)}
      <section class="block {check.level}">
        <h3>{check.title} <span class="chip">{check.count}</span><span class="level">{LEVEL[check.level]}</span></h3>
        {#if HINT[check.code]}<p class="muted small">{HINT[check.code]}</p>{/if}
        <ul>
          {#each check.items as item (item.kind + item.id + item.label)}
            <li><a href={link(item)}>{item.label}</a></li>
          {/each}
        </ul>
        {#if check.count > check.items.length}<p class="muted small">…и ещё {check.count - check.items.length}.</p>{/if}
      </section>
    {/each}
  {/if}
</div>

<style>
  .screen { display: flex; flex-direction: column; gap: 14px; padding: 24px 32px 40px; max-width: 900px; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; }
  h2 { margin: 0; font-size: 20px; }
  p { margin: 4px 0 0; }
  ul { margin: 0; padding: 0; list-style: none; columns: 2; column-gap: 24px; }
  li { padding: 2px 0; break-inside: avoid; }
  .ok { color: var(--ok); }
  .level { margin-left: auto; text-transform: none; letter-spacing: 0; font-weight: 400; }
  .error { border-left: 3px solid var(--danger); }
  .warning { border-left: 3px solid var(--warn); }
  .info { border-left: 3px solid var(--line); }
</style>
