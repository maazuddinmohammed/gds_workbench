// The Stage Runner bundles the same generated table used by the GDS local helper.
// @ts-expect-error The shared generated CommonJS asset intentionally has no declaration file.
import unicodeModule from "../../gds/skills/gds/workbench/unicode.js";

const unicode = unicodeModule as {
  casefold(value: string): string;
  lower(value: string): string;
};

export const unicodeCasefold = unicode.casefold;
export const unicodeLower = unicode.lower;
