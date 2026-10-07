/*
 * ==================================================
 * AETHER MARKUP — CODEMIRROR LANGUAGE
 * ==================================================
 *
 * Aether-specific lexer.
 *
 * Здесь НЕ пытаемся реализовать весь Markdown.
 * Markdown-подобные конструкции, которые важны
 * для Aether, распознаются отдельно:
 *
 *   headings
 *   bold
 *   italic
 *   strikethrough
 *   lists
 *   quotes
 *   links
 *
 * Aether:
 *
 *   ::widget
 *   ::widget positional=value
 *   ::widget key=value
 *   ::block
 *   ::
 *
 * Inline:
 *
 *   [text]{condition}
 *   [text](url)
 */

import {
  StreamLanguage,
} from "https://esm.sh/@codemirror/language@6";

import {
  tags as t,
} from "https://esm.sh/@lezer/highlight@1";


/* ==================================================
 * AETHER DEFINITIONS
 * ================================================== */

const BLOCKS = new Set([
  "signature",
  "log",
  "checks",
  "kv",
  "kvm",
  "timeline",
  "spoiler",
]);

const RAW_BLOCKS = new Set([
  "log",
  "checks",
  "kv",
  "kvm",
  "timeline",
]);

const CONTAINERS = new Set([
  "section",
  "box",
  "grid",
  "fold",
]);

const LINE_WIDGETS = new Set([
  "stamp",
  "barcode",
  "masthead",
  "bar",
  "image",
  "divider",
  "page",
  "site",
]);


/* ==================================================
 * STATE
 * ================================================== */

function startState() {
  return {
    block: null,
    raw: false,

    /*
     * Stack of parent Aether blocks.
     *
     * Example:
     *
     * ::section
     *   ::grid
     *
     * block      = "grid"
     * blockStack = ["section"]
     */
    blockStack: [],

    /*
     * Current Aether declaration.
     */
    widget: false,

    /*
     * Current inline construct:
     *
     * null
     * spoiler
     * link
     */
    inline: null,

    /*
     * Current inline construct phase.
     */
    inlinePhase: null,

    /*
     * Markdown inline code.
     */
    code: false,
  };
}


/* ==================================================
 * HELPERS
 * ================================================== */

function identifierStart(ch) {
  return !!ch && /[A-Za-z_]/.test(ch);
}


function identifierChar(ch) {
  return !!ch && /[A-Za-z0-9_-]/.test(ch);
}


function digit(ch) {
  return !!ch && /[0-9]/.test(ch);
}


function readIdentifier(stream) {
  const start = stream.pos;

  while (!stream.eol()) {
    if (!identifierChar(stream.peek())) {
      break;
    }

    stream.next();
  }

  return stream.string.slice(
    start,
    stream.pos
  );
}


function readString(stream) {
  const quote = stream.next();

  while (!stream.eol()) {
    const ch = stream.next();

    if (ch === "\\") {
      if (!stream.eol()) {
        stream.next();
      }

      continue;
    }

    if (ch === quote) {
      break;
    }
  }

  return "string";
}


/* ==================================================
 * AETHER LINE DETECTION
 * ================================================== */

/*
 * CodeMirror's stream.sol() means:
 *
 *   "we are physically at character 0 of the line"
 *
 * It does NOT mean:
 *
 *   "we are at the first non-whitespace character"
 *
 * Therefore:
 *
 *     ::stamp TEST
 *
 * and:
 *
 *         ::stamp TEST
 *
 * must be detected differently from ordinary
 * stream.sol() handling.
 *
 * These helpers only inspect the line from the
 * current position. They do not consume anything.
 */

function startsAetherDirective(stream) {
  if (!stream.sol()) {
    return false;
  }

  return /^\s*::/.test(
    stream.string.slice(stream.pos)
  );
}


function startsAetherClose(stream) {
  if (!stream.sol()) {
    return false;
  }

  return /^\s*::\s*$/.test(
    stream.string.slice(stream.pos)
  );
}


function startsNestedAetherDirective(stream) {
  if (!stream.sol()) {
    return false;
  }

  return /^\s*::(?!\s*$)/.test(
    stream.string.slice(stream.pos)
  );
}


