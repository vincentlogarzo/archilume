variable "ARCHILUME_VERSION" { default = "latest" }
variable "REFLEX_API_URL"    { default = "http://localhost:3000" }

group "default" {
  targets = ["archilume-frontend", "archilume-backend", "archilume-engine"]
}

target "archilume-frontend" {
  context    = "."
  dockerfile = ".docker/Dockerfile"
  target     = "archilume-frontend"
  tags       = ["vlogarzo/archilume-frontend:${ARCHILUME_VERSION}"]
  args       = { REFLEX_API_URL = REFLEX_API_URL }
}

target "archilume-backend" {
  context    = "."
  dockerfile = ".docker/Dockerfile"
  target     = "archilume-backend"
  tags       = ["vlogarzo/archilume-backend:${ARCHILUME_VERSION}"]
}

target "archilume-engine" {
  context    = "."
  dockerfile = ".docker/Dockerfile"
  target     = "archilume-engine"
  tags       = ["vlogarzo/archilume-engine:${ARCHILUME_VERSION}"]
}
