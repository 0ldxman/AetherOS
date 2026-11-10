// Excalidraw (React) внутри Студии (Svelte): монтируется в элемент страницы, грузится отдельным куском только для доски.
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { CaptureUpdateAction, convertToExcalidrawElements, Excalidraw, reconcileElements } from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";

type Props = Record<string, unknown>;

export function mountBoard(host: HTMLElement, props: Props): () => void {
  const root = createRoot(host);
  root.render(createElement(Excalidraw, {
    langCode: "ru-RU",
    theme: "dark",
    isCollaborating: true,
    UIOptions: { canvasActions: { loadScene: false, saveToActiveFile: false } },
    ...props,
  }));
  return () => root.unmount();
}

export { CaptureUpdateAction, convertToExcalidrawElements, reconcileElements };