/*
 * Grid metadata may also be indented:
 *
 *     -- label="AGENT"
 *     -- span=2
 */

function startsGridMetadata(stream) {
  if (!stream.sol()) {
    return false;
  }

  return /^\s*--/.test(
    stream.string.slice(stream.pos)
  );
}


/* ==================================================
 * NESTED AETHER DECLARATION
 * ================================================== */

function beginNestedAether(stream, state) {

  /*
   * Consume indentation first.
   *
   * Example:
   *
   *     ::stamp TEST
   */
  stream.eatSpace();


  /*
   * ::
   */
  stream.match(/^::/);


  /*
   * Just ::
   *
   * This is a closing marker.
   */
  if (stream.eol()) {

    /*
     * Return to the parent block.
     */
    if (state.blockStack.length) {

      const parent =
        state.blockStack.pop();

      state.block =
        parent.block;

      state.raw =
        parent.raw;

    } else {

      state.block = null;
      state.raw = false;
    }

    state.widget = false;

    return "close";
  }


  /*
   * Space after ::
   */
  stream.eatSpace();


  /*
   * Widget name.
   */
  const name =
    readIdentifier(stream);


  if (!name) {

    stream.skipToEnd();

    return "punctuation";
  }


  /*
   * Every nested Aether declaration
   * gets the same widget highlighting
   * as a top-level declaration.
   */
  state.widget = true;


  /*
   * Nested block / container.
   *
   * Save the current block before
   * replacing it.
   */
  if (
    BLOCKS.has(name) ||
    CONTAINERS.has(name)
  ) {

    if (state.block) {

      state.blockStack.push({
        block: state.block,
        raw: state.raw,
      });
    }

    state.block = name;

    state.raw =
      RAW_BLOCKS.has(name);
  }


  /*
   * One-line widget.
   *
   * It does NOT change the current
   * enclosing block.
   */
  if (
    LINE_WIDGETS.has(name)
  ) {
    /*
     * Keep the current block exactly
     * as it was.
     */
  }


  return "widget";
}


/* ==================================================
 * BLOCK TOKENIZATION
 * ================================================== */

function tokenBlock(stream, state) {

  /*
   * ------------------------------------------------
   * Closing ::
   * ------------------------------------------------
   *
   * Important:
   *
   *     ::
   *
   * and:
   *
   *         ::
   *
   * are both valid closing markers.
   */
  if (
    startsAetherClose(stream)
  ) {

    /*
     * Consume the complete closing line,
     * including indentation.
     */
    stream.skipToEnd();


    if (state.blockStack.length) {

      const parent =
        state.blockStack.pop();

      state.block =
        parent.block;

      state.raw =
        parent.raw;

    } else {

      state.block = null;
      state.raw = false;
    }

    state.widget = false;

    return "close";
  }


  /*
   * ------------------------------------------------
   * Nested Aether declaration
   * ------------------------------------------------
   *
   * This must happen BEFORE raw/content handling
   * for normal structural blocks.
   *
   * Example:
   *
   * ::section
   *
   *     ::stamp TEST
   *
   *     ::
   */
  if (
    !state.raw &&
    startsNestedAetherDirective(stream)
  ) {

    return beginNestedAether(
      stream,
      state
    );
  }


  /*
   * ------------------------------------------------
   * Raw Aether blocks
   * ------------------------------------------------
   *
   * Raw blocks deliberately do not interpret
   * nested Aether syntax.
   *
   * Example:
   *
   * ::log
   * ::stamp TEST
   * ::
   *
   * Everything inside log remains content.
   */
  if (state.raw) {

    stream.skipToEnd();

    return "content";
  }


  /*
   * ------------------------------------------------
   * Grid
   * ------------------------------------------------
   */
  if (state.block === "grid") {

    return tokenGrid(
      stream,
      state
    );
  }


  /*
   * ------------------------------------------------
   * key: value
   * ------------------------------------------------
   *
   * signature:
   *
   *     name: Ivan
   *     role: Director
   */
  if (stream.sol()) {

    const match =
      stream.string
        .slice(stream.pos)
        .match(
          /^\s*[A-Za-z_][A-Za-z0-9_-]*\s*:/
        );

    if (match) {

      stream.match(/^\s*/);

      stream.match(
        /^[A-Za-z_][A-Za-z0-9_-]*/
      );

      stream.match(/^\s*:/);

      return "property";
    }
  }


  /*
   * ------------------------------------------------
   * Quoted value
   * ------------------------------------------------
   */
  if (
    stream.peek() === '"' ||
    stream.peek() === "'"
  ) {
    return readString(stream);
  }


  /*
   * ------------------------------------------------
   * Number
   * ------------------------------------------------
   */
  if (digit(stream.peek())) {

    stream.match(
      /^[0-9]+(?:\.[0-9]+)?/
    );

    return "number";
  }


  /*
   * ------------------------------------------------
   * Markdown / inline constructs
   * ------------------------------------------------
   *
   * This allows nested content such as:
   *
   * [link](#)
   * **bold**
   * [secret]{key}
   */
  if (state.inline) {

    return tokenInline(
      stream,
      state
    );
  }


  if (
    stream.peek() === "["
  ) {

    const kind =
      detectBracketConstruct(
        stream
      );

    if (kind) {

      stream.next();

      state.inline = kind;
      state.inlinePhase = "text";

      return "bracket";
    }
  }


  /*
   * ------------------------------------------------
   * Ordinary block content
   * ------------------------------------------------
   */
  stream.skipToEnd();

  return "content";
}


