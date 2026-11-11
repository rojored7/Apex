# Política del api (S5-D11, M-2): cifrar y descifrar con apex-kek y renovar su propio token.
# v0.3 (S6-D6, D41): además VERIFICA firmas con apex-sign-audit; el api no firma.
# Nada más: ni leer la llave, ni rotarla, ni rutas sys/.
path "transit/encrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/decrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/verify/apex-sign-audit" {
  capabilities = ["update"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
