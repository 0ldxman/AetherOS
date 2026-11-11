// Терминал: найти спрятанный ключ в файле, достать его и снять пароль с файла.
const { dblclick, type, camera } = require("./_lib");

module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/desktop/`);
    await pause(1500);
    await dblclick(page, page.locator("text=console.sh").first());
    const term = page.frameLocator("iframe").first();
    const input = term.locator("#terminal-input");
    await input.waitFor();
    await pause(1200);
    await camera(page, { x: 100, y: 20, w: 520, h: 380 });                      // окно терминала крупно
    await pause(800);
    const run = async (command, wait = 1600) => {
      await type(page, input, command);
      await page.keyboard.press("Enter");
      await pause(wait);
    };
    await run("ls -l");
    await run("txtx report.rec", 2200);
    const text = await term.locator("#terminal-output").innerText();
    const found = text.match(/(0x[0-9A-Fa-f]+)\s+-----BEGIN/);
    await run(`kex report.rec ${found ? found[1] : "0x0"}`, 2200);
    await run("ward keys", 1800);
    await run("ward door.bin hunter2", 2400);
    await pause(1500);
    await camera(page, null);
    await pause(1200);
  },
};
