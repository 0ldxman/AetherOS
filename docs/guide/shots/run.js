// Съёмка справки: запускает docs_media. Сценарий <имя>.shot.js делает картинку, <имя>.clip.js видео.
// Сценарий экспортирует { as: "author" | "player", run({ page, base, pause }) }. Окружение даёт команда.
const fs = require("fs");
const os = require("os");
const path = require("path");

const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const base = process.env.GUIDE_BASE;
const out = process.env.GUIDE_OUT;
const dir = process.env.GUIDE_SHOTS;
const only = (process.env.GUIDE_ONLY || "").split(",").filter(Boolean);
const world = JSON.parse(process.env.GUIDE_WORLD);

// Видео playwright не рисует курсор: добавляем свой, он идёт за мышью.
const CURSOR = `
  try { document.documentElement.style.background = "#0e0f12"; } catch (e) {}      // без белой вспышки при загрузке
  addEventListener("DOMContentLoaded", () => {
    const arrow = document.createElement("div");
    arrow.innerHTML = '<svg width="22" height="30" viewBox="0 0 22 30" xmlns="http://www.w3.org/2000/svg"><path d="M2 2 L2 23 L7.6 18 L11.4 27.2 L15 25.6 L11.2 16.6 L18.6 16.6 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    arrow.style.cssText = "position:fixed;z-index:2147483647;left:-60px;top:-60px;width:22px;height:30px;pointer-events:none;transform-origin:2px 2px;transition:transform .09s;filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))";
    document.documentElement.append(arrow);
    addEventListener("mousemove", (e) => { arrow.style.left = e.clientX - 2 + "px"; arrow.style.top = e.clientY - 2 + "px"; }, true);
    addEventListener("mousedown", (e) => {
      arrow.style.transform = "scale(.86)";
      const ring = document.createElement("div");                                   // кольцо под местом нажатия
      ring.style.cssText = "position:fixed;z-index:2147483646;width:28px;height:28px;border-radius:50%;border:2px solid rgba(122,162,255,.9);pointer-events:none;transition:transform .45s ease-out,opacity .45s ease-out;left:" + (e.clientX - 14) + "px;top:" + (e.clientY - 14) + "px";
      document.documentElement.append(ring);
      requestAnimationFrame(() => requestAnimationFrame(() => { ring.style.transform = "scale(2)"; ring.style.opacity = "0"; }));
      setTimeout(() => ring.remove(), 600);
    }, true);
    addEventListener("mouseup", () => (arrow.style.transform = ""), true);
  });`;

async function authorState(browser) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${base}/admin/login/?next=/studio/`);
  await page.fill("#id_username", world.author.username);
  await page.fill("#id_password", world.author.password);
  await page.click("input[type=submit]");
  await page.waitForURL("**/studio/**");
  const state = await ctx.storageState();
  await ctx.close();
  return state;
}

(async () => {
  const launch = { args: ["--no-sandbox"] };
  if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(launch);
  const author = await authorState(browser);
  const jobs = fs.readdirSync(dir).filter((f) => /\.(shot|clip)\.js$/.test(f)).map((f) => {
    const [name, kind] = f.split(".");
    return { name, kind, file: path.join(dir, f) };
  }).filter((job) => !only.length || only.includes(job.name));

  let failed = 0;
  for (const job of jobs) {
    const script = require(job.file);
    const clip = job.kind === "clip";
    const tmp = clip ? fs.mkdtempSync(path.join(os.tmpdir(), "guide-")) : null;
    const size = clip ? { width: 1280, height: 720 } : { width: 1280, height: 800 };
    let ctx, page, video;
    try {
      ctx = await browser.newContext({
        viewport: size, deviceScaleFactor: 1, storageState: script.as === "player" ? undefined : author,
        ...(clip ? { recordVideo: { dir: tmp, size } } : {}),
      });
      if (script.as === "player") await ctx.addCookies([{ name: "sessionid", value: world.player_cookie, url: base }]);
      if (clip) await ctx.addInitScript(CURSOR);
      page = await ctx.newPage();
      if (clip) await page.setContent('<body style="margin:0;background:#0e0f12"></body>');
      page.on("pageerror", (e) => console.log(`     pageerror: ${e.message.slice(0, 200)}`));
      await script.run({ page, base, pause: (ms) => page.waitForTimeout(ms) });
      if (clip) video = page.video();
      else await page.screenshot({ path: path.join(out, `${job.name}.png`) });
      await page.close();
      if (script.cleanup) {                                  // вернуть мир в исходное: съёмки не должны мешать друг другу
        const tidy = await ctx.newPage();
        await script.cleanup({ page: tidy, base, pause: (ms) => tidy.waitForTimeout(ms) });
        await tidy.close();
      }
      if (clip) {
        const file = await video.path();
        await ctx.close();
        fs.copyFileSync(file, path.join(out, `${job.name}.webm`));
      } else await ctx.close();
      console.log(`ok   ${job.name}`);
    } catch (error) {
      failed++;
      const shot = path.join(os.tmpdir(), `guide-fail-${job.name}.png`);
      await page?.screenshot({ path: shot }).then(() => console.log(`     экран в момент ошибки: ${shot}`), () => {});
      console.log(`FAIL ${job.name}: ${String(error.message).split("\n").find((l) => l.trim()) || error}`);
      await ctx?.close().catch(() => {});
    }
    if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
