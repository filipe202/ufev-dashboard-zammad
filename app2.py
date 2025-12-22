import os
import json
import requests
from datetime import datetime, timezone
from collections import defaultdict

BASE_URL = os.environ.get("ZAMMAD_BASE_URL", "https://ufevsuporte.zammad.com").rstrip("/")
TOKEN = os.environ.get("ZAMMAD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing ZAMMAD_TOKEN environment variable")

# Mapeamento hardcoded de agentes (id -> nome)
AGENT_NAME_OVERRIDES = {
    21: "Rafaela Lapa",
    724: "Marta Oliveira",
    20: "Catarina França",
    19: "Paula Candeias",
    18: "Cátia Leal",
    17: "Inês Martinho",
    5: "Magali Morim",
    4: "Sandra Reis",
    3: "Carolina Ferreirinha",
}


AGENT_IDS = set(AGENT_NAME_OVERRIDES.keys())

# Intervalo de análise (podes alterar)
FROM_DATE = "2025-09-30"
OPEN_STATE_QUERY = "state:new OR state:open OR state:pending reminder OR state:pending close"
CLOSED_STATES = {"closed"}
OPEN_STATES = {state.strip().lower() for state in OPEN_STATE_QUERY.replace("state:", "").split("OR")}

S = requests.Session()
S.headers.update({"Authorization": f"Token token={TOKEN}"})


def log(message):
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")


def paged_get(path, params=None):
    """Itera paginação até esgotar"""
    out = []
    page = 1
    while True:
        p = dict(params or {})
        p.update({"per_page": 200, "page": page})
        url = f"{BASE_URL}/api/v1{path}"
        log(f"GET {url} params={p}")
        r = S.get(url, params=p, timeout=60)
        log(f"<- {r.status_code} {url}")
        r.raise_for_status()
        data = r.json()
        log(f"   page {page} returned {len(data) if isinstance(data, list) else 'dict keys: ' + ','.join(data.keys()) if isinstance(data, dict) else type(data)}")
        if not data:
            break
        out.extend(data)
        if len(data) < 200:
            break
        page += 1
    return out


def fetch_agents(role_ids=None):
    role_ids = role_ids or [2]
    out = []
    page = 1
    while True:
        payload = {
            "force": True,
            "refresh": False,
            "sort_by": "created_at, id",
            "order_by": "DESC, ASC",
            "page": page,
            "per_page": 200,
            "query": "",
            "role_ids": role_ids,
            "full": True,
        }
        url = f"{BASE_URL}/api/v1/users/search"
        log(f"POST {url} json={payload}")
        r = S.post(url, json=payload, timeout=60)
        log(f"<- {r.status_code} {url}")
        try:
            r.raise_for_status()
        except requests.HTTPError as err:
            if err.response is not None and err.response.status_code == 403:
                log("WARN: sem permissão para /users/search, usando fallback /users")
                return paged_get("/users")
            raise
        data = r.json()

        if isinstance(data, list):
            users_page = data
        elif isinstance(data, dict):
            users_page = data.get("users")
            if users_page is None:
                ids = data.get("data") or data.get("result")
                if ids and isinstance(ids, list):
                    user_assets = data.get("assets", {}).get("User", {})
                    missing = [uid for uid in ids if str(uid) not in user_assets]
                    if missing:
                        log(f"   missing user assets for ids: {missing}")
                    users_page = [
                        user_assets[str(uid)]
                        for uid in ids
                        if str(uid) in user_assets
                    ]
                elif "assets" in data and isinstance(data["assets"], dict):
                    user_assets = data["assets"].get("User")
                    users_page = list(user_assets.values()) if isinstance(user_assets, dict) else []
            if users_page is None:
                users_page = []
            log(f"   dict response keys={list(data.keys())} users={len(users_page)}")
        else:
            users_page = []
            log("   unexpected response type for users, treated as empty")

        if not users_page:
            break

        out.extend(users_page)
        log(f"   accumulated users={len(out)}")

        if len(users_page) < 200:
            break
        page += 1

    return out


def search_tickets(query):
    """Busca tickets via /tickets/search com paginação"""
    out = []
    page = 1
    while True:
        params = {"query": query, "expand": "true", "per_page": 200, "page": page}
        url = f"{BASE_URL}/api/v1/tickets/search"
        log(f"GET {url} params={params}")
        r = S.get(url, params=params, timeout=60)
        log(f"<- {r.status_code} {url}")
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            tickets_page = data.get("tickets") or []
            if tickets_page and isinstance(tickets_page[0], int):
                ticket_assets = data.get("assets", {}).get("Ticket", {})
                missing_assets = [tid for tid in tickets_page if str(tid) not in ticket_assets]
                if missing_assets:
                    log(f"   missing assets for ticket ids: {missing_assets}")
                tickets_page = [
                    ticket_assets[str(ticket_id)]
                    for ticket_id in tickets_page
                    if str(ticket_id) in ticket_assets
                ]
            log(f"   dict response: tickets={len(tickets_page)} keys={list(data.keys())}")
        elif isinstance(data, list):
            tickets_page = data
            log(f"   list response: tickets={len(tickets_page)}")
        else:
            tickets_page = []
            log("   unexpected response type, treated as empty")

        if not tickets_page:
            break

        out.extend(tickets_page)
        log(f"   accumulated tickets={len(out)}")
        if len(tickets_page) < 200:
            break
        page += 1
    return out


