import { Monitor, Moon, Sun } from "lucide-react";
import { useId } from "react";
import { useTheme } from "./ThemeProvider";

export function ThemeSelector({
  label = "Dashboard theme",
}: {
  label?: string;
}) {
  const { preference, setPreference } = useTheme();
  const id = useId();
  return (
    <fieldset className="theme-selector" aria-label={label}>
      <legend className="sr-only">{label}</legend>
      {(
        [
          { value: "light", label: "Light", Icon: Sun },
          { value: "dark", label: "Dark", Icon: Moon },
          { value: "system", label: "System", Icon: Monitor },
        ] as const
      ).map(({ value, label: name, Icon }) => (
        <label
          key={value}
          className="theme-choice"
          data-selected={preference === value}
          title={`${name} theme`}
        >
          <input
            type="radio"
            name={id}
            value={value}
            checked={preference === value}
            onChange={() => setPreference(value)}
            aria-label={`${name} theme`}
          />
          <Icon size={15} aria-hidden="true" />
          <span>{name}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function ThemePreferences() {
  const { resolved } = useTheme();
  return (
    <section className="panel theme-preferences">
      <div>
        <span className="eyebrow">THIS BROWSER / APPEARANCE</span>
        <h2>Theme preference</h2>
        <p className="muted">
          Choose Light, Dark or follow your system. Currently {resolved}. Saved
          only on this browser/device.
        </p>
      </div>
      <ThemeSelector label="Settings theme" />
    </section>
  );
}
