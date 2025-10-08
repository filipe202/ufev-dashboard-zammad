import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
import requests

load_dotenv()

ZAMMAD_BASE_URL = os.getenv("ZAMMAD_BASE_URL", "https://ufevsuporte.zammad.com")
ZAMMAD_TOKEN = os.getenv("ZAMMAD_TOKEN")


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")

    @app.route("/")
    def dashboard():
        return render_template(
            "index.html",
            default_from=(datetime.utcnow() - timedelta(days=29)).strftime("%Y-%m-%d"),
            default_to=datetime.utcnow().strftime("%Y-%m-%d"),
            base_url=ZAMMAD_BASE_URL,
            token_required=ZAMMAD_TOKEN is None,
        )

    @app.get("/api/tickets")
    def get_tickets():
        token = ZAMMAD_TOKEN or request.args.get("token", type=str)
        if not token:
            return jsonify({"error": "Missing token"}), 400

        base = request.args.get("base", ZAMMAD_BASE_URL).rstrip("/")
        from_date = request.args.get("from")
        to_date = request.args.get("to")

        if not from_date:
            return jsonify({"error": "Missing 'from' date"}), 400

        date_filter = f"close_at:>={from_date}"
        if to_date:
            date_filter += f" AND close_at:<={to_date}"

        query = f"state:closed AND {date_filter}"

        try:
            users = fetch_paginated(f"{base}/api/v1/users", token)
            tickets = search_tickets(f"{base}/api/v1/tickets/search", token, query)
        except requests.HTTPError as err:
            return jsonify({"error": str(err), "status_code": err.response.status_code}), 502
        except requests.RequestException as err:
            return jsonify({"error": str(err)}), 502

        user_by_id = {}
        for user in users:
            name = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip()
            user_by_id[user["id"]] = name or user.get("login") or f"id_{user['id']}"

        counts = {}
        agents = set()

        for ticket in tickets:
            owner_id = ticket.get("owner_id")
            closed = ticket.get("close_at")
            if not owner_id or not closed:
                continue

            day = iso_day(closed)
            agent = user_by_id.get(owner_id, f"id_{owner_id}")
            counts.setdefault(day, {})
            counts[day][agent] = counts[day].get(agent, 0) + 1
            agents.add(agent)

        days_sorted = sorted(counts.keys())
        agents_sorted = sorted(agents)

        table = [
            {
                "day": day,
                "values": {agent: counts.get(day, {}).get(agent, 0) for agent in agents_sorted},
            }
            for day in days_sorted
        ]

        return jsonify(
            {
                "days": days_sorted,
                "agents": agents_sorted,
                "table": table,
                "total_tickets": len(tickets),
            }
        )

    return app


def fetch_paginated(url: str, token: str):
    page = 1
    items = []

    while True:
        params = {"per_page": 200, "page": page}
        response = requests.get(url, headers=zammad_headers(token), params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if len(data) < 200:
            break
        page += 1

    return items


def search_tickets(url: str, token: str, query: str):
    page = 1
    items = []
    while True:
        params = {"query": query, "expand": "true", "per_page": 200, "page": page}
        response = requests.get(url, headers=zammad_headers(token), params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if len(data) < 200:
            break
        page += 1
    return items


def zammad_headers(token: str):
    return {"Authorization": f"Token token={token}"}


def iso_day(z_iso: str):
    dt = datetime.fromisoformat(z_iso.replace("Z", "+00:00"))
    return dt.date().isoformat()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
