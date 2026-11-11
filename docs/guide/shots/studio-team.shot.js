// Команда: авторы.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/team`);
    await pause(1800);
  },
};
