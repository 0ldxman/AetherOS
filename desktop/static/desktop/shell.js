/* ==================================================
   Оболочка: общие компоненты, которые шаблон стиля (desktop/shells/<стиль>.html) расставляет как хочет.
   Подключается после desktop.js и пользуется его openApp, openWindows, openMeta и focusOrder.

   Разметка шаблона связывается с кодом атрибутами data-shell:
     launcher        кнопка, открывает и закрывает панель лаунчера
     launcher-panel  сама панель (атрибут hidden), в ней могут быть search, apps, tasks
     search          поле поиска по приложениям
     apps            список приложений стола; с data-dock отмечает запущенные
     tasks           список открытых окон: клик фокусирует, повторный клик сворачивает
     notices-toggle  кнопка центра уведомлений (внутри может быть notices-count с числом непрочитанных)
     notices-panel   панель центра уведомлений (атрибут hidden), в ней notices (список) и notices-clear (очистить)
   Горячая клавиша: отдельное нажатие Meta (Super) открывает и закрывает лаунчер.
   ================================================== */

(function () {
  const all = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const panel = document.querySelector('[data-shell="launcher-panel"]');
  const search = document.querySelector('[data-shell="search"]');
  const openers = all('[data-shell="launcher"]');

  // приложения берутся с иконок стола: так список всегда совпадает с тем, что доступно игроку
  function apps() {
    return all("#icons .icon:not(.is-closed)").map((icon) => {
      const glyph = icon.querySelector(".icon-glyph");
      const badge = icon.querySelector(".icon-badge");

      return {
        id: icon.dataset.app,
        url: icon.dataset.url,
        label: icon.querySelector(".icon-label").textContent.trim(),
        glyph: Array.from(glyph.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => node.textContent).join("").trim(),
        badge: badge ? badge.textContent : "",
      };
    });
  }

  function part(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function button(className, info) {
    const node = part("button", className);
    node.type = "button";
    node.dataset.app = info.id;
    node.append(part("span", "shell-glyph"), part("span", "shell-label"));
    return node;
  }

  // Обновляет кнопку на месте: перерисовка на каждый blur окна заменяла бы кнопку между нажатием и отпусканием, и клик терялся бы.
  function fill(node, info, classes) {
    node.title = info.label;
    node.querySelector(".shell-glyph").textContent = info.glyph;
    node.querySelector(".shell-label").textContent = info.label;

    let badge = node.querySelector(".shell-badge");
    if (info.badge && !badge) node.append((badge = part("span", "shell-badge")));
    if (badge) {
      if (info.badge) badge.textContent = info.badge;
      else badge.remove();
    }

    ["is-open", "is-active", "is-min"].forEach((name) => node.classList.toggle(name, classes.includes(name)));
  }

  // Приводит содержимое контейнера к списку rows ({info, classes}), сохраняя уже созданные кнопки.
  function sync(container, className, rows) {
    const have = new Map(Array.from(container.children).map((node) => [node.dataset.app, node]));
    const nodes = rows.map(({ info, classes }) => {
      const node = have.get(String(info.id)) || button(className, info);
      fill(node, info, classes);
      return node;
    });

    const same = nodes.length === container.children.length && nodes.every((node, index) => node === container.children[index]);
    if (!same) container.replaceChildren(...nodes);
  }

  function renderApps(container) {
    const dock = "dock" in container.dataset;
    const term = container.closest('[data-shell="launcher-panel"]') && search ? search.value.trim().toLowerCase() : "";

    sync(
      container,
      "shell-app",
      apps()
        .filter((info) => !term || info.label.toLowerCase().includes(term))
        .map((info) => ({ info, classes: dock && openWindows[info.id] ? ["is-open"] : [] }))
    );
  }

  function renderTasks(container) {
    const front = String(focusOrder[focusOrder.length - 1]);
    const known = Object.fromEntries(apps().map((info) => [info.id, info]));

    sync(
      container,
      "shell-task",
      Object.keys(openWindows).map((id) => {
        const meta = openMeta[id] || {};
        const info = { id, label: meta.label || id, glyph: known[id] ? known[id].glyph : "▢", badge: "" };
        return { info, classes: openWindows[id].min ? ["is-min"] : id === front ? ["is-active"] : [] };
      })
    );
  }

  function render() {
    all('[data-shell="apps"]').forEach(renderApps);
    all('[data-shell="tasks"]').forEach(renderTasks);
  }

  function setLauncher(open) {
    if (!panel) return;
    if (open && typeof setNotices === "function" && noticePanel && !noticePanel.hidden) setNotices(false);
    panel.hidden = !open;
    document.body.classList.toggle("launcher-open", open);
    openers.forEach((node) => node.setAttribute("aria-expanded", open ? "true" : "false"));

    if (open && search) {
      search.value = "";
      render();
      search.focus();
    }
  }

  /* ---------- центр уведомлений: история тостов ---------- */

  const NOTICE_LIMIT = 30;
  const noticePanel = document.querySelector('[data-shell="notices-panel"]');
  const noticeTogglers = all('[data-shell="notices-toggle"]');
  const history = [];
  let unread = 0;

  function renderNotices() {
    all('[data-shell="notices"]').forEach((list) => {
      list.replaceChildren(
        ...history.map((item) => {
          const node = part("button", "shell-notice shell-notice--" + item.kind);
          node.type = "button";
          node.append(part("strong", "shell-notice-title", item.title), part("span", "shell-notice-time", item.time));
          if (item.text) node.append(part("span", "shell-notice-text", item.text));
          node.addEventListener("click", () => {
            setNotices(false);
            if (item.onClick) item.onClick();
          });
          return node;
        })
      );
      list.classList.toggle("is-empty", history.length === 0);
    });

    all('[data-shell="notices-count"]').forEach((node) => {
      node.textContent = unread > 9 ? "9+" : String(unread);
      node.hidden = unread === 0;
    });
  }

  function setNotices(open) {
    if (!noticePanel) return;
    if (open) setLauncher(false);
    noticePanel.hidden = !open;
    noticeTogglers.forEach((node) => node.setAttribute("aria-expanded", open ? "true" : "false"));
    if (open) {
      unread = 0;
      all("#toasts .toast").forEach((toast) => toast.remove()); // они уже есть в списке
    }
    renderNotices();
  }

  document.addEventListener("desktop:notice", (event) => {
    const now = new Date();
    history.unshift({ ...event.detail, time: now.toTimeString().slice(0, 5) });
    history.length = Math.min(history.length, NOTICE_LIMIT);
    if (!noticePanel || noticePanel.hidden) unread += 1;
    renderNotices();
  });

  noticeTogglers.forEach((node) =>
    node.addEventListener("click", () => setNotices(noticePanel ? noticePanel.hidden : false))
  );

  all('[data-shell="notices-clear"]').forEach((node) =>
    node.addEventListener("click", () => {
      history.length = 0;
      renderNotices();
    })
  );

  document.addEventListener("desktop:windows", render);
  document.addEventListener("shell:close", () => setLauncher(false));

  openers.forEach((node) =>
    node.addEventListener("click", () => setLauncher(panel ? panel.hidden : false))
  );

  document.addEventListener("click", (event) => {
    const appButton = event.target.closest(".shell-app");
    const taskButton = event.target.closest(".shell-task");

    if (appButton) {
      const icon = all("#icons .icon").find((item) => item.dataset.app === appButton.dataset.app);
      if (icon) openApp(icon.dataset.app, icon.querySelector(".icon-label").textContent.trim(), icon.dataset.url);
      setLauncher(false);
    } else if (taskButton) {
      const win = openWindows[taskButton.dataset.app];
      if (!win) return;
      const front = String(focusOrder[focusOrder.length - 1]) === taskButton.dataset.app;

      if (win.min) {
        win.restore();
        win.focus();
      } else if (front) {
        win.minimize();
      } else {
        win.focus();
      }
      setLauncher(false);
    }
  });

  if (search) {
    search.addEventListener("input", () => all('[data-shell="apps"]').forEach(renderApps));
    search.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const first = panel.querySelector(".shell-app");
      if (first) first.click();
    });
  }

  document.addEventListener("pointerdown", (event) => {
    if (noticePanel && !noticePanel.hidden && !noticePanel.contains(event.target) && !noticeTogglers.some((node) => node.contains(event.target))) {
      setNotices(false);
    }
    if (panel && !panel.hidden && !panel.contains(event.target) && !openers.some((node) => node.contains(event.target))) {
      setLauncher(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (panel && !panel.hidden) setLauncher(false);
      if (noticePanel && !noticePanel.hidden) setNotices(false);
    }
  });

  // Super: отдельное нажатие (без других клавиш) открывает и закрывает лаунчер
  let superAlone = false;

  document.addEventListener("keydown", (event) => {
    superAlone = event.key === "Meta" && !event.repeat;
  });

  document.addEventListener("keyup", (event) => {
    if (event.key === "Meta" && superAlone && panel) setLauncher(panel.hidden);
    superAlone = false;
  });

  // клик внутри окна приложения (iframe) сюда не доходит, но снимает фокус с документа
  window.addEventListener("blur", () => {
    setLauncher(false);
    setNotices(false);
  });

  render();
  renderNotices();
})();
