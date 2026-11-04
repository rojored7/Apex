# Configuración de OpenBao para APEX (S5-D10, D12, D104; W0-2). Se monta de a un archivo, en solo
# lectura, en /openbao/config/config.hcl: con read_only y tmpfs /tmp, `bao server` solo arranca con
# la configuración en un archivo (BAO_LOCAL_CONFIG escribiría local.json y falla; S5-D104).

# Sin interfaz web: el único cliente son la CLI y la API desde la red interna.
ui = false

# El contenedor corre sin capacidades (cap_drop ALL): no puede llamar a mlock. OpenBao 2.7 registra
# este campo como "unknown or unsupported" (aviso inofensivo: ya no usa mlock); se deja explícito. Los volcados de
# memoria quedan desactivados por el entrypoint de la imagen (ulimit -c 0) y el contenedor no
# tiene swap propio.
disable_mlock = true

storage "raft" {
  # Volumen nombrado openbao-data; la carpeta pertenece al usuario openbao (uid 100, gid 1000).
  path    = "/openbao/file"
  node_id = "apex-1"
}

listener "tcp" {
  address = "0.0.0.0:8200"
  # tls_disable: el servicio solo vive en la red `custody` (internal: true, sin puertos al anfitrión)
  # y solo lo alcanzan api, worker y tools. El TLS interno llega con Caddy en EP-20 (S5-D10).
  tls_disable = true
}

# Segundo listener, SOLO para la operación de custodia (S5-D107): OpenBao 2.7 cierra por defecto los
# endpoints sin token de sys/generate-root y sys/rekey. --reissue-tokens y `rekey` los necesitan porque
# la raíz inicial se revoca al instalar (S5-D76). Aquí quedan abiertos en 127.0.0.1:8210, que solo
# alcanzan el propio contenedor openbao y openbao-bootstrap (network_mode: service:openbao); api, worker
# y tools, en la red custody, solo ven el 8200 con esos endpoints cerrados. Ambos exigen el quórum de 3
# llaves de desello: sin ellas no completan nada.
listener "tcp" {
  address     = "127.0.0.1:8210"
  tls_disable = true
  disable_unauthed_generate_root_endpoints = false
  disable_unauthed_rekey_endpoints         = false
}

api_addr     = "http://openbao:8200"
cluster_addr = "http://127.0.0.1:8201"

