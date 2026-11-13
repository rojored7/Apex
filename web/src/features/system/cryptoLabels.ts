// S6-F2 · US-143 a US-145: las palabras de la pantalla de llaves (propósito, operación, trabajo, proveedor y
// estado del custodio). Un valor que el front no conoce se muestra tal cual, nunca se inventa.
import type { CryptoJobView, CryptoKeyView, CryptoVerb, JobKind, KeyProvider, KeyPurpose, ProviderState } from "./schemas";

export const PURPOSE_LABELS: Readonly<Record<KeyPurpose, string>> = { encrypt: "Cifrado", index: "Índice ciego", sign: "Firma" };

export const PROVIDER_LABELS: Readonly<Record<KeyProvider, string>> = { local: "Local", openbao: "OpenBao" };

export const VERB_LABELS: Readonly<Record<CryptoVerb, string>> = {
  encrypt: "Cifrar",
  decrypt: "Descifrar",
  index: "Indexar",
  sign: "Firmar",
  verify: "Verificar",
  wrap: "Envolver",
  unwrap: "Desenvolver",
  rotate: "Rotar",
  export: "Exportar",
};

export const JOB_KIND_LABELS: Readonly<Record<JobKind, string>> = {
  rotate: "Rotación",
  reencrypt: "Recifrado",
  migrate_provider: "Cambio de proveedor",
  rewrap: "Re-envoltura",
};

export const PROVIDER_STATE_LABELS: Readonly<Record<ProviderState, string>> = {
  ok: "conectado",
  sealed: "sellado",
  unreachable: "inalcanzable",
  unknown: "sin verificar",
};

const isProvider = (name: string): name is KeyProvider => Object.hasOwn(PROVIDER_LABELS, name);

/** «Local», «OpenBao» o «Local y OpenBao»; sin proveedores, «ninguno». */
export function providerNames(names: readonly string[]): string {
  const labels = names.map((name) => (isProvider(name) ? PROVIDER_LABELS[name] : name));
  const last = labels.at(-1);
  if (last === undefined) return "ninguno";
  return labels.length === 1 ? last : `${labels.slice(0, -1).join(", ")} y ${last}`;
}

/** «Rotar» solo en una llave activa de cifrado: ni índice ni firma (409 `purpose_not_rotatable`), ni una vieja. */
export function canRotate(key: Pick<CryptoKeyView, "state" | "purpose">): boolean {
  return key.state === "active" && key.purpose === "encrypt";
}

/** Texto de un trabajo para nombres accesibles: «rotación de member.phone». */
export function jobTitle(job: Pick<CryptoJobView, "kind" | "data_class">): string {
  const kind = JOB_KIND_LABELS[job.kind].toLowerCase();
  return job.data_class ? `${kind} de ${job.data_class}` : kind;
}
