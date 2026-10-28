// S2-F5 (blueprint, decisión 22, alternativa "adaptador propio"): Zod como resolver de React
// Hook Form sin @hookform/resolvers. Desde la 5.8 ese paquete declara ajv y otra veintena de
// validadores como peer y npm 7+ instala ajv en el runtime del front; este adaptador cubre lo
// que usan los formularios del panel.
// - Valores válidos: devuelve lo que entrega el esquema (con sus `trim`), sin errores.
// - Inválidos: un error por ruta (el primero que reporta Zod), anidado como lo espera RHF; un
//   error sin ruta (un `refine` del objeto entero) queda en `root`.
// - S3-D105: desde Zod 4 el `type` de cada error es el código de Zod 4 (`invalid_format` donde Zod 3
//   decía `invalid_string`, `invalid_value` donde decía `invalid_enum_value`); ninguna pantalla lo lee
//   (solo el `type: "server"` que pone el 422 del api).
import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";
import type { core, ZodType } from "zod";

interface ErrorLeaf {
  type: string;
  message: string;
}

type ErrorTree = { [key: string]: ErrorTree | ErrorLeaf };

function insert(tree: ErrorTree, path: readonly string[], leaf: ErrorLeaf): ErrorTree {
  const [head, ...rest] = path;
  if (head === undefined) return tree;
  const current = tree[head];
  if (rest.length === 0) return current === undefined ? { ...tree, [head]: leaf } : tree;
  const child = current !== undefined && !("message" in current && typeof current.message === "string") ? (current as ErrorTree) : {};
  return { ...tree, [head]: insert(child, rest, leaf) };
}

function toFieldErrors(issues: readonly core.$ZodIssue[]): ErrorTree {
  return issues.reduce<ErrorTree>((tree, issue) => {
    const path = issue.path.length > 0 ? issue.path.map(String) : ["root"];
    return insert(tree, path, { type: issue.code, message: issue.message });
  }, {});
}

export function zodResolver<T extends FieldValues>(schema: ZodType<T, T>): Resolver<T> {
  return async (values) => {
    const result = await schema.safeParseAsync(values);
    if (result.success) return { values: result.data, errors: {} };
    return { values: {}, errors: toFieldErrors(result.error.issues) as FieldErrors<T> };
  };
}
