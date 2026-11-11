// Поддержка: форма нового обращения.
module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/apps/support/`);
    await pause(1200);
    const compose = page.locator('button:has-text("new"), button:has-text("request")').first();
    if (await compose.count()) { await compose.click(); await pause(900); }
  },
};
