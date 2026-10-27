path "support/data/vector-db" {
  capabilities = ["read"]
}
# Permit inspection of this token's own permissions for the smoke check.
path "sys/capabilities-self" {
  capabilities = ["update"]
}
