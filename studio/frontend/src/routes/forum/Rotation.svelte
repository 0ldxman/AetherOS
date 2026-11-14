<script lang="ts">
  // Ротация тем: пустое поле наследуется (подсказка показывает действующее значение выше), 0 выключает правило.
  import Hint from "../../lib/Hint.svelte";

  let { value = $bindable(), inherited, editable, error = "" }: {
    value: Record<string, number>; inherited: Record<string, number>; editable: boolean; error?: string;
  } = $props();

  const FIELDS: { key: string; label: string; unit: string; hint: string }[] = [
    { key: "archive_days", label: "Закрытая тема в архив через", unit: "дн.", hint: "Закрытая тема (вручную, за тишину или полный том) уходит в архив раздела: читать можно, отвечать нет." },
    { key: "idle_days", label: "Предупреждать после тишины", unit: "дн.", hint: "Сколько игровых дней без сообщений до записи системы «тема скоро закроется». Закреплённые темы и темы персонажей и системы не трогаются." },
    { key: "grace_days", label: "Закрыть после предупреждения через", unit: "дн.", hint: "Любое новое сообщение отменяет закрытие. 0: закрыть сразу, без предупреждения." },
    { key: "volume_posts", label: "Том по", unit: "сообщ.", hint: "Тема с таким числом сообщений закрывается томом и продолжается следующим с тем же заголовком." },
    { key: "compress_days", label: "Сжать архив через", unit: "дн.", hint: "Через столько дней в архиве от темы остаются заголовок и первое сообщение: «[N records compressed]». 0: не сжимать." },
  ];
  function set(key: string, raw: string) {
    const next = { ...value };
    if (raw.trim() === "") delete next[key];
    else next[key] = Number(raw);
    value = next;
  }
</script>

<fieldset class="rot">
  <legend class="label">Ротация тем<Hint text="Сроки в игровых днях. Пустое поле: как выше (у раздела — как у родителя и пространства). 0 выключает правило. Пока игровое время стоит, ротация тоже стоит." /></legend>
  {#each FIELDS as f (f.key)}
    <label class="line"><span>{f.label}<Hint text={f.hint} /></span>
      <input class="field mono" type="number" min="0" value={value[f.key] ?? ""} placeholder={String(inherited[f.key] ?? "")} disabled={!editable}
             oninput={(e) => set(f.key, (e.currentTarget as HTMLInputElement).value)} />
      <span class="muted small">{f.unit}</span></label>
  {/each}
  {#if error}<span class="error small">{error}</span>{/if}
</fieldset>

<style>
  .rot { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; border: 0; }
  .line { display: grid; grid-template-columns: minmax(0, 1fr) 90px 50px; align-items: center; gap: 8px; font-size: 13px; }
  .small { font-size: 12px; }
</style>
