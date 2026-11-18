# Perfil del atleta: operación del día a día

Guía para quien opera el box. Cubre solo lo que cambia el procedimiento; el contrato de las rutas
está en `docs/openapi.json`.

Los comandos se corren desde la raíz del repositorio, con este alias (en desarrollo súmale
`-f infra/compose.dev.yml`):

```
DC="docker compose --env-file .env --env-file .env.ops -f infra/compose.yml"
```

## Qué se guarda

- Medidas del cuerpo (peso, estatura, grasa, notas): siempre cifradas. Solo se guardan si el socio
  firmó la autorización de datos; si no, el sistema responde `consent_required`. Para verlas hay
  que pulsar «Mostrar», y eso queda en la auditoría. Un campo vacío también deja la fila de
  auditoría (no descifra nada); la pantalla no ofrece «Mostrar» en un campo vacío.
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
$DC --profile tools run --rm tools derive-records --dry-run --as <correo de un admin>
$DC --profile tools run --rm tools derive-records --as <correo de un admin>
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

## Anular una medición e invalidar un récord

- Una medición mal cargada se anula; un récord manual mal cargado se invalida. Ninguno se borra:
  queda el rastro con quién y cuándo. «Editar» un récord es en realidad invalidar el anterior y
  registrar uno nuevo.
- El admin puede anular o invalidar cualquiera.
- El coach solo lo que registró él mismo y dentro de las 24 horas siguientes (la hora 24 exacta
  aún cuenta). Si no, recibe 403 `forbidden`. Si se pasó el plazo, que lo haga un admin.
- Sobre un socio dado de baja no se puede anular ni invalidar (responde 404 `member_not_found`).
  Si hay que corregirlo, se reactiva al socio, se corrige y se vuelve a dar de baja.

## «Mostrar» una medida: cupo y auditoría

- «Mostrar» comparte el cupo con la ficha del socio: 30 por minuto, 200 por hora y 600 por día
  por usuario (429 `rate_limited` con `Retry-After`). Lo que se revela en la ficha cuenta aquí y
  al revés.
- Al pasar de la mitad del cupo horario (más de 100 reveladas en una hora), el log lleva
  `reveal volume` y llega una alerta interna `reveal_volume`, una vez por usuario y hora, sin
  nombres (ver `docs/RUNBOOK.md` §15).
- Quién reveló qué medidas: un admin entra a la pantalla Auditoría (`/sistema/auditoria`) y
  filtra por acción `reveal` y tabla `athletes.body_metrics`. Por la API es
  `GET /api/v1/audit?action=reveal&table=athletes.body_metrics` (admite también `user_id`,
  `subject_member_id`, `from` y `to`). Cada fila dice quién, cuándo, de qué socio, qué campo y
  desde qué IP; nunca el valor.

## Socio dado de baja y supresión

Al dar de baja a un socio se conservan sus medidas (cifradas), sus récords y sus resultados. La
baja es un borrado lógico y los datos de rendimiento siguen en el historial del box.

- Las listas y el resumen siguen visibles para admin y coach, en solo lectura. Las medidas se
  ven como `•••` (la lista solo dice si tienen valor).
- «Mostrar» una medida de un socio dado de baja: solo un admin. El coach recibe 403 `forbidden`
  y no se descifra nada.
- Escribir (medir, registrar, anular, invalidar) sobre un socio dado de baja responde 404
  `member_not_found`. `derive-records` tampoco lo toca.

En v0.6 NO hay supresión: ninguna medida ni récord se borra, ni por pantalla ni por comando.
Ante una solicitud de supresión (Ley 1581):

1. Guarda la evidencia de la solicitud (quién, cuándo, qué socio).
2. Pásala al titular del tratamiento: borrar o conservar es decisión suya, no del operador.
3. Mientras tanto, el socio debe estar dado de baja: así solo un admin puede revelar sus medidas.
4. No borres filas a mano en la base: la auditoría y los respaldos las referencian. No existe
   un comando de supresión de medidas; lo define el titular (modelo del procedimiento manual:
   `adjuntos.md`, «Supresión a petición»).
5. Los respaldos conservan los datos hasta que cada copia rote.

## Rotar la llave de las medidas

La clase `athlete.metric` (peso, estatura, grasa y notas) se rota como cualquier otra. La llave
la crea el api al arrancar; no hay paso `init-keys` para ella.

```
$DC --profile tools run --rm tools rotate-key athlete.metric --reason "rotación anual 2026" --as <correo de un admin>
```

Es reanudable y el sistema sigue atendiendo. Al terminar, la llave anterior queda en
`decrypt_only`; retirarla es con `retire-key` (guía completa en `rotar-llave.md`). Los récords
no se cifran y no entran en la rotación.

## Si llega la alerta `athletes_derive_skipped`

Dice que un récord no se pudo derivar o reponer (lleva solo el tipo de error). Una sola alerta
puede cubrir varias: el sistema no repite la misma alerta del mismo código y job dentro de 60
segundos. Ante una, no cuentes cuántas hubo: corre `derive-records` completo (arriba) y revisa
que termine con código 0.
