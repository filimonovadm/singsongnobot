output "function_id" {
  value = yandex_function.bot.id
}

output "invoke_url" {
  value = "https://functions.yandexcloud.net/${yandex_function.bot.id}"
}
