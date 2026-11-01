// The Atlas Bridge bundles the same generated table used by the Atlas local helper.
// @ts-expect-error The shared generated CommonJS asset intentionally has no declaration file.
import unicodeModule from "../../atlas-plugin/atlas-local-workbench/unicode.js";

const unicode = unicodeModule as {
  casefold(value: string): string;
  lower(value: string): string;
};

export const unicodeCasefold = unicode.casefold;
export const unicodeLower = unicode.lower;
