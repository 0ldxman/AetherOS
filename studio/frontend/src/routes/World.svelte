<script lang="ts">
  import PageHead from "../lib/PageHead.svelte";
</script>

<PageHead title="Мир">
  {#snippet sub()}Сценарии, их этапы и пульт управления.{/snippet}
</PageHead>

<section class="card">
  <h2>Время</h2>
  <p class="muted">Игровое время, его ход и запланированные сдвиги: раздел <a href="#/time">Время</a>.</p>
</section>

<section class="card">
  <h2>Сценарии</h2>
  <p class="muted">Редактор сценариев: раздел <a href="#/graphs">Сценарии</a>. Здесь появится пульт управления ими.</p>
</section>

<style>
  .card { margin: 12px 32px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 10px; }
  h2 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
</style>
