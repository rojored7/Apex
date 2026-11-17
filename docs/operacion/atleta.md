# Perfil del atleta: operación del día a día

Guía para quien opera el box. Cubre solo lo que cambia el procedimiento; el contrato de las rutas
está en `docs/openapi.json`.

## Qué se guarda

- Medidas del cuerpo (peso, estatura, grasa, notas): siempre cifradas. Solo se guardan si el socio
  firmó la autorización de datos; si no, el sistema responde `consent_required`. Para verlas hay
  que pulsar «Mostrar», y eso queda en la auditoría.
- Récords personales: el RM de cada movimiento y el mejor tiempo o marca de cada benchmark. Salen
  solos de los resultados que el coach valida, o los carga a mano un coach o un admin. No son
  datos de salud y no van cifrados.

## Qué pasa cuando se corrige o se anula un resultado

El récord que nació de ese resultado queda invalidado (con motivo y quién) y el sistema repone el
mejor resultado que quedaba sin récord. Si por cualquier fallo no se pudo reponer o derivar, el
resultado igual se guarda y llega una alerta interna sin datos personales (el log dice qué socio);
el comando de abajo lo repara.

## `derive-records`: derivar o reparar los récords

Sirve para dos cosas: derivar los récords de los resultados anteriores a v0.6 (paso de
despliegue, ver `actualizar.md`) y reparar cualquier récord que faltó. Es seguro repetirlo.

```
docker compose --profile tools run --rm tools derive-records --dry-run --as <correo de un admin>
docker compose --profile tools run --rm tools derive-records --as <correo de un admin>
```

- `--dry-run` hace todo el trabajo y lo deshace: informa sin escribir nada.
- `--as` es obligatorio en producción y debe ser un admin activo; sin él, en desarrollo, la acción
  se atribuye al usuario técnico.
- Trabaja de a un socio por transacción. Puede crear récords históricos (por ejemplo 100, 110 y
  120 kg si el socio los marcó en ese orden); el vigente siempre es el mejor real.
- Recorre todas las marcas de cada socio, sin topes: el récord vigente queda siempre en el mejor
  real. No toca a los socios dados de baja.
- Resumen: `socios`, `creados`, `ocupados` (la base estaba ocupada con ese socio: se reintentó 3
  veces) y `fallidos` (algo falló; ese socio quedó intacto).
- Código de salida `0`: todo en orden. `1`: hubo `ocupados` o `fallidos`; el resto se procesó.
  Repite el comando cuando el box esté tranquilo; si persiste, mira el log (lleva solo el nombre
  del tipo de error, nunca datos del socio). Desde `tools` los avisos quedan en el log y en el
  resumen: el comando no manda alertas a Telegram. Si falla la conexión, imprime los conteos
  parciales y termina con error.
- Queda auditado: una fila por récord creado y una fila resumen con solo los conteos.
