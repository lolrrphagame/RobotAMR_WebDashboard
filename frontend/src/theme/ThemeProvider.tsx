import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { ReactNode } from "react";

export type ThemePreference = "light" | "dark" | "system";
type ThemeState = { preference: ThemePreference; resolved: "light" | "dark" };
declare global {
  interface Window {
    pbl4Theme: {
      key: string;
      apply: (value: string | null, persist?: boolean) => ThemeState;
    };
  }
}
const ThemeContext = createContext<
  (ThemeState & { setPreference: (value: ThemePreference) => void }) | null
>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ThemeState>(() =>
    window.pbl4Theme.apply(
      document.documentElement.dataset.themePreference ?? "system",
    ),
  );
  const setPreference = useCallback(
    (value: ThemePreference) => setState(window.pbl4Theme.apply(value, true)),
    [],
  );
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: light)");
    const systemChanged = () => {
      if (document.documentElement.dataset.themePreference === "system")
        setState(window.pbl4Theme.apply("system"));
    };
    const stored = (event: StorageEvent) => {
      if (event.key === window.pbl4Theme.key || event.key === null)
        setState(window.pbl4Theme.apply(event.newValue));
    };
    query.addEventListener("change", systemChanged);
    window.addEventListener("storage", stored);
    return () => {
      query.removeEventListener("change", systemChanged);
      window.removeEventListener("storage", stored);
    };
  }, []);
  return (
    <ThemeContext.Provider value={{ ...state, setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw Error("ThemeProvider is required");
  return context;
}
