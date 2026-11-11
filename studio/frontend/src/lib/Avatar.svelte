<script lang="ts">
  // Кружок с первой буквой имени; цвет считается из имени, поэтому у одного человека он везде одинаковый.
  let { name, size = 24 }: { name: string; size?: number } = $props();
  const hue = $derived([...name].reduce((sum, ch) => (sum * 31 + ch.charCodeAt(0)) % 360, 7));
</script>

<span class="avatar" style="--hue: {hue}; --size: {size}px" title={name} aria-label={name}>{name.slice(0, 1).toUpperCase()}</span>

<style>
  .avatar {
    flex: none; display: inline-grid; place-items: center; width: var(--size); height: var(--size); border-radius: 50%;
    background: hsl(var(--hue) 42% 32%); color: #fff; font-size: calc(var(--size) * 0.45); font-weight: 650; line-height: 1;
  }
</style>
