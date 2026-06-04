terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = "~> 0.140"
    }
  }

  backend "s3" {
    endpoint = "https://storage.yandexcloud.net"
    bucket   = "singsongnobot-tfstate"
    key      = "terraform.tfstate"
    region   = "ru-central1"

    skip_region_validation      = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}

provider "yandex" {
  service_account_key_file = var.sa_key_file
  folder_id                = var.folder_id
}

data "archive_file" "function_zip" {
  type        = "zip"
  output_path = "${path.module}/../function.zip"
  source_dir  = "${path.module}/.."
  excludes = [
    ".git",
    ".github",
    ".gitignore",
    ".agent",
    ".claude",
    ".opencode",
    ".playwright-mcp",
    ".DS_Store",
    "terraform",
    "function.zip",
    "avatar.png",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "requirements.txt",
  ]
}

# Service account (singsongnobot-deploy, id: ajearql5kugafb67p02n) is
# managed outside Terraform. It already has serverless.functions.admin role.

# Storage bucket (singsongnobot-tracks) and SA (singsongnobot-storage, id: ajev12nglllf4g6gdlm0)
# are managed outside Terraform. Static keys are passed via GitHub Secrets.

resource "yandex_function" "bot" {
  name               = "singsongnobot"
  folder_id          = var.folder_id
  runtime            = "python312"
  entrypoint         = "index.handler"
  memory             = 512
  execution_timeout  = "25"
  user_hash          = data.archive_file.function_zip.output_md5

  content {
    zip_filename = data.archive_file.function_zip.output_path
  }

  environment = {
    TG_TOKEN      = var.tg_token
    YM_TOKEN      = var.ym_token
    S3_BUCKET     = "singsongnobot-tracks"
    S3_ACCESS_KEY = var.s3_access_key
    S3_SECRET_KEY = var.s3_secret_key
  }
}

resource "yandex_function_iam_binding" "public_invoke" {
  function_id = yandex_function.bot.id
  role        = "serverless.functions.invoker"

  members = ["system:allUsers"]
}
