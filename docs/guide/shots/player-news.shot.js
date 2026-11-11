// Новости: открыта закреплённая новость.
module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/apps/news/`);
    await page.locator(".card, .post, li").first().waitFor();
    await pause(1500);
  },
};
