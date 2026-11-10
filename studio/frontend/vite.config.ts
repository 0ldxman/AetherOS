import { defineConfig, type Plugin } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";
import { copyFileSync, cpSync, existsSync, mkdirSync } from "node:fs";

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

// Шрифты холста доски (Excalidraw) кладутся рядом со сборкой: иначе он берёт их с внешнего CDN. Китайский набор (Xiaolai,
// больше 10 МБ) не копируется: он нужен только для иероглифов.
function excalidrawFonts(): Plugin {
  return {
    name: "excalidraw-fonts",
    apply: "build",
    closeBundle() {
      const from = here("node_modules/@excalidraw/excalidraw/dist/prod/fonts");
      if (existsSync(from)) cpSync(from, here("../static/studio/app/fonts"), { recursive: true, filter: (path) => !path.includes("Xiaolai") });
    },
  };
}

// Наши шрифты (static/ui/fonts) в выборе шрифта доски. Своих шрифтов Excalidraw подключать не даёт: список зашит в его
// код, поэтому при сборке он дополняется (версия пакета закреплена; если код сменится, сборка предупредит, а не упадёт).
// Excalidraw подписывает формат по расширению (format('ttf')), такие источники браузер пропускает: ttf и otf подписываются
// как truetype и opentype.
const OWN_FONTS: [string, string][] = [
  ["Terminus", "TerminusTTF-4.49.3.ttf"],
  ["IBM VGA", "WebPlus_IBM_VGA_9x16.woff"],
  ["AST PremiumExec", "Web437_AST_PremiumExec.woff"],
  ["VCR OSD", "vcrosdmonorus_vhsicons.ttf"],
  ["HomeVideo", "HomeVideo-Regular.otf"],
  ["Core Narae", "CoreNaraePro_0.ttf"],
  ["Belepotan Rus", "Belepotan-Rus.woff2"],
  ["Lemon Tuesday", "Lemon-Tuesday.woff2"],
  ["Strokify", "Strokify-Light.woff2"],
];

function excalidrawOwnFonts(): Plugin {
  const families = OWN_FONTS.map(([name], at) => `${JSON.stringify(name)}:${20 + at}`).join(",");
  return {
    name: "excalidraw-own-fonts",
    transform(code, id) {
      if (!id.includes("@excalidraw/excalidraw/dist") || !code.includes('"Liberation Sans":9}')) return null;
      let next = code.replace('"Liberation Sans":9}', `"Liberation Sans":9,${families}}`);
      next = next.replace(/([\w$]+)\("Virgil",\.\.\.([\w$]+)\),/, (found, init) =>
        found + OWN_FONTS.map(([name, file]) => `${init}(${JSON.stringify(name)},{uri:${JSON.stringify(`./fonts/aether/${file}`)}}),`).join(""));
      next = next.replace(/`format\('\$\{([\w$]+)\.pop\(\)\}'\)`/, (_found, parts) =>
        `((e)=>\`format('\${({ttf:"truetype",otf:"opentype"})[e]??e}')\`)(${parts}.pop())`);
      const done = next.includes(`./fonts/aether/${OWN_FONTS[0][1]}`) && next.includes("truetype");
      if (!done) this.warn("Excalidraw изменился: свои шрифты на доску не добавлены (vite.config.ts, excalidrawOwnFonts).");
      return { code: next, map: null };
    },
    closeBundle() {
      const from = here("../../static/ui/fonts");
      const to = here("../static/studio/app/fonts/aether");
      mkdirSync(to, { recursive: true });
      for (const [, file] of OWN_FONTS) if (existsSync(`${from}/${file}`)) copyFileSync(`${from}/${file}`, `${to}/${file}`);
    },
  };
}

// Сборка ложится в статику Django (studio/static/studio/app): страницу /studio/ отдаёт Django, файлы подключает по манифесту.
export default defineConfig({
  plugins: [esmFromNpm(), svelte(), excalidrawFonts(), excalidrawOwnFonts()],
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
