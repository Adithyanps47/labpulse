import json
import re
import uuid

EQUIPMENT_RE = re.compile(r"^[A-Za-z0-9-]{2,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


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


def lambda_handler(event, context):
    try:
        data = json.loads(event.get("body") or "{}")
        if not isinstance(data, dict):
            raise ValueError("Body must be a JSON object")
    except (ValueError, TypeError):
        return response(400, {"ok": False, "message": "Invalid request body."})

    clean, errors = validate(data)
    if errors:
        return response(400, {"ok": False, "message": "Validation failed.", "errors": errors})

    report_id = "LP-" + uuid.uuid4().hex[:8].upper()
    print(json.dumps({"event": "report_received", "report_id": report_id,
                      "equipment_id": clean["equipment_id"], "lab": clean["lab"]}))

    return response(200, {
        "ok": True,
        "report_id": report_id,
        "message": "Report received. (Beginner version: not stored yet.)",
    })