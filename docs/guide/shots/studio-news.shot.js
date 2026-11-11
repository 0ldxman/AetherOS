// Новости: опубликованная новость в редакторе.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/news`);
    await pause(1200);
    await page.getByText("Welcome to Aether").first().click();
    await pause(1800);
  },
};
