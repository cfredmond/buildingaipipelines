locals {
  lambda_code_dir = "${path.module}/../lambda_src"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = local.lambda_code_dir
  output_path = "${path.module}/lambda_src.zip"
}

resource "aws_lambda_function" "search" {
  function_name    = "${var.project_name}-search"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "search_handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
      API_KEYS_SECRET_ARN = aws_secretsmanager_secret.api_keys.arn
    }
  }
}

resource "aws_lambda_function" "extract" {
  function_name    = "${var.project_name}-extract"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "extract_handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
      API_KEYS_SECRET_ARN = aws_secretsmanager_secret.api_keys.arn
    }
  }
}

resource "aws_lambda_function" "extract_worker" {
  function_name    = "${var.project_name}-extract-worker"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "extract_worker.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
      API_KEYS_SECRET_ARN = aws_secretsmanager_secret.api_keys.arn
    }
  }
}

resource "aws_lambda_function" "label_score" {
  function_name    = "${var.project_name}-label-score"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "label_score_handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 900
  memory_size      = 1024

  environment {
    variables = {
      ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
      API_KEYS_SECRET_ARN = aws_secretsmanager_secret.api_keys.arn
    }
  }
}

resource "aws_lambda_function" "report" {
  function_name    = "${var.project_name}-report"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "report_handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 120
  memory_size      = 512

  environment {
    variables = {
      ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
      API_KEYS_SECRET_ARN = aws_secretsmanager_secret.api_keys.arn
    }
  }
}

