// Главная Студии.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/home`);
    await pause(2000);
  },
};
