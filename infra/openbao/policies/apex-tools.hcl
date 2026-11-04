# Política de tools (CLI del operador, S5-D11): lo del api más recifrar (rewrap), rotar la llave y
# fijar la versión mínima de descifrado. Sin delete, sin trim, sin sys/.
path "transit/encrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/decrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/rewrap/apex-kek" {
  capabilities = ["update"]
}

path "transit/keys/apex-kek/rotate" {
  capabilities = ["update"]
}

path "transit/keys/apex-kek/config" {
  capabilities = ["update"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
