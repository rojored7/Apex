// Plazo de inactividad del modo tablet (S7-D24). Vive en un módulo .ts sin CSS para que la spec E2E de kiosk-idle y GymLayout
// compartan UNA constante (antes la spec guardaba un espejo que podía divergir sin que nadie lo notara; V7 L12).

/** Diez minutos sin tocar la tablet cierran la sesión (S7-D24). */
export const TABLET_IDLE_MS = 10 * 60 * 1000;
