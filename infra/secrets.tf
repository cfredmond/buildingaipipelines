resource "aws_secretsmanager_secret" "api_keys" {
  name = "${var.project_name}-api-keys"
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  secret_id = aws_secretsmanager_secret.api_keys.id

  secret_string = jsonencode({
    GOOGLE_CSE_API_KEY = var.google_cse_api_key
    GOOGLE_CSE_CX      = var.google_cse_cx
    OPENAI_API_KEY     = var.openai_api_key
    OPENAI_MODEL       = var.openai_model
  })
}

