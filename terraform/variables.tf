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
  type        = string
  default     = null
  description = "Path to service account key JSON. Used locally; in CI set via env TF_VAR_sa_key_file or YC_SERVICE_ACCOUNT_KEY_FILE."
}
