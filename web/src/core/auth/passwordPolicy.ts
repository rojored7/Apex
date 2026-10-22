// Revisión del Sprint 2 (M5 de la revisión general, parte front): la política de longitud de
// contraseña del api (N-10, S2-D30) en un solo lugar. Los esquemas de features/auth la toman
// de aquí y passwordPolicy.test.ts la compara con `minLength`/`maxLength` de
// ChangePasswordIn.new_password y ResetIn.new_password en docs/openapi.json.
export const PASSWORD_LIMITS = Object.freeze({ min: 12, max: 128 });
