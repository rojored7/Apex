# Política del worker (S5-D11): solo descifrar y renovar su token. No cifra.
path "transit/decrypt/apex-kek" {
  capabilities = ["update"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
