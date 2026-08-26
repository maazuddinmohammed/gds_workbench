"""Regenerate the static Unicode casefold tables used by non-Python plugin runtimes."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKBENCH = REPOSITORY_ROOT / "plugins" / "v2" / "gds" / "skills" / "gds" / "workbench"


def main() -> None:
    mapping = {
        str(codepoint): folded
        for codepoint in range(0x110000)
        if (folded := chr(codepoint).casefold()) != chr(codepoint)
    }
    encoded = json.dumps(mapping, ensure_ascii=True, separators=(",", ":"))
    (WORKBENCH / "unicode-casefold.json").write_text(encoded + "\n", encoding="utf-8")
    source = f"""(function (root, factory) {{
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSUnicode = api;
}})(typeof globalThis === "object" ? globalThis : this, function () {{
  "use strict";
  const casefoldMap = {encoded};
  function casefold(value) {{
    let result = "";
    for (const character of value) {{
      result += casefoldMap[character.codePointAt(0)] ?? character;
    }}
    return result;
  }}
  return {{ casefold, lower: (value) => value.toLowerCase() }};
}});
"""
    (WORKBENCH / "unicode.js").write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
