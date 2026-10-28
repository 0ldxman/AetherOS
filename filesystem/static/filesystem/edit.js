(function () {
  const root = document.querySelector("[data-edit-url]");
  const area = document.querySelector("[data-edit-area]");
  const button = document.querySelector("[data-edit-save]");
  const status = document.querySelector("[data-viewer-status]");
  if (!root || !area || !button) { return; }

  let saved = area.value;
  const say = function (text) { if (status) { status.textContent = text; } };
  const csrf = function () {
    const found = document.cookie.split("; ").find(function (row) { return row.startsWith("csrftoken="); });
    return found ? decodeURIComponent(found.split("=")[1]) : "";
  };

  async function save() {
    say("SAVING");
    try {
      const response = await fetch(root.dataset.editUrl, {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
        body: JSON.stringify({text: area.value}),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) { say((data.error || "ERROR").toUpperCase()); return; }
      saved = area.value;
      say("SAVED");
    } catch (error) { say("ERROR"); }
  }

  area.addEventListener("input", function () { say(area.value === saved ? "READY" : "MODIFIED"); });
  area.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save(); }
  });
  button.addEventListener("click", save);
  say("READY");
})();
