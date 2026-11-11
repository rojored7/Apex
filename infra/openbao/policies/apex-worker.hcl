# Política del worker (S5-D11): descifrar y renovar su token. No cifra.
# v0.3 (S6-D6, D41): firma y verifica con apex-sign-audit (solo el worker firma la auditoría).
# Sin rotate, config, delete, trim ni export (M-2c).
path "transit/decrypt/apex-kek" {
  capabilities = ["update"]
}

path "transit/sign/apex-sign-audit" {
  capabilities = ["update"]
}

path "transit/verify/apex-sign-audit" {
  capabilities = ["update"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}