/* ==================================================
 * GRID
 * ================================================== */

function tokenGrid(stream, state) {

  /*
   * ------------------------------------------------
   * Closing block
   * ------------------------------------------------
   */
  if (
    startsAetherClose(stream)
  ) {

    stream.skipToEnd();


    if (state.blockStack.length) {

      const parent =
        state.blockStack.pop();

      state.block =
        parent.block;

      state.raw =
        parent.raw;

    } else {

      state.block = null;
      state.raw = false;
    }

    state.widget = false;

    return "close";
  }


  /*
   * ------------------------------------------------
   * Nested Aether declaration
   * ------------------------------------------------
   *
   * Example:
   *
   * ::grid cols=3
   *
   *     ::stamp IMPORTANT
   *
   *     ::
   */
  if (
    startsNestedAetherDirective(stream)
  ) {

    return beginNestedAether(
      stream,
      state
    );
  }


  /*
   * ------------------------------------------------
   * Grid cell metadata
   * ------------------------------------------------
   *
   * -- label="..."
   * -- span=2
   *
   * Indentation is allowed here too.
   */
  if (
    startsGridMetadata(stream)
  ) {

    stream.eatSpace();
    stream.match(/^--/);

    return "grid";
  }


  /*
   * ------------------------------------------------
   * Existing inline construct
   * ------------------------------------------------
   */
  if (state.inline) {

    return tokenInline(
      stream,
      state
    );
  }


  /*
   * ------------------------------------------------
   * [text]{condition}
   *
   * [text](url)
   * ------------------------------------------------
   */
  if (
    stream.peek() === "["
  ) {

    const kind =
      detectBracketConstruct(
        stream
      );

    if (kind) {

      stream.next();

      state.inline = kind;
      state.inlinePhase = "text";

      return "bracket";
    }
  }


  /*
   * ------------------------------------------------
   * Cell content
   * ------------------------------------------------
   */
  if (
    stream.peek() === '"' ||
    stream.peek() === "'"
  ) {
    return readString(stream);
  }


  /*
   * ------------------------------------------------
   * Markdown inside grid
   * ------------------------------------------------
   */
  const markdown =
    tokenMarkdown(
      stream,
      state
    );

  if (markdown) {
    return markdown;
  }


  stream.skipToEnd();

  return "content";
}


/* ==================================================
 * AETHER DECLARATION
 * ================================================== */

function beginAether(stream, state) {

  /*
   * Consume indentation before ::
   *
   *     ::stamp TEST
   */
  stream.eatSpace();


  /*
   * ::
   */
  stream.match(/^::/);


  /*
   * Just ::
   */
  if (stream.eol()) {

    state.block = null;
    state.raw = false;
    state.widget = false;

    state.blockStack = [];

    return "close";
  }


  /*
   * Space after ::
   */
  stream.eatSpace();


  /*
   * Widget name.
   */
  const name =
    readIdentifier(stream);


  if (!name) {

    stream.skipToEnd();

    return "punctuation";
  }


  /*
   * Every Aether declaration starts with
   * a clearly highlighted widget name.
   */
  state.widget = true;


  /*
   * Block structures.
   */
  if (
    BLOCKS.has(name) ||
    CONTAINERS.has(name)
  ) {

    state.block = name;

    state.raw =
      RAW_BLOCKS.has(name);
  }


  /*
   * One-line widgets don't open a block.
   */
  if (
    LINE_WIDGETS.has(name)
  ) {

    state.block = null;
    state.raw = false;
  }


  return "widget";
}


