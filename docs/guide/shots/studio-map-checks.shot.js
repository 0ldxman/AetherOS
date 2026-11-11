// Карта: проверка данных.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/map/checks`);
    await pause(3000);
  },
};
