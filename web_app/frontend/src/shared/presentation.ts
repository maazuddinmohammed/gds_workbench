export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase() ?? "")
    .join("") || "G";
}

export function shortCode(code: string): string {
  return code.replace(/[^a-zA-Z0-9]/g, "").slice(0, 2).toLocaleUpperCase() || "G";
}

export function formatDateTime(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatRequiredDateTime(value: string): string {
  return formatDateTime(value) ?? "Unavailable";
}

export function zoneLabel(zone: string): string {
  return zone[0]?.toLocaleUpperCase() + zone.slice(1);
}
