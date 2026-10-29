# Datos de demostración (`seed --demo`)

Para enseñar APEX sin datos reales: 3 planes y 30 socios **ficticios** (documentos `999` + 7 dígitos, teléfonos `300 000 00xx`, correos `demo+NN@ejemplo.invalid`) con ventas y pagos en los seis estados (al día, por vencer, vencida, congelada, pendiente de pago, anulada), una renovación pendiente y un pago anulado. Las fechas salen de "hoy" y de los días de aviso configurados.

## Regla de oro: nunca la base real

La demostración **solo** corre sobre una base aparte. Con `ENV=production` el comando se niega salvo que se cumplan las tres cosas:

1. `--as <correo de un administrador activo>`;
2. `--allow-production`;
3. el nombre de la base (`current_database()`) termina en **`_demo`**, **`_ensayo`** o **`_smoke`**.

Si no, sale con código 2 y no escribe nada. **Nunca** apunte `seed --demo` a la base del contenedor `apex-db-1`.

## Crear la base de demostración y sembrar

```bash
DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"
$DC exec -T db_test createdb -U apex apex_demo
$DC run --rm --entrypoint alembic \
  -e DATABASE_URL=postgresql+asyncpg://apex:apex-test@db_test:5432/apex_demo tools upgrade head
$DC run --rm -e DATABASE_URL=postgresql+asyncpg://apex:apex-test@db_test:5432/apex_demo \
  tools seed --demo
```

Salida: `seed de demo: planes=3 socios=30 membresias=31 pagos=NN` (solo conteos). Repetir el comando no cambia nada y dice `seed de demo ya aplicado`.

## Cosas que conviene saber

- **No es atómico, es reanudable.** Cada socio se da de alta y luego se le vende y paga en otra transacción (por el orden de candados). Si se corta a la mitad, se repite el comando y completa lo que falta sin duplicar.
- **Si la base ya tiene socios reales** el comando sale con 2. `--force-demo-on-non-empty` siembra al lado de ellos: úselo solo en una base de pruebas.
- La auditoría va al usuario técnico, o al administrador de `--as`. Al terminar, `verify-audit` debe decir "Cadena íntegra".
- No lee `.env.seed` ni necesita `ADMIN_*`; si quiere entrar a la demostración cree un administrador aparte.
- Para borrarla: elimine la base (`dropdb apex_demo`), no los socios uno a uno.
