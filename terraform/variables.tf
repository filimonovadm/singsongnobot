variable "folder_id" {
  type = string
}

variable "tg_token" {
  type      = string
  sensitive = true
}

variable "ym_token" {
  type      = string
  sensitive = true
}

variable "sa_key_file" {
  type    = string
  default = null
}

variable "s3_access_key" {
  type      = string
  sensitive = true
}

variable "s3_secret_key" {
  type      = string
  sensitive = true
}