/* ==================================================
 * AETHER DECLARATION PARAMETERS
 * ================================================== */

function tokenAetherLine(
  stream,
  state
) {

  /*
   * Whitespace.
   */
  if (stream.eatSpace()) {
    return null;
  }


  /*
   * Quoted positional argument.
   */
  if (
    stream.peek() === '"' ||
    stream.peek() === "'"
  ) {
    return readString(stream);
  }


  /*
   * Number.
   */
  if (digit(stream.peek())) {

    stream.match(
      /^[0-9]+(?:\.[0-9]+)?/
    );

    return "number";
  }


  /*
   * Negative number.
   */
  if (
    stream.peek() === "-" &&
    digit(
      stream.string[
        stream.pos + 1
      ]
    )
  ) {

    stream.next();

    stream.match(
      /^[0-9]+(?:\.[0-9]+)?/
    );

    return "number";
  }


  /*
   * Parameter / positional argument.
   */
  if (
    identifierStart(
      stream.peek()
    )
  ) {

    const word =
      readIdentifier(stream);


    /*
     * key=value
     */
    if (
      stream.peek() === "="
    ) {
      return "property";
    }


    /*
     * Parameter value / positional arg.
     */
    return "atom";
  }


  /*
   * Operators.
   */
  if (
    stream.match("=")
  ) {
    return "operator";
  }

  if (
    stream.match("|")
  ) {
    return "operator";
  }

  if (
    stream.match(":")
  ) {
    return "operator";
  }


  /*
   * Anything else.
   */
  stream.next();

  return null;
}


/* ==================================================
 * INLINE AETHER SPOILER / MARKDOWN LINK
 * ================================================== */

function detectBracketConstruct(stream) {

  const rest =
    stream.string.slice(
      stream.pos
    );


  /*
   * Aether spoiler:
   *
   * [text]{condition}
   */
  if (
    /^\[[^\]]*\]\{/.test(rest)
  ) {
    return "spoiler";
  }


  /*
   * Markdown link:
   *
   * [text](url)
   */
  if (
    /^\[[^\]]*\]\(/.test(rest)
  ) {
    return "link";
  }


  return null;
}


function tokenInline(
  stream,
  state
) {

  /*
   * -----------------------------------------------
   * AETHER SPOILER
   * -----------------------------------------------
   */

  if (
    state.inline === "spoiler"
  ) {

    /*
     * Hidden text.
     */
    if (
      state.inlinePhase === "text"
    ) {

      if (
        stream.peek() === "]"
      ) {
        stream.next();

        state.inlinePhase =
          "condition-open";

        return "bracket";
      }

      stream.skipTo("]");

      if (
        stream.pos === stream.start
      ) {
        stream.next();
      }

      return "content";
    }


    /*
     * Opening {
     */
    if (
      state.inlinePhase ===
        "condition-open"
    ) {

      if (
        stream.peek() === "{"
      ) {
        stream.next();

        state.inlinePhase =
          "condition";

        return "bracket";
      }

      state.inline = null;
      state.inlinePhase = null;

      return null;
    }


    /*
     * Condition.
     */
    if (
      state.inlinePhase ===
        "condition"
    ) {

      if (
        stream.peek() === "}"
      ) {
        stream.next();

        state.inline = null;
        state.inlinePhase = null;

        return "bracket";
      }


      if (
        stream.match("&&") ||
        stream.match("||") ||
        stream.match("!")
      ) {
        return "operator";
      }


      if (
        identifierStart(
          stream.peek()
        )
      ) {

        const word =
          readIdentifier(stream);

        if (
          word === "and" ||
          word === "or" ||
          word === "not"
        ) {
          return "keyword";
        }

        return "variableName";
      }


      if (
        stream.eatSpace()
      ) {
        return null;
      }


      stream.next();

      return null;
    }
  }


  /*
   * -----------------------------------------------
   * MARKDOWN LINK
   * -----------------------------------------------
   */

  if (
    state.inline === "link"
  ) {

    if (
      state.inlinePhase === "text"
    ) {

      if (
        stream.peek() === "]"
      ) {
        stream.next();

        state.inlinePhase =
          "url-open";

        return "bracket";
      }

      stream.skipTo("]");

      if (
        stream.pos === stream.start
      ) {
        stream.next();
      }

      return "linkText";
    }


    if (
      state.inlinePhase === "url-open"
    ) {

      if (
        stream.peek() === "("
      ) {
        stream.next();

        state.inlinePhase =
          "url";

        return "bracket";
      }

      state.inline = null;
      state.inlinePhase = null;

      return null;
    }


    if (
      state.inlinePhase === "url"
    ) {

      if (
        stream.peek() === ")"
      ) {
        stream.next();

        state.inline = null;
        state.inlinePhase = null;

        return "bracket";
      }

      stream.skipTo(")");

      if (
        stream.pos === stream.start
      ) {
        stream.next();
      }

      return "link";
    }
  }


  return null;
}


