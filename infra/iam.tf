data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project_name}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_s3_artifacts" {
  statement {
    sid = "ListArtifactsBucketRunsPrefix"
    actions = [
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.artifacts.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["runs/*"]
    }
  }

  statement {
    sid = "ReadWriteArtifactsObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = ["${aws_s3_bucket.artifacts.arn}/runs/*"]
  }
}

resource "aws_iam_role_policy" "lambda_s3_artifacts" {
  name   = "${var.project_name}-lambda-s3-artifacts"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_s3_artifacts.json
}

data "aws_iam_policy_document" "lambda_read_api_keys_secret" {
  statement {
    sid     = "ReadApiKeysSecret"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.api_keys.arn
    ]
  }
}

resource "aws_iam_role_policy" "lambda_read_api_keys_secret" {
  name   = "${var.project_name}-lambda-read-api-keys-secret"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_read_api_keys_secret.json
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn_exec" {
  name               = "${var.project_name}-sfn-exec"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn_invoke_lambdas" {
  statement {
    sid     = "InvokePipelineLambdas"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.search.arn,
      aws_lambda_function.extract.arn,
      aws_lambda_function.extract_worker.arn,
      aws_lambda_function.label_score.arn,
      aws_lambda_function.report.arn
    ]
  }
}

resource "aws_iam_role_policy" "sfn_invoke_lambdas" {
  name   = "${var.project_name}-sfn-invoke-lambdas"
  role   = aws_iam_role.sfn_exec.id
  policy = data.aws_iam_policy_document.sfn_invoke_lambdas.json
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_invoke" {
  name               = "${var.project_name}-scheduler-invoke"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_start_state_machine" {
  statement {
    sid     = "StartPipelineStateMachine"
    actions = ["states:StartExecution"]
    resources = [
      aws_sfn_state_machine.pipeline.arn
    ]
  }
}

resource "aws_iam_role_policy" "scheduler_start_state_machine" {
  name   = "${var.project_name}-scheduler-start-pipeline"
  role   = aws_iam_role.scheduler_invoke.id
  policy = data.aws_iam_policy_document.scheduler_start_state_machine.json
}

