// Настройки мира.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/world`);
    await pause(1500);
  },
};