/* ==================================================
 * MARKDOWN
 * ================================================== */

function tokenMarkdown(
  stream,
  state
) {

  /*
   * Existing inline construct.
   *
   * Normally token() handles this, but structural
   * blocks such as grid call tokenMarkdown()
   * directly.
   */
  if (state.inline) {
    return tokenInline(
      stream,
      state
    );
  }


  /*
   * Inline Aether spoiler / Markdown link.
   */
  if (
    stream.peek() === "["
  ) {

    const kind =
      detectBracketConstruct(
        stream
      );

    if (kind) {

      stream.next();

      state.inline = kind;
      state.inlinePhase = "text";

      return "bracket";
    }
  }


  /*
   * Inline code.
   */
  if (
    stream.peek() === "`"
  ) {

    stream.next();

    state.code =
      !state.code;

    return "string";
  }


  if (state.code) {

    stream.skipTo("`");

    if (
      stream.pos === stream.start
    ) {
      stream.next();
    }

    return "string";
  }


  /*
   * Heading.
   */
  if (
    stream.sol() &&
    stream.match(
      /^#{1,6}(?=\s)/
    )
  ) {
    stream.skipToEnd();

    return "heading";
  }


  /*
   * Block quote.
   */
  if (
    stream.sol() &&
    stream.match(/^>\s?/)
  ) {
    return "quote";
  }


  /*
   * Unordered list.
   */
  if (
    stream.sol() &&
    stream.match(
      /^[-*+](?=\s)/
    )
  ) {
    return "list";
  }


  /*
   * Ordered list.
   */
  if (
    stream.sol() &&
    stream.match(
      /^\d+\.(?=\s)/
    )
  ) {
    return "list";
  }


  /*
   * Strong.
   */
  if (
    stream.match("**")
  ) {
    return "strong";
  }


  /*
   * Emphasis.
   */
  if (
    stream.match("*")
  ) {
    return "emphasis";
  }


  /*
   * Strikethrough.
   */
  if (
    stream.match("~~")
  ) {
    return "strikethrough";
  }


  /*
   * Table separator.
   */
  if (
    stream.sol() &&
    /^\s*\|?(?:\s*:?-+:?\s*\|)+/.test(
      stream.string.slice(stream.pos)
    )
  ) {
    stream.skipToEnd();

    return "table";
  }


  return null;
}


/* ==================================================
 * MAIN TOKENIZER
 * ================================================== */

