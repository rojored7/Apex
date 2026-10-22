// US-062 T3: marco de las pantallas de la tablet del box (CheckIn.html y
// Resultados_Registro.html).
// - Tema oscuro forzado sin depender de la preferencia del sistema; se restaura al salir.
// - --control pasa a --control-gym (56 px) en el contenedor: Button y Field miden 56 px sin
//   variantes nuevas.
// - Barra mínima con la salida, el nombre de la sesión y un subtítulo; sin menú lateral.
import { ChevronLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link, Outlet } from "react-router";
import { useForcedTheme } from "../shared/hooks/useForcedTheme";
import styles from "./GymLayout.module.css";

export interface GymLayoutProps {
  title: string;
  subtitle?: string | undefined;
  exitTo: string;
  exitLabel?: string;
  children?: ReactNode;
}

export function GymLayout({ title, subtitle, exitTo, exitLabel = "Salir", children }: GymLayoutProps) {
  useForcedTheme("dark");
  return (
    <div className={styles.root}>
      <header className={styles.bar}>
        <Link to={exitTo} className={styles.exit}>
          <ChevronLeft size={20} aria-hidden="true" />
          {exitLabel}
        </Link>
        <div className={styles.titles}>
          <h1 className={styles.title}>{title}</h1>
          {subtitle !== undefined && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
      </header>
      <main className={styles.content}>{children ?? <Outlet />}</main>
    </div>
  );
}
