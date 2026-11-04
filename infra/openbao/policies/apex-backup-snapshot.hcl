# Política del respaldo del estado de OpenBao (S5-D75, B13): la ÚNICA ruta sys/ de todas las
# políticas, exacta y solo de lectura (snapshot de raft).
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