def iso_date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    # Mapeamento user_id -> nome
    try:
        users = fetch_agents([2])
    except requests.HTTPError as err:
        log(f"WARN: falha ao obter agentes dinamicamente ({err}), usando apenas mapeamento fixo")
        users = []

    user_by_id = {}
    for u in users:
        fullname = (u.get("fullname") or "").strip()
        name = fullname or f"{u.get('firstname','')} {u.get('lastname','')}".strip() or u.get("login") or f"id_{u['id']}"
        user_by_id[u["id"]] = name

    for agent_id, agent_name in AGENT_NAME_OVERRIDES.items():
        user_by_id[agent_id] = agent_name

    # Mapeamento priority_id -> nome
    try:
        priorities = paged_get("/ticket_priorities")
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 403:
            log("WARN: sem permissão para /ticket_priorities, usando nomes vindos dos tickets")
            priorities = []
        else:
            raise
    priority_by_id = {p["id"]: p.get("name") or f"priority_{p['id']}" for p in priorities}

    # Query ampla e filtro local por estado/data
    all_query = "*"
    tickets_raw = search_tickets(all_query)
    log(f"tickets_total fetched: {len(tickets_raw)}")

    def is_after_from_date(iso_dt: str):
        try:
            return iso_date(iso_dt).date().isoformat() >= FROM_DATE
        except Exception:
            return False

    tickets_closed = []
    tickets_open = []

    for t in tickets_raw:
        state = (t.get("state") or "").strip().lower()
        if state in CLOSED_STATES and t.get("close_at") and is_after_from_date(t.get("close_at")):
            tickets_closed.append(t)
        elif state in OPEN_STATES and t.get("created_at") and is_after_from_date(t.get("created_at")):
            tickets_open.append(t)

    log(f"tickets_closed filtered: {len(tickets_closed)}")
    log(f"tickets_open filtered: {len(tickets_open)}")

    per_agent = defaultdict(
        lambda: {
            "overall": {"tickets_per_day": defaultdict(int), "total_time": 0.0, "count": 0},
            "priorities": defaultdict(lambda: {"tickets_per_day": defaultdict(int), "total_time": 0.0, "count": 0}),
        }
    )
    closed_by_day = defaultdict(int)

    for t in tickets_closed:
        owner_id = t.get("owner_id")
        created = t.get("created_at")
        closed = t.get("close_at")
        if not owner_id or not created or not closed:
            continue

        if AGENT_IDS and owner_id not in AGENT_IDS:
            continue

        try:
            dt_created = iso_date(created)
            dt_closed = iso_date(closed)
        except Exception:
            continue

        day = dt_closed.date().isoformat()
        if day < FROM_DATE:
            continue

        delta = (dt_closed - dt_created).total_seconds() / 3600.0  # em horas
        agent = user_by_id.get(owner_id, AGENT_NAME_OVERRIDES.get(owner_id, f"id_{owner_id}"))
        if agent is None:
            continue
        priority_id = t.get("priority_id")
        priority_name = t.get("priority") or priority_by_id.get(priority_id) or f"priority_{priority_id}" if priority_id else "unknown"

        agent_bucket = per_agent[agent]
        overall_bucket = agent_bucket["overall"]
        priority_bucket = agent_bucket["priorities"][priority_name]

        for bucket in (overall_bucket, priority_bucket):
            bucket["tickets_per_day"][day] += 1
            bucket["total_time"] += delta
            bucket["count"] += 1

        closed_by_day[day] += 1

    open_by_day = defaultdict(int)
    for t in tickets_open:
        created = t.get("created_at")
        if not created:
            continue

        try:
            day_created = iso_date(created).date().isoformat()
        except Exception:
            continue

        if day_created < FROM_DATE:
            continue

        owner_id = t.get("owner_id")
        if owner_id and AGENT_IDS and owner_id not in AGENT_IDS:
            continue

        open_by_day[day_created] += 1

    agents_result = {}

    for agent, buckets in per_agent.items():
        def format_bucket(bucket):
            avg_time = bucket["total_time"] / bucket["count"] if bucket["count"] else None
            return {
                "avg_time_hours": round(avg_time, 2) if avg_time is not None else None,
                "tickets_count": bucket["count"],
                "tickets_per_day": dict(sorted(bucket["tickets_per_day"].items())),
            }

        agents_result[agent] = {
            "overall": format_bucket(buckets["overall"]),
            "priorities": {priority: format_bucket(bucket) for priority, bucket in sorted(buckets["priorities"].items())},
        }

    all_days = sorted(set(closed_by_day.keys()) | set(open_by_day.keys()))
    daily_summary = {
        day: {
            "closed": closed_by_day.get(day, 0),
            "open": open_by_day.get(day, 0),
        }
        for day in all_days
    }

    output = {
        "filters": {"from_date": FROM_DATE},
        "agents": agents_result,
        "daily_summary": daily_summary,
    }

    # Guardar JSON
    with open("zammad_metrics.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("Resultados gravados em zammad_metrics.json")


if __name__ == "__main__":
    main()
