resource "aws_scheduler_schedule" "pipeline_weekday_8am_et" {
  name = "${var.project_name}-weekday-8am-et"

  schedule_expression          = "cron(0 8 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.scheduler_invoke.arn

    input = jsonencode({
      run_id   = "<<aws.scheduler.scheduled-time>>"
      query    = "UFO sightings (UAP reports)"
      max_urls = 50
    })
  }
}

