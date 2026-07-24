resource "random_id" "this" {
  byte_length = 4

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

resource "random_pet" "this" {
  length    = 3
  separator = "-"

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

# Signing key for the API's JWT access/refresh tokens. Generated once and kept
# in Terraform state so it stays stable across applies (rotating it would
# invalidate every issued token). backend/_shared/auth.py deliberately refuses
# to fall back to a predictable secret when IS_LOCAL is false, so this must be
# injected for any cloud deployment.
resource "random_password" "jwt" {
  length  = 48
  special = false

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}
