import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

TABLE_NAME = "labpulse-reports"
OPEN_STATUSES = ["OPEN", "IN_PROGRESS"]
ALL_STATUSES = ["OPEN", "IN_PROGRESS", "RESOLVED"]
STAFF_KEY = os.environ.get("STAFF_KEY", "")

EQUIPMENT_RE = re.compile(r"^[A-Za-z0-9-]{2,20}$")
REPORT_ID_RE = re.compile(r"^LP-[A-Z0-9]{8}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

table = boto3.resource("dynamodb").Table(TABLE_NAME)


def to_json(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    raise TypeError("Not serializable")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=to_json),
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_staff(event):
    supplied = (event.get("headers") or {}).get("x-staff-key", "")
    return bool(STAFF_KEY) and hmac.compare_digest(supplied.encode(), STAFF_KEY.encode())


def parse_body(event):
    try:
        data = json.loads(event.get("body") or "{}")
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def validate(data):
    errors = {}
    equipment_id = str(data.get("equipment_id", "")).strip()
    lab = str(data.get("lab", "")).strip()
    description = str(data.get("description", "")).strip()
    email = str(data.get("reporter_email", "")).strip()

    if not EQUIPMENT_RE.match(equipment_id):
        errors["equipment_id"] = "Use 2-20 letters, numbers or hyphens."
    if not 2 <= len(lab) <= 50:
        errors["lab"] = "Lab name must be 2-50 characters."
    if not 10 <= len(description) <= 500:
        errors["description"] = "Describe the problem in 10-500 characters."
    if email and not EMAIL_RE.match(email):
        errors["reporter_email"] = "Enter a valid email or leave it blank."

    clean = {
        "equipment_id": equipment_id.upper(),
        "lab": lab,
        "description": description,
        "reporter_email": email,
    }
    return clean, errors


def find_open_report(equipment_id):
    kwargs = {
        "KeyConditionExpression": Key("equipment_id").eq(equipment_id),
        "FilterExpression": Attr("status").is_in(OPEN_STATUSES),
    }
    while True:
        result = table.query(**kwargs)
        items = result.get("Items", [])
        if items:
            return items[0]
        if "LastEvaluatedKey" not in result:
            return None
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def merge_into(existing):
    return table.update_item(
        Key={"equipment_id": existing["equipment_id"], "report_id": existing["report_id"]},
        UpdateExpression="SET updated_at = :now ADD report_count :one",
        ConditionExpression="#s IN (:o, :p)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":now": now_iso(), ":one": 1, ":o": "OPEN", ":p": "IN_PROGRESS"},
        ReturnValues="ALL_NEW",
    )["Attributes"]


def create_report(clean):
    stamp = now_iso()
    item = {
        "equipment_id": clean["equipment_id"],
        "report_id": "LP-" + uuid.uuid4().hex[:8].upper(),
        "lab": clean["lab"],
        "description": clean["description"],
        "status": "OPEN",
        "report_count": 1,
        "created_at": stamp,
        "updated_at": stamp,
    }
    if clean["reporter_email"]:
        item["reporter_email"] = clean["reporter_email"]
    table.put_item(Item=item, ConditionExpression="attribute_not_exists(report_id)")
    return item


def post_report(event):
    data = parse_body(event)
    if data is None:
        return response(400, {"ok": False, "message": "Invalid request body."})
    clean, errors = validate(data)
    if errors:
        return response(400, {"ok": False, "message": "Validation failed.", "errors": errors})

    merged = False
    record = None
    existing = find_open_report(clean["equipment_id"])
    if existing:
        try:
            record = merge_into(existing)
            merged = True
        except ClientError as err:
            if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
    if record is None:
        record = create_report(clean)

    print(json.dumps({"event": "report_saved", "report_id": record["report_id"],
                      "equipment_id": record["equipment_id"], "merged": merged,
                      "report_count": int(record["report_count"])}))
    return response(200, {
        "ok": True,
        "report_id": record["report_id"],
        "merged": merged,
        "report_count": int(record["report_count"]),
        "status": record["status"],
        "message": "Added to the existing open report." if merged else "New report created.",
    })


def get_status(event):
    equipment_id = ((event.get("pathParameters") or {}).get("equipment_id") or "").strip()
    if not EQUIPMENT_RE.match(equipment_id):
        return response(400, {"ok": False, "message": "Invalid equipment ID."})
    open_report = find_open_report(equipment_id.upper())
    if not open_report:
        return response(200, {"ok": True, "equipment_id": equipment_id.upper(), "has_open_report": False})
    return response(200, {
        "ok": True,
        "equipment_id": open_report["equipment_id"],
        "has_open_report": True,
        "status": open_report["status"],
        "report_count": open_report["report_count"],
        "last_updated": open_report["updated_at"],
    })


def list_reports(event):
    if not is_staff(event):
        return response(403, {"ok": False, "message": "Staff access only."})
    items = []
    kwargs = {}
    while len(items) < 200:
        result = table.scan(**kwargs)
        items.extend(result.get("Items", []))
        if "LastEvaluatedKey" not in result:
            break
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    items.sort(key=lambda i: i.get("updated_at", ""), reverse=True)
    return response(200, {"ok": True, "count": len(items), "reports": items[:200]})


def update_status(event):
    if not is_staff(event):
        return response(403, {"ok": False, "message": "Staff access only."})
    params = event.get("pathParameters") or {}
    equipment_id = (params.get("equipment_id") or "").strip().upper()
    report_id = (params.get("report_id") or "").strip().upper()
    data = parse_body(event) or {}
    new_status = str(data.get("status", "")).strip().upper()
    if not EQUIPMENT_RE.match(equipment_id) or not REPORT_ID_RE.match(report_id):
        return response(400, {"ok": False, "message": "Invalid identifiers."})
    if new_status not in ALL_STATUSES:
        return response(400, {"ok": False, "message": "Status must be one of: " + ", ".join(ALL_STATUSES)})

    stamp = now_iso()
    expression = "SET #s = :s, updated_at = :now"
    values = {":s": new_status, ":now": stamp}
    if new_status == "RESOLVED":
        expression += ", resolved_at = :now"
    try:
        updated = table.update_item(
            Key={"equipment_id": equipment_id, "report_id": report_id},
            UpdateExpression=expression,
            ConditionExpression="attribute_exists(report_id)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return response(404, {"ok": False, "message": "Report not found."})
        raise
    print(json.dumps({"event": "status_changed", "report_id": report_id, "status": new_status}))
    return response(200, {"ok": True, "report_id": report_id, "status": updated["status"]})


ROUTES = {
    "POST /reports": post_report,
    "GET /status/{equipment_id}": get_status,
    "GET /reports": list_reports,
    "PATCH /reports/{equipment_id}/{report_id}": update_status,
}


def lambda_handler(event, context):
    handler = ROUTES.get(event.get("routeKey", ""))
    if handler is None:
        return response(404, {"ok": False, "message": "Not found."})
    try:
        return handler(event)
    except ClientError as err:
        print(json.dumps({"event": "dynamodb_error", "code": err.response["Error"]["Code"]}))
        return response(500, {"ok": False, "message": "Could not complete the request. Please try again."})