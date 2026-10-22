// S2-F2: marco de las pantallas de acceso (Login.html): tarjeta centrada sobre --surface con
// el logo de fondo claro, siempre en tema claro. Las tarjetas (login, recuperar,
// restablecer, cambiar contraseña) llegan en S2-F3 y S2-F4a como hijos o por la ruta.
import type { ReactNode } from "react";
import { Outlet } from "react-router";
import { useForcedTheme } from "../shared/hooks/useForcedTheme";
import styles from "./AccessLayout.module.css";

export function AccessLayout({ children }: { children?: ReactNode }) {
  useForcedTheme("light");
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <img className={styles.logo} src="/brand/apex-logo-light-bg.png" alt="APEX Hybrid Training" width={198} height={56} />
        {children ?? <Outlet />}
      </div>
    </main>
  );
}
