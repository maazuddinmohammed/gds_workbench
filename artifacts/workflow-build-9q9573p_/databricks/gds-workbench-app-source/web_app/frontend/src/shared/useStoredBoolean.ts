import { useEffect, useState } from "react";

export function useStoredBoolean(key: string, defaultValue = false) {
  const [value, setValue] = useState(() => {
    try {
      const storedValue = window.localStorage.getItem(key);
      if (storedValue === "true") return true;
      if (storedValue === "false") return false;
    } catch {
      // Browser storage can be unavailable; the preference remains session-local.
    }
    return defaultValue;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, String(value));
    } catch {
      // The layout still works when browser storage is unavailable.
    }
  }, [key, value]);

  return [value, setValue] as const;
}
