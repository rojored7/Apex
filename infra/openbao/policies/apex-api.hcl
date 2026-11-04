# Política del api (S5-D11, M-2): cifrar y descifrar con apex-kek y renovar su propio token.
# Nada más: ni leer la llave, ni rotarla, ni rutas sys/.
path "transit/encrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/decrypt/apex-kek" {
  capabilities = ["update"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
