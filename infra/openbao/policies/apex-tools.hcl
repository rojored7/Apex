# Política de tools (CLI del operador, S5-D11): lo del api más rotar la llave, leerla (`key_info`,
# S5-D185) y fijar la versión mínima de descifrado. `rewrap` no está (S5-D55a: la re-envoltura es
# unwrap + wrap; S5-D191). La ruta `config` solo admite `min_decryption_version`. Sin delete, sin
# trim, sin sys/.
path "transit/encrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/decrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/keys/apex-kek" {
  capabilities = ["read"]
}

path "transit/keys/apex-kek/rotate" {
  capabilities = ["update"]
}

path "transit/keys/apex-kek/config" {
  capabilities = ["update"]
  allowed_parameters = {
    "min_decryption_version" = []
  }
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
