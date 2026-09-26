"""
ISDO Lab C2 - Mock Jira REST API (Flask).

  GET /rest/agile/1.0/board/requests   all service requests (?request_type= ?priority= ?status= filters)
  GET /rest/api/2/issue/<key>          one request, Jira-style nested 'fields'
  PUT /rest/api/2/issue/<key>          update a request in memory (flat or Jira 'fields' body)
  GET /health                          status

Run from the project root:  python mcp_server/jira_shim.py   (port 5002)
"""

import csv
import os

from flask import Flask, jsonify, request

PORT = 5002
DATA_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "requests.csv"))
FILTERS = ["request_type", "priority", "status"]
JIRA_TO_CSV = {"issuetype": "request_type", "customfield_sla": "sla"}

app = Flask(__name__)


def load_requests():
    """Load requests.csv once at startup into an in-memory dict keyed by issue key."""
    try:
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            return {row["key"]: dict(row) for row in csv.DictReader(f)}
    except FileNotFoundError:
        print(f"Warning: {DATA_FILE} not found - starting with no requests.")
        return {}


REQUESTS = load_requests()


@app.get("/rest/agile/1.0/board/requests")
def list_requests():
    results = list(REQUESTS.values())
    for field in FILTERS:
        value = request.args.get(field)  # Flask decodes "Access+Grant" to "Access Grant"
        if value:
            results = [r for r in results if r.get(field, "").strip().lower() == value.strip().lower()]
    return jsonify({"issues": results, "total": len(results)})


@app.get("/rest/api/2/issue/<key>")
def get_request(key):
    req = REQUESTS.get(key)
    if req is None:
        return jsonify({"errorMessages": [f"Issue {key} does not exist"]}), 404
    return jsonify({"key": key, "fields": {
        "summary": req.get("summary"),
        "issuetype": {"name": req.get("request_type")},
        "priority": {"name": req.get("priority")},
        "status": {"name": req.get("status")},
        "assignee": {"displayName": req.get("assignee")},
        "customfield_sla": req.get("sla"),
    }})


@app.put("/rest/api/2/issue/<key>")
def update_request(key):
    if key not in REQUESTS:
        return jsonify({"errorMessages": [f"Issue {key} does not exist"]}), 404
    body = request.get_json(silent=True)
    fields = body.get("fields", body) if isinstance(body, dict) else {}
    # Jira sends {"status": {"name": "Done"}}; store it flat like the CSV: {"status": "Done"}
    updates = {JIRA_TO_CSV.get(k, k): (v.get("name", v.get("displayName", "")) if isinstance(v, dict) else v)
               for k, v in fields.items() if k != "key"}
    if not updates:
        return jsonify({"errorMessages": ["No update body provided"]}), 400
    REQUESTS[key].update(updates)
    print(f"[Jira Mock] Updated {key}: {updates}")
    return jsonify({"key": key, "message": "Updated successfully"})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "Jira Mock", "requests_loaded": len(REQUESTS)})


if __name__ == "__main__":
    print(f"Jira Mock API starting on http://localhost:{PORT}")
    print(f"Loaded {len(REQUESTS)} requests from {DATA_FILE}")
    app.run(port=PORT, debug=True, use_reloader=False)