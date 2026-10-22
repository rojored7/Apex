// US-068 T4: conmutador de tema del panel, en la TopBar. Botón real de 44 px con un texto
// accesible que dice a qué tema cambia; el icono es decorativo.
import { Moon, Sun } from "lucide-react";
import { toggleTheme, useTheme } from "./theme";
import styles from "./ThemeToggle.module.css";

export function ThemeToggle() {
  const isDark = useTheme("light") === "dark";
  const label = isDark ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
  const Icon = isDark ? Sun : Moon;
  return (
    <button type="button" className={styles.toggle} aria-label={label} title={label} onClick={toggleTheme}>
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}
