// S2-D25: Inicio mínima hasta GET /dashboard (Sprint 3): saludo con el correo y accesos a lo
// que el Sprint 2 trae para el rol.
// DESIGN-GAP: Inicio.html trae KPIs, "Hoy en el box", "Por avisar hoy", asistencia y últimos
// movimientos; llegan con GET /dashboard (S3). El nombre de la persona llega con US-110.
import { Link } from "react-router";
import { Can, useSession, type Action } from "../../../core/auth";
import { PageHeader } from "../../../shared/ui/PageHeader";
import styles from "./InicioPage.module.css";

interface Shortcut {
  label: string;
  to: string;
  action: Action;
  note: string;
}

const SHORTCUTS: readonly Shortcut[] = [
  { label: "Socios", to: "/socios", action: "members.view", note: "Registrar y buscar socios." },
  { label: "Planes", to: "/planes", action: "plans.view", note: "Crear y revisar los planes del gimnasio." },
  { label: "Usuarios y roles", to: "/sistema/usuarios", action: "users.manage", note: "Cuentas del equipo y enlaces de activación." },
  { label: "Configuración", to: "/sistema/configuracion", action: "settings.manage", note: "Datos del gimnasio, privacidad y membresías." },
];

export default function InicioPage() {
  const { user } = useSession();
  return (
    <div className={styles.page}>
      <PageHeader title={user ? `Hola, ${user.email}` : "Inicio"} />
      <p className={styles.note}>El tablero con socios al día, vencimientos e ingresos llega en la próxima versión.</p>
      <nav aria-label="Accesos rápidos">
        <ul className={styles.grid}>
          {SHORTCUTS.map((shortcut) => (
            <Can key={shortcut.to} action={shortcut.action}>
              <li>
                <Link to={shortcut.to} className={styles.card} aria-describedby={`acceso-${shortcut.action}`}>
                  {shortcut.label}
                </Link>
                <p id={`acceso-${shortcut.action}`} className={styles.cardNote}>
                  {shortcut.note}
                </p>
              </li>
            </Can>
          ))}
        </ul>
      </nav>
    </div>
  );
}
