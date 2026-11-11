// Почта игрока: письмо охраны порта открыто.
module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/apps/mail/`);
    await page.locator(".card").first().waitFor();
    await page.locator(".card").first().click();
    await pause(1200);
  },
};
