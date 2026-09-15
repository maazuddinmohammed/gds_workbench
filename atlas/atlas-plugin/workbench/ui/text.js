(function (root) {
  "use strict";
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function label(value) {
    return String(value || "")
      .split("_")
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  }

  function valueText(value) {
    if (value === undefined) return "Missing";
    if (value === null) return "null";
    if (value === "") return 'Empty string';
    if (value === true) return "Yes";
    if (value === false) return "No";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }
  const api = { escapeHtml, label, valueText };
  root.AtlasText = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(globalThis);
