// S3-D105: Zod 4 compila los objetos con `new Function` cuando puede y, para saberlo, prueba un
// `new Function("")` la primera vez que valida un objeto. Con la CSP de Nginx (sin
// 'unsafe-eval') esa prueba falla en silencio pero el navegador la reporta como violación
// (`securitypolicyviolation`, script-src eval). `jitless` apaga la compilación y la prueba: Zod
// valida con su intérprete, con los mismos resultados. Se importa antes que nada en main.tsx,
// en la entrada del catálogo y en src/test/setup.ts (las pruebas corren el mismo camino).
import { z } from "zod";

z.config({ jitless: true });
