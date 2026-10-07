/*
 * ==================================================
 * AETHER MARKUP — FOLDING
 * ==================================================
 *
 * Folding для:
 *
 *   ::signature
 *   ::log
 *   ::checks
 *   ::kv
 *   ::kvm
 *   ::timeline
 *   ::spoiler
 *
 *   ::section
 *   ::box
 *   ::grid
 *   ::fold
 *
 * Поддерживается вложенность.
 *
 * RAW-блоки:
 *
 *   ::log
 *   ::checks
 *   ::kv
 *   ::kvm
 *   ::timeline
 *
 * Внутри RAW-блока содержимое не разбирается
 * как Aether markup.
 */

import {
  foldService,
  foldGutter,
} from "https://esm.sh/@codemirror/language@6";


/* ==================================================
 * BLOCK DEFINITIONS
 * ================================================== */

const FOLDABLE = new Set([
  "signature",
  "log",
  "checks",
  "kv",
  "kvm",
  "timeline",
  "spoiler",

  "section",
  "box",
  "grid",
  "fold",
]);


/*
 * Эти блоки содержат произвольный raw-текст.
 *
 * Поэтому ::something внутри них не должно
 * восприниматься как вложенный Aether-блок.
 */
const RAW_BLOCKS = new Set([
  "log",
  "checks",
  "kv",
  "kvm",
  "timeline",
]);


/* ==================================================
 * PARSE LINE
 * ================================================== */

function parseDirective(line) {

  const match =
    line.match(
      /^\s*::([a-z][a-z0-9_]*)\b/
    );

  if (!match) {
    return null;
  }

  return match[1];
}


function isClose(line) {

  return /^\s*::\s*$/.test(
    line
  );
}


/* ==================================================
 * FIND FOLD
 * ================================================== */

function findFold(
  state,
  lineStart
) {

  const line =
    state.doc.lineAt(
      lineStart
    );

  const name =
    parseDirective(
      line.text
    );


  /*
   * Fold marker появляется только
   * на действительно foldable-блоках.
   */
  if (
    !name ||
    !FOLDABLE.has(name)
  ) {
    return null;
  }


  /*
   * Stack содержит открытые блоки.
   *
   * Для каждого элемента:
   *
   *   {
   *     name: "section",
   *     raw: false
   *   }
   */
  const stack = [
    {
      name,
      raw:
        RAW_BLOCKS.has(name),
    },
  ];


  /*
   * Ищем соответствующий закрывающий ::
   */
  for (
    let number =
      line.number + 1;

    number <=
      state.doc.lines;

    number++
  ) {

    const current =
      state.doc.line(
        number
      );

    const text =
      current.text;


    /*
     * --------------------------------------------------
     * RAW BLOCK
     * --------------------------------------------------
     *
     * Внутри raw-блока ничего не разбираем.
     *
     * Единственное, что нас интересует —
     * его собственный закрывающий ::
     */
    if (
      stack.length > 0 &&
      stack[stack.length - 1].raw
    ) {

      if (
        isClose(text)
      ) {

        stack.pop();

        /*
         * Закрыли исходный блок.
         */
        if (
          stack.length === 0
        ) {

          return {
            from:
              line.to,

            to:
              current.from,
          };
        }
      }

      continue;
    }


    /*
     * --------------------------------------------------
     * CLOSING MARKER
     * --------------------------------------------------
     */

    if (
      isClose(text)
    ) {

      stack.pop();


      /*
       * Закрыли исходный блок.
       */
      if (
        stack.length === 0
      ) {

        return {
          from:
            line.to,

          to:
            current.from,
        };
      }

      continue;
    }


    /*
     * --------------------------------------------------
     * NESTED AETHER BLOCK
     * --------------------------------------------------
     */

    const nested =
      parseDirective(
        text
      );

    if (
      nested &&
      FOLDABLE.has(nested)
    ) {

      stack.push({
        name:
          nested,

        raw:
          RAW_BLOCKS.has(
            nested
          ),
      });

      continue;
    }
  }


  /*
   * Если закрывающий ::
   * не найден — folding отсутствует.
   */
  return null;
}


/* ==================================================
 * FOLD SERVICE
 * ================================================== */

export const aetherFoldService =
  foldService.of(
    (state, lineStart) => {

      return findFold(
        state,
        lineStart
      );
    }
  );


/* ==================================================
 * FOLD GUTTER
 * ================================================== */

export const aetherFoldGutter =
  foldGutter({

    openText:
      "▸",

    closeText:
      "▾",

    markerDOM:
      (open) => {

        const marker =
          document.createElement(
            "span"
          );

        marker.className =
          open
            ? "aether-fold-marker aether-fold-marker--open"
            : "aether-fold-marker aether-fold-marker--closed";

        marker.textContent =
          open
            ? "▸"
            : "▾";

        return marker;
      },

  });