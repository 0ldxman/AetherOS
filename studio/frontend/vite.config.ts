import { defineConfig, type Plugin } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// Подсветка разметки общая со старым редактором (documents/static/documents/editor): там CodeMirror берётся с esm.sh,
// здесь те же адреса ведут в пакеты npm этой папки (файлы лежат вне её, поэтому пакет ищется от src/).
function esmFromNpm(): Plugin {
  const pattern = /^https:\/\/esm\.sh\/(@[a-z]+\/[a-z]+)@\d+$/;
  return {
    name: "esm-from-npm",
    enforce: "pre",
    resolveId(source) {
      const found = pattern.exec(source);
      return found ? this.resolve(found[1], here("src/main.ts"), { skipSelf: true }) : null;
    },
  };
}

// Сборка ложится в статику Django (studio/static/studio/app): страницу /studio/ отдаёт Django, файлы подключает по манифесту.
export default defineConfig({
  plugins: [esmFromNpm(), svelte()],
  base: "./",
  resolve: {
    alias: { $documents: here("../../documents/static/documents") },
  },
  build: {
    outDir: here("../static/studio/app"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: "src/main.ts" },
  },
});
