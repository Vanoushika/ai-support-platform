# Local single-server demonstration. Host port is bound to loopback only.
ui = true
disable_mlock = true
api_addr = "http://openbao:8200"
storage "file" {
  path = "/bao/data"
}
listener "tcp" {
  address = "0.0.0.0:8200"
  tls_disable = true
}
