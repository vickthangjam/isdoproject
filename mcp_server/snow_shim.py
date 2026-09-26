"""
ISDO Lab C2 - Mock ServiceNow Table API (Flask).

  GET   /api/now/table/incident            all incidents (?category= ?priority= filters)
  GET   /api/now/table/incident/<number>   one incident
  PATCH /api/now/table/incident/<number>   update fields in memory
  GET   /health                            status

Run from the project root:  python mcp_server/snow_shim.py   (port 5001)
"""

import csv
import os

from flask import Flask, jsonify, request

PORT = 5001
DATA_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "incidents.csv"))
FILTERS = ["category", "priority"]

app = Flask(__name__)


def load_incidents():
    """Load incidents.csv once at startup into an in-memory dict keyed by number."""
    try:
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            return {row["number"]: dict(row) for row in csv.DictReader(f)}
    except FileNotFoundError:
        print(f"Warning: {DATA_FILE} not found - starting with no incidents.")
        return {}


INCIDENTS = load_incidents()


@app.get("/api/now/table/incident")
def list_incidents():
    results = list(INCIDENTS.values())
    for field in FILTERS:
        value = request.args.get(field)
        if value:
            results = [r for r in results if r.get(field, "").strip().lower() == value.strip().lower()]
    return jsonify({"result": results, "total": len(results)})


@app.get("/api/now/table/incident/<number>")
def get_incident(number):
    incident = INCIDENTS.get(number)
    if incident is None:
        return jsonify({"error": f"Incident {number} not found"}), 404
    return jsonify({"result": incident})


@app.patch("/api/now/table/incident/<number>")
def update_incident(number):
    if number not in INCIDENTS:
        return jsonify({"error": f"Incident {number} not found"}), 404
    updates = request.get_json(silent=True)
    if not isinstance(updates, dict) or not updates:
        return jsonify({"error": "Body must be a non-empty JSON object"}), 400
    updates.pop("number", None)  # the record key can't be changed
    INCIDENTS[number].update(updates)
    print(f"[ServiceNow Mock] Updated {number}: {updates}")
    return jsonify({"result": INCIDENTS[number], "message": "Updated successfully"})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "ServiceNow Mock", "incidents_loaded": len(INCIDENTS)})


if __name__ == "__main__":
    print(f"ServiceNow Mock API starting on http://localhost:{PORT}")
    print(f"Loaded {len(INCIDENTS)} incidents from {DATA_FILE}")
    # use_reloader=False keeps PATCHed changes from being wiped by an auto-restart
    app.run(port=PORT, debug=True, use_reloader=False)