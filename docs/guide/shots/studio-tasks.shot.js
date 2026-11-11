// Задачи: доска по статусам.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/tasks`);
    await pause(2000);
  },
};
