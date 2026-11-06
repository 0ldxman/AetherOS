<script lang="ts">
  // Живой предпросмотр текста по его формату: формат с разметкой рисуется как документ, остальные (и несуществующие) как есть.
  // Запросы идут по одному и не чаще раза в 300 мс (первый сразу), ответ подменяет страницу в рамке на месте, без перезагрузки
  // оформления и со своей прокруткой. Используется для объекта и для файла без объекта.
  import { untrack } from "svelte";
  import { api, type Schemas } from "./api";

  let { format, title, body, meta = "", only = "body", keysMode = "all", issues = $bindable([]) }: {
    format: string;
    title: string;
    body: string;
    meta?: string;
    only?: "body" | "infobox";
    keysMode?: "all" | "none";
    issues?: Schemas["Issue"][];
  } = $props();

  type Sent = { format: string; title: string; body: string; meta: string; mode: string; only: "body" | "infobox" };
  let busy = false;
  let sentAt = 0;
  let wake: ReturnType<typeof setTimeout>;
  let latest: Sent | null = null;
  let lastKey = "";

  $effect(() => {
    const snapshot: Sent = { format, title, body, meta, mode: keysMode, only };
    const key = JSON.stringify(snapshot);
    if (key === lastKey) return;
    lastKey = key;
    latest = snapshot;
    untrack(pump);
  });

  function pump() {
    if (busy || !latest) return;
    const wait = sentAt + 300 - Date.now();
    if (wait > 0) {
      clearTimeout(wake);
      wake = setTimeout(pump, wait);
      return;
    }
    const sent = latest;
    latest = null;
    busy = true;
    sentAt = Date.now();
    api.POST("/studio/api/items/preview", {
      body: { format: sent.format, title: sent.title, body: sent.body, meta: sent.meta, keys: { mode: sent.mode, slugs: [] }, only: sent.only },
    }).then(({ data }) => {
      busy = false;
      if (data) {
        issues = [...(data.issues.body ?? []), ...(data.issues.infobox ?? [])];
        show(sent.only === "body" ? data.body : data.infobox);
      }
      pump();
    });
  }

  // страницы документов прячут горизонтальный выход за край; в предпросмотре его нужно уметь прокрутить
  const SCROLLABLE = "<style>html,body{overflow-x:auto!important}.page,.md--body{overflow-x:visible!important}</style>";
  // то, что оживляют скрипты страницы при загрузке: такую страницу подменять на месте нельзя
  const LIVE = /widget|<audio|<video|map-embed|<script/;
  const sheets = (doc: Document) => [...doc.querySelectorAll("link[rel=stylesheet]")].map((link) => link.getAttribute("href")).join();

  let frame = $state<HTMLIFrameElement>();
  let loaded = false;
  let scroll = { x: 0, y: 0 };

  function reframe(html: string) {
    const win = frame?.contentWindow;
    if (win && loaded) scroll = { x: win.scrollX, y: win.scrollY };
    loaded = false;
    if (frame) frame.srcdoc = html + SCROLLABLE;
  }

  function show(html: string) {
    const doc = frame?.contentDocument;
    if (!frame || !doc || !loaded) return reframe(html);
    const next = new DOMParser().parseFromString(html, "text/html");
    if (sheets(next) !== sheets(doc) || LIVE.test(doc.body.innerHTML) || LIVE.test(next.body.innerHTML)) return reframe(html);
    doc.body.className = next.body.className;
    doc.body.innerHTML = next.body.innerHTML;
  }

  function framed() {
    if (!frame?.srcdoc) return;
    loaded = true;
    frame?.contentWindow?.scrollTo(scroll.x, scroll.y);
  }
</script>

<iframe title="Предпросмотр" bind:this={frame} onload={framed}></iframe>

<style>
  iframe { flex: 1; width: 100%; min-height: 0; border: 0; background: #fff; }
</style>
