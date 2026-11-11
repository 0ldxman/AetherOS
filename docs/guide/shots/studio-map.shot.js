// Карта: территории.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/map`);
    await pause(5000);
  },
};
