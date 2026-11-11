// Доска.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/boards`);
    await pause(5000);
  },
};
