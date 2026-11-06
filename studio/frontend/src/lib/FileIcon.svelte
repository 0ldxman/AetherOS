<script lang="ts">
  import type { Kind } from "./fileKind";

  /** Значок типа файла. Объекты окрашены акцентом, файлы без объекта нейтральные, папки жёлтые. */
  let { kind, own = false, size = 16 }: { kind: Kind; own?: boolean; size?: number } = $props();
</script>

<svg class="icon {kind}" class:own width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  {#if kind === "folder"}
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
  {:else if kind === "image"}
    <rect x="4" y="5" width="16" height="14" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="M4 17l5-5 4 4 3-3 4 4" />
  {:else if kind === "archive"}
    <path d="M4 4h16v4H4z M5 8h14v12H5z M10 12h4" />
  {:else if kind === "key"}
    <circle cx="8" cy="15" r="4" /><path d="M11 12l8-8 M16 7l2 2 M14 9l2 2" />
  {:else if kind === "doc"}
    <path d="M6 3h8l5 5v13H6z M14 3v5h5 M9 12h7 M9 15h7 M9 18h5" />
  {:else}
    <path d="M6 3h8l5 5v13H6z M14 3v5h5" />
  {/if}
</svg>

<style>
  .icon { flex: none; color: var(--accent); }
  .icon.own { color: var(--muted); }
  .icon.folder { color: var(--warn); }
</style>
