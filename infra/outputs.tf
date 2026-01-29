output "lambda_exec_role_arn" {
  value       = aws_iam_role.lambda_exec.arn
  description = "ARN of the Lambda execution role (pipeline functions)"
}

output "sfn_exec_role_arn" {
  value       = aws_iam_role.sfn_exec.arn
  description = "ARN of the Step Functions execution role"
}

output "scheduler_invoke_role_arn" {
  value       = aws_iam_role.scheduler_invoke.arn
  description = "ARN of the EventBridge Scheduler invoke role"
}

output "api_keys_secret_arn" {
  value       = aws_secretsmanager_secret.api_keys.arn
  description = "ARN of the Secrets Manager secret holding API keys/config"
}

output "artifacts_bucket_name" {
  value       = aws_s3_bucket.artifacts.bucket
  description = "Name of the S3 bucket used for run artifacts (runs/<run_id>/...)"
}

output "artifacts_bucket_arn" {
  value       = aws_s3_bucket.artifacts.arn
  description = "ARN of the S3 bucket used for run artifacts"
}

output "state_machine_arn" {
  value       = aws_sfn_state_machine.pipeline.arn
  description = "ARN of the Step Functions state machine orchestrating the pipeline"
}

output "schedule_arn" {
  value       = aws_scheduler_schedule.pipeline_weekday_8am_et.arn
  description = "ARN of the EventBridge Scheduler schedule"
}

