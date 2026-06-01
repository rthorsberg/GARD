import { Moon, Sun, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme, type Theme } from "@/hooks/useTheme";

const cycle: Theme[] = ["light", "dark", "system"];

function nextTheme(current: Theme): Theme {
  const i = cycle.indexOf(current);
  return cycle[(i + 1) % cycle.length]!;
}

function label(theme: Theme): string {
  if (theme === "light") return "Light mode";
  if (theme === "dark") return "Dark mode";
  return "System theme";
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <Button
      variant="outline"
      size="icon"
      aria-label={label(theme)}
      title={label(theme)}
      onClick={() => setTheme(nextTheme(theme))}
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}
