// US-053 T5: un rol sin la acción de la ruta ve "Sin permiso" dentro de su layout, con un
// enlace a su inicio. Ocultar no reemplaza el 403 del api (RN-15).
// DESIGN-GAP: la página "Sin permiso" no está en el diseño (docs/design/screens/).
import { MessagePage } from "../../shared/ui/MessagePage";
import { homeFor } from "./routeAccess";
import { useRole } from "./useCan";

export function NoPermissionPage() {
  return (
    <MessagePage
      title="Sin permiso"
      message="Tu rol no tiene acceso a esta pantalla. Si la necesitas, pídesela a un administrador."
      linkLabel="Ir al inicio"
      linkTo={homeFor(useRole())}
    />
  );
}
