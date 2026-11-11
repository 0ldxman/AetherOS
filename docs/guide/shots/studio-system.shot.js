// Операционная система AETHER.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/systems/AETHER/overview`);
    await pause(2200);
  },
};
