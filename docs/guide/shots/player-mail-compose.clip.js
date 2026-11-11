// Ответ персонажу: выбрать вариант, набрать текст с секретом и словом-выбором.
const { click, type, glide } = require("./_lib");

module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/apps/mail/`);
    await page.locator(".card").first().waitFor();
    await pause(1500);
    await click(page, page.locator("#mail-compose"));
    await pause(700);
    await type(page, page.locator("input.compose-input").first(), "guard@aether-core");
    await page.keyboard.press("Enter");
    await pause(1200);
    await click(page, page.locator(".offer").first());
    await pause(900);
    await page.keyboard.type("I need access to the docks.", { delay: 60 });
    await pause(700);
    await click(page, page.locator('button.mail-button:has-text("send")'));
    await pause(2500);
    // ответ охраны: открыть и ответить паролем
    await click(page, page.locator(".card").first());
    await pause(1500);
    await click(page, page.locator('#mail-reader button:has-text("reply")').first());
    await pause(900);
    await click(page, page.locator(".offer", { hasText: "password" }).first());
    await pause(1200);
    await page.keyboard.type("Password: hunter2. Dock 7, please.", { delay: 70 });
    await pause(900);
    await click(page, page.locator('button.mail-button:has-text("send")'));
    await pause(2200);
  },
};
