# LabPulse

A serverless lab equipment fault-reporting system built on AWS. A student scans a QR link on a machine, sees whether that machine already has an open report, and reports a fault only if needed. Duplicate reports on the same machine are merged and counted, so repeated failures stand out to staff.

Built for the ShadowFox Cloud Engineer (AWS) internship. Status: **Beginner and Intermediate working and tested.** Advanced is not claimed as complete (see the last section).

## Architecture

```
Browser -> S3 static website -> API Gateway (HTTP API) -> Lambda -> DynamoDB
                                                           |
                                                           -> CloudWatch Logs
```

| Component | Role |
|---|---|
| Amazon S3 | Hosts `index.html` (report form) and `staff.html` (staff dashboard) using static website hosting |
| API Gateway HTTP API | Public HTTPS endpoints, CORS limited to the S3 website origin |
| AWS Lambda (Python) | One function that routes four endpoints, validates input and applies the business rules |
| Amazon DynamoDB | Stores reports. Partition key `equipment_id`, sort key `report_id` |
| CloudWatch Logs | Records each saved report and each status change |

Region: Asia Pacific (Mumbai).

**Why DynamoDB and not RDS:** it needs no VPC or server, it suits low traffic, and one query by `equipment_id` returns every report for a machine, which is exactly what the duplicate check needs. The trade-off: listing all reports for staff uses a Scan, which is acceptable for a small lab but would not scale to very large volumes.

## API routes

| Route | Access | What it does |
|---|---|---|
| `POST /reports` | Public | Validates, then creates a report or merges into the machine's open report |
| `GET /status/{equipment_id}` | Public | Returns whether the machine has an open report, its status and report count. Returns no description or email |
| `GET /reports` | Staff key | Lists all reports |
| `PATCH /reports/{equipment_id}/{report_id}` | Staff key | Changes status to OPEN, IN_PROGRESS or RESOLVED |

Staff routes require an `x-staff-key` header. The key is stored in a Lambda environment variable and compared in constant time. It is never in the code or this repository. Without the key the API returns 403.

## Data flow

1. The user opens the site, optionally through a QR link such as `/?eq=PC-14`, which fills the equipment ID.
2. The page calls `GET /status/PC-14` and shows whether an open report already exists.
3. The browser validates the fields, then sends `POST /reports`.
4. Lambda validates again on the server, because browser checks can be bypassed.
5. If the machine has an OPEN or IN_PROGRESS report, Lambda increments its `report_count` with a conditional update. Otherwise it creates a new OPEN report.
6. Staff open `staff.html`, enter the key, and see counts, filters and a status control for each report. Machines reported three or more times are marked in red.

## Validation

| Field | Rule |
|---|---|
| Equipment ID | 2-20 letters, numbers or hyphens |
| Lab | 2-50 characters |
| Description | 10-500 characters |
| Email | Optional, must look like an email if given |

The reporter's email is stored but never returned by any public route.

## Security decisions

- The S3 bucket policy allows only `s3:GetObject`, so the public can read the site files but cannot list or write to the bucket.
- API CORS allows one origin (the S3 website endpoint), the methods `GET`, `POST`, `PATCH` and `OPTIONS`, and the headers `content-type` and `x-staff-key`. Credentials are off.
- The Lambda execution role has an inline policy limited to `PutItem`, `Query`, `UpdateItem` and `Scan` on the one table.
- The staff dashboard keeps the key in `sessionStorage` only for the browser session. It is typed at runtime.
- No credentials or account identifiers are committed to this repository.

## Cost decisions

- The account is on the AWS Free plan with credits, and a zero-spend budget alert is set.
- The DynamoDB table uses provisioned capacity of 1 read and 1 write unit with auto scaling off. The console estimated about $0.67 per month, which the credits cover. This estimate was read from the console, not independently verified against billing.
- Lambda, API Gateway and S3 usage is a handful of requests during testing.

## Testing evidence

- Lambda console tests: valid input returns 200, invalid input returns 400.
- DynamoDB: two submissions for the same machine produced one item with `report_count` 2.
- `tests/labpulse-api-tests.ps1` runs against the live API. It asks for the staff key at runtime. Results from a run: public status 200, `GET /reports` without the key 403, with the key 200, `PATCH` without the key 403, with the key 200, and the public status updated after the change.
- Browser tests: report submitted with an ID, validation errors for empty and bad input, QR link filling the equipment ID, status banner, dashboard filters and status changes.
- CloudWatch shows a log line for each saved report.

Screenshots are in `docs/screenshots/`.

## Repository layout

```
frontend/index.html           report form
frontend/staff.html           staff dashboard
backend/lambda_function.py    Lambda handler (all four routes)
tests/labpulse-api-tests.ps1  live API tests (prompts for the staff key)
docs/screenshots/             test evidence
```

## Known limitations

- S3 website hosting serves over HTTP only. The API calls themselves use HTTPS and no passwords are entered on the site.
- The staff key is a shared secret, not per-user login. Amazon Cognito would be the upgrade.
- The key sits in a Lambda environment variable, which is encrypted at rest but visible to anyone with console access to the function. Secrets Manager or Parameter Store would be the upgrade.
- API rate limiting was not verified, so it is not claimed here.
- Listing reports uses a DynamoDB Scan.
- The site must be opened from the S3 website endpoint, not the S3 object URL, because CORS allows one origin.

## Cleanup plan

Delete in this order when the project ends: the S3 bucket (empty it first), the API Gateway API, the Lambda function and its CloudWatch log group, the DynamoDB table, then the Lambda role's inline policy. The Free plan account also closes automatically after the free period unless upgraded.

## Advanced level: honest status

Not completed. Parts that exist: CloudWatch logging, a least-privilege Lambda role, cost controls (Free plan, budget alert, small provisioned capacity), a cleanup plan, and a staff-only access check. Parts not built: RDS, a VPC, CloudFront with HTTPS, per-user authentication, alarms and a repeatable deployment template. RDS and a VPC were not used because DynamoDB fits the access pattern at lower cost and risk.
## Project materials

- Demo video (Google Drive): https://drive.google.com/file/d/16JsN8H8F9pFafWj9BZoeFIUyx9JfJA_M/view?usp=drive_link
- Demo video file: [docs/video/labpulse-demo.mp4](docs/video/labpulse-demo.mp4)
- Presentation: [docs/presentation/LabPulse-Presentation-Deck.pptx](docs/presentation/LabPulse-Presentation-Deck.pptx)
- Internship report: [docs/report/LabPulse-Internship-Report.pdf](docs/report/LabPulse-Internship-Report.pdf)