function token(
  stream,
  state
) {

  /*
   * -----------------------------------------------
   * Existing Aether block
   * -----------------------------------------------
   */

  if (state.block) {

    return tokenBlock(
      stream,
      state
    );
  }


  /*
   * -----------------------------------------------
   * New Aether declaration
   * -----------------------------------------------
   *
   * IMPORTANT:
   *
   * We check for optional indentation here.
   *
   * Both:
   *
   * ::stamp TEST
   *
   * and:
   *
   *     ::stamp TEST
   *
   * are Aether declarations.
   */
  if (
    startsAetherDirective(stream)
  ) {

    state.widget = false;

    return beginAether(
      stream,
      state
    );
  }


  /*
   * -----------------------------------------------
   * Aether declaration remainder
   * -----------------------------------------------
   */

  if (state.widget) {

    const result =
      tokenAetherLine(
        stream,
        state
      );

    if (stream.eol()) {
      state.widget = false;
    }

    return result;
  }


  /*
   * -----------------------------------------------
   * Existing inline construct
   * -----------------------------------------------
   */

  if (state.inline) {
    return tokenInline(
      stream,
      state
    );
  }


  /*
   * -----------------------------------------------
   * [ ... ]{...} or [ ... ](...)
   * -----------------------------------------------
   */

  if (
    stream.peek() === "["
  ) {

    const kind =
      detectBracketConstruct(
        stream
      );

    if (kind) {

      stream.next();

      state.inline = kind;
      state.inlinePhase = "text";

      return "bracket";
    }
  }


  /*
   * -----------------------------------------------
   * Markdown
   * -----------------------------------------------
   */

  const markdown =
    tokenMarkdown(
      stream,
      state
    );

  if (markdown) {
    return markdown;
  }


  /*
   * -----------------------------------------------
   * Comments
   * -----------------------------------------------
   */

  if (
    stream.sol() &&
    stream.peek() === "#"
  ) {
    stream.skipToEnd();

    return "comment";
  }


  /*
   * -----------------------------------------------
   * Whitespace
   * -----------------------------------------------
   */

  if (
    stream.eatSpace()
  ) {
    return null;
  }


  /*
   * -----------------------------------------------
   * Strings
   * -----------------------------------------------
   */

  if (
    stream.peek() === '"' ||
    stream.peek() === "'"
  ) {
    return readString(stream);
  }


  /*
   * -----------------------------------------------
   * Numbers
   * -----------------------------------------------
   */

  if (
    digit(stream.peek())
  ) {

    stream.match(
      /^[0-9]+(?:\.[0-9]+)?/
    );

    return "number";
  }


  /*
   * -----------------------------------------------
   * Plain identifier
   * -----------------------------------------------
   */

  if (
    identifierStart(
      stream.peek()
    )
  ) {

    readIdentifier(stream);

    return "variableName";
  }


  /*
   * -----------------------------------------------
   * Operators
   * -----------------------------------------------
   */

  if (
    stream.match("=") ||
    stream.match("|") ||
    stream.match(":")
  ) {
    return "operator";
  }


  /*
   * -----------------------------------------------
   * Default
   * -----------------------------------------------
   */

  stream.next();

  return null;
}


/* ==================================================
 * LANGUAGE
 * ================================================== */

export const aetherLanguage =
  StreamLanguage.define({

    name: "aether",

    startState,

    copyState(state) {
      return {
        block:
          state.block,

        raw:
          state.raw,

        /*
         * IMPORTANT:
         *
         * blockStack must be copied deeply.
         * Otherwise CodeMirror's incremental
         * parser can mutate states that belong
         * to another document position.
         */
        blockStack:
          state.blockStack.map(
            (item) => ({
              block: item.block,
              raw: item.raw,
            })
          ),

        widget:
          state.widget,

        inline:
          state.inline,

        inlinePhase:
          state.inlinePhase,

        code:
          state.code,
      };
    },

    token,

    tokenTable: {

      widget:
        t.keyword,

      keyword:
        t.keyword,

      property:
        t.propertyName,

      string:
        t.string,

      number:
        t.number,

      variableName:
        t.variableName,

      atom:
        t.atom,

      content:
        t.content,

      comment:
        t.comment,

      operator:
        t.operator,

      bracket:
        t.bracket,

      close:
        t.punctuation,

      grid:
        t.labelName,

      heading:
        t.heading,

      strong:
        t.strong,

      emphasis:
        t.emphasis,

      strikethrough:
        t.strikethrough,

      list:
        t.list,

      quote:
        t.quote,

      table:
        t.punctuation,

      link:
        t.link,

      linkText:
        t.link,

      punctuation:
        t.punctuation,
    },

    languageData: {
      commentTokens: {
        line: "#",
      },
    },

  });