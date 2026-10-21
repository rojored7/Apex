# EP-20 · Acceso cifrado con TLS híbrido

- **Versión del plan:** v0.3 (punto 2 de la versión 0.3; supuesto de P7).
- **Bounded context:** ninguno de negocio; borde de la infraestructura (`caddy` delante de `nginx`). Es una épica de seguridad explícita.
- **Estimación relativa:** S.

## Objetivo de negocio

Que el sistema se pueda usar desde fuera del local (el celular del dueño, y más adelante el portal del socio) sin que las contraseñas, los tokens ni los datos viajen en claro, y que ese cifrado resista a un atacante que guarde hoy el tráfico para descifrarlo mañana con computación cuántica.

## Actores

- Administrador u operador: configura el dominio y el `.env`.
- Todos los usuarios, como beneficiarios.

## Capacidades incluidas

- Servicio `caddy` en Compose delante de Nginx, con TLS automático para el dominio del gimnasio.
- Grupo de intercambio de llaves `X25519MLKEM768` (híbrido clásico más post-cuántico).
- Redirección de HTTP a HTTPS y cabecera `Strict-Transport-Security`.
- `CORS_ORIGINS` y CSP actualizadas al dominio HTTPS.
- Caddy opcional: en LAN sin dominio el sistema sigue funcionando por HTTP en el puerto 80 (decisión de P7).

## Fuera de alcance

- Certificados de cliente o VPN.
- Exposición pública del panel de administración con restricción por IP (no está en el plan).

## Criterios de éxito medibles

- Con dominio configurado, una conexión con un cliente moderno negocia `X25519MLKEM768`.
- Una petición HTTP recibe redirección a HTTPS.
- SSL Labs o equivalente da calificación A o superior.
- La renovación automática del certificado funciona sin intervención (prueba con certificados de staging).

## Dependencias

- EP-03 Seguridad de la plataforma (cabeceras, CORS, CSP).
- EP-00 Cimientos (Compose y Nginx).

## Riesgos

- P7 abierta: si hay dominio desde el inicio, esta épica se adelanta a v0.1 y el portal del socio podría adelantarse.
- Clientes viejos sin soporte del grupo híbrido deben poder caer a X25519 sin romper el acceso.
- Licencia de Caddy (Apache 2.0, permitida) y de sus módulos: verificar que no se agregue un módulo con licencia prohibida.

## Pantallas del diseño que habilita

- Ninguna propia. Es condición para usar `Portal_*` desde fuera del gimnasio (EP-25).
