resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project_name}-pipeline"
  role_arn = aws_iam_role.sfn_exec.arn

  definition = jsonencode({
    Comment = "Building AI Pipelines: search -> extract -> label_score -> report"
    StartAt = "Search"
    States = {
      Search = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.search.arn
          "Payload.$"  = "$"
        }
        OutputPath = "$.Payload"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Next = "ExtractMap"
      }
      ExtractMap = {
        Type           = "Map"
        ItemsPath      = "$.urls"
        MaxConcurrency = 10
        Parameters = {
          "run_id.$" = "$.run_id"
          timeout_s  = 10
          max_chars  = 8000
          user_agent = "Mozilla/5.0 (compatible; buildingaipipelines.com/1.0)"

          "url.$"          = "$$.Map.Item.Value.url"
          "title.$"        = "$$.Map.Item.Value.title"
          "source.$"       = "$$.Map.Item.Value.source"
          "published_at.$" = "$$.Map.Item.Value.published_at"
        }
        Iterator = {
          StartAt = "ExtractOne"
          States = {
            ExtractOne = {
              Type           = "Task"
              Resource       = "arn:aws:states:::lambda:invoke"
              TimeoutSeconds = 20
              Parameters = {
                FunctionName = aws_lambda_function.extract_worker.arn
                "Payload.$"  = "$"
              }
              OutputPath = "$.Payload"
              Retry = [
                {
                  ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
                  IntervalSeconds = 2
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }
              ]
              Catch = [
                {
                  ErrorEquals = ["States.ALL"]
                  ResultPath  = "$.error"
                  Next        = "MakeErrorRow"
                }
              ]
              End = true
            }

            MakeErrorRow = {
              Type = "Pass"
              Parameters = {
                "run_id.$"           = "$.run_id"
                "title.$"            = "$.title"
                "source.$"           = "$.source"
                "date.$"             = "$.published_at"
                "url.$"              = "$.url"
                "dedupe_key.$"       = "$.url"
                "extracted_text"     = ""
                "extraction_status"  = "error"
                "extraction_error.$" = "$.error.Error"
              }
              End = true
            }
          }
        }
        ResultPath = "$.extract_results"
        Next       = "WriteExtracted"
      }
      WriteExtracted = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.extract.arn
          Payload = {
            "run_id.$"          = "$.run_id"
            "urls_s3_key.$"     = "$.urls_s3_key"
            "extract_results.$" = "$.extract_results"
          }
        }
        OutputPath = "$.Payload"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Next = "LabelScore"
      }
      LabelScore = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.label_score.arn
          "Payload.$"  = "$"
        }
        OutputPath = "$.Payload"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Next = "Report"
      }
      Report = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.report.arn
          "Payload.$"  = "$"
        }
        OutputPath = "$.Payload"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        End = true
      }
    }
  })
}

