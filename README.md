# LabPulse

A serverless fault-reporting system for lab equipment. A student scans a QR code on a machine, the report form opens with the equipment ID already filled in, and the report is validated and processed by AWS.

Built for the ShadowFox Cloud Engineer (AWS) internship. Status: **Beginner level working and tested. Intermediate in progress.**

## Architecture (Beginner)
```
Browser -> S3 static website -> API Gateway (HTTP API) -> Lambda -> CloudWatch Logs
```


| Component | Role |
|---|---|
| Amazon S3 | Hosts the static form (`frontend/index.html`) using static website hosting |
| API Gateway HTTP API | Public HTTPS endpoint `POST /reports`, CORS limited to the S3 website origin |
| AWS Lambda (Python) | Validates the input, generates a report ID, logs the event, returns JSON |
| CloudWatch Logs | Records each received report |

Region: Asia Pacific (Mumbai).

## Data flow

1. The user opens the site, optionally through a QR link such as `/?eq=PC-14`, which pre-fills the equipment ID.
2. The browser validates the fields and shows errors without calling the server if they fail.
3. If valid, the browser sends a JSON `POST` to API Gateway.
4. API Gateway invokes Lambda. Lambda validates again on the server, because browser checks can be bypassed.
5. Lambda returns `200` with a report ID, or `400` with field-level errors. The page shows a success or failure message.

## Validation

| Field | Rule |
|---|---|
| Equipment ID | 2-20 letters, numbers or hyphens |
| Lab | 2-50 characters |
| Description | 10-500 characters |
| Email | Optional, must look like an email if given |

## Security and cost decisions

- The S3 bucket policy allows only `s3:GetObject`, so the public can read the site files but cannot list or write to the bucket.
- API CORS allows one origin, the S3 website endpoint, and only the `POST` and `OPTIONS` methods and the `content-type` header.
- No credentials or secrets exist in the code or the repository.
- The account runs on the AWS Free plan with a zero-spend budget alert. API Gateway and Lambda appear on AWS's list of services included in the Free plan. S3 and CloudWatch worked on the account without errors.
- Known limitation: S3 website hosting serves over HTTP only. The form carries no passwords and the API call itself uses HTTPS.
- Known limitation: the API has no throttling yet. Throttling is planned for the Intermediate version.
- Beginner version does not store reports. The success message says so.

## Testing evidence

- Lambda console tests: valid input returned 200, invalid input returned 400.
- Direct HTTP tests with PowerShell returned 200 and 400 as expected.
- Browser tests: success path with a report ID, validation errors for bad and empty input, and QR pre-fill.
- CloudWatch shows a `report_received` log line for a browser submission.

Screenshots are in `docs/screenshots/`.

## Repository layout

```
frontend/index.html           the form page
backend/lambda_function.py    the Lambda handler
docs/screenshots/             test evidence
```

## Roadmap

- Intermediate: DynamoDB storage, a retrieval endpoint, duplicate-report merging, status tracking, API throttling.
- Advanced: monitoring, access control, repeatable deployment, cost review.