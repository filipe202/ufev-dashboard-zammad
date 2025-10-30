# scripts/generate_metrics.py
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import calendar

# === Ajuste principal: escrever em src/ como módulo JS ===
ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(ROOT, "..", "src", "zammad_metrics.js")

BASE_URL = os.environ.get("ZAMMAD_BASE_URL", "https://ufevsuporte.zammad.com").rstrip("/")
TOKEN = os.environ.get("ZAMMAD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing ZAMMAD_TOKEN environment variable")
CA_BUNDLE = os.environ.get("ZAMMAD_CA_BUNDLE")
VERIFY_SSL = os.environ.get("ZAMMAD_VERIFY_SSL", "false").strip().lower() not in {"0", "false", "no"}

AGENT_NAME_OVERRIDES = {
    21: "Rafaela Lapa",
    20: "Catarina França",
    19: "Paula Candeias",
    18: "Cátia Leal",
    17: "Inês Martinho",
    5: "Magali Morim",
    4: "Sandra Reis",
    3: "Carolina Ferreirinha",
    1: "Não Atribuído",
}
AGENT_IDS = set(AGENT_NAME_OVERRIDES.keys())

FROM_DATE = "2025-09-30"  # Expandir para início de setembro
OPEN_STATE_QUERY = "state:new OR state:open OR state:pending reminder OR state:pending close"
CLOSED_STATES = {"closed"}
OPEN_STATES = {state.strip().lower() for state in OPEN_STATE_QUERY.replace("state:", "").split("OR")}
IGNORED_STATES = {"merged"}  # Estados a ignorar completamente


def format_state_label(raw_state: str | None) -> str:
    raw_state = (raw_state or "").strip()
    if not raw_state:
        return "Desconhecido"
    return " ".join(word.capitalize() for word in raw_state.split())


def make_bucket():
    return {
        "tickets_per_day": defaultdict(int),
        "total_time": 0.0,
        "time_count": 0,
        "count": 0,
    }


def make_state_holder():
    return {
        "overall": make_bucket(),
        "priorities": defaultdict(make_bucket),
    }


def make_holder():
    return {
        "overall": make_bucket(),
        "priorities": defaultdict(make_bucket),
        "states": defaultdict(make_state_holder),
    }


def update_bucket(bucket, day: str, delta_hours: float | None):
    bucket["tickets_per_day"][day] += 1
    bucket["count"] += 1
    if delta_hours is not None:
        bucket["total_time"] += delta_hours
        bucket["time_count"] += 1


def record_entity(holder, day: str, priority_name: str, state_label: str, delta_hours: float | None):
    update_bucket(holder["overall"], day, delta_hours)
    update_bucket(holder["priorities"][priority_name], day, delta_hours)
    state_holder = holder["states"][state_label]
    update_bucket(state_holder["overall"], day, delta_hours)
    update_bucket(state_holder["priorities"][priority_name], day, delta_hours)

S = requests.Session()
S.headers.update({"Authorization": f"Token token={TOKEN}"})

if CA_BUNDLE:
    S.verify = CA_BUNDLE
elif not VERIFY_SSL:
    S.verify = False
    from urllib3.exceptions import InsecureRequestWarning

    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def log(message):
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")


def paged_get(path, params=None):
    out = []
    page = 1
    per_page = 100  # Ajustar para o que a API realmente suporta
    while True:
        p = dict(params or {})
        p.update({"per_page": per_page, "page": page})
        url = f"{BASE_URL}/api/v1{path}"
        log(f"GET {url} params={p}")
        r = S.get(url, params=p, timeout=60)
        log(f"<- {r.status_code} {url}")
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        out.extend(data)
        log(f"Página {page}: {len(data)} tickets, total acumulado: {len(out)}")
        if len(data) < per_page:
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
        else:
            users_page = []

        if not users_page:
            break

        out.extend(users_page)
        if len(users_page) < 200:
            break
        page += 1

    return out


def search_tickets(query):
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
                tickets_page = [
                    ticket_assets.get(str(ticket_id))
                    for ticket_id in tickets_page
                    if str(ticket_id) in ticket_assets
                ]
        elif isinstance(data, list):
            tickets_page = data
        else:
            tickets_page = []

        if not tickets_page:
            break

        out.extend(tickets_page)
        if len(tickets_page) < 200:
            break
        page += 1
    return out


def iso_date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
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

    try:
        priorities = paged_get("/ticket_priorities")
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 403:
            priorities = []
        else:
            raise
    priority_by_id = {p["id"]: p.get("name") or f"priority_{p['id']}" for p in priorities}

    # Buscar estados da API
    try:
        states = paged_get("/ticket_states")
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 403:
            states = []
        else:
            raise
    state_by_id = {s["id"]: s.get("name") or f"state_{s['id']}" for s in states}
    log(f"Estados mapeados: {state_by_id}")

    # Usar endpoint direto em vez de search para garantir todos os tickets
    tickets_raw = paged_get("/tickets")
    log(f"Total tickets encontrados: {len(tickets_raw)}")

    def is_after_from_date(iso_dt: str):
        try:
            return iso_date(iso_dt).date().isoformat() >= FROM_DATE
        except Exception:
            return False

    tickets_closed = []
    tickets_open = []

    for t in tickets_raw:
        created_at = t.get("created_at")
        if created_at and is_after_from_date(created_at):
            state_id = t.get("state_id")
            state_name = state_by_id.get(state_id, "").lower() if state_id else ""
            
            # Ignorar tickets merged
            if state_name in IGNORED_STATES:
                continue
            
            # Incluir TODOS os outros tickets, só separar por estado
            if state_name in CLOSED_STATES:
                tickets_closed.append(t)
            elif state_name in OPEN_STATES:
                tickets_open.append(t)
            else:
                # Incluir outros estados também
                tickets_open.append(t)
    
    log(f"Tickets fechados filtrados: {len(tickets_closed)}")
    log(f"Tickets abertos filtrados: {len(tickets_open)}")
    
    # Debug: verificar estrutura dos tickets
    if tickets_raw:
        sample_ticket = tickets_raw[0]
        log(f"Campos do primeiro ticket: {list(sample_ticket.keys())}")
        log(f"State do primeiro ticket: '{sample_ticket.get('state')}' (type: {type(sample_ticket.get('state'))})")
        log(f"State_id do primeiro ticket: '{sample_ticket.get('state_id')}'")
        
    # Verificar estados únicos
    all_states = set()
    all_state_ids = set()
    for t in tickets_raw:
        state = t.get("state")
        state_id = t.get("state_id")
        if state:
            all_states.add(state)
        if state_id:
            all_state_ids.add(state_id)
    log(f"Estados únicos na API: {sorted(all_states) if all_states else 'NENHUM'}")
    log(f"State_ids únicos na API: {sorted(all_state_ids) if all_state_ids else 'NENHUM'}")

    per_state = defaultdict(make_holder)
    per_agent = defaultdict(make_holder)
    per_customer = defaultdict(make_holder)
    closed_by_day = defaultdict(int)
    
    # Contadores de respostas por agente
    agent_responses = defaultdict(int)
    
    # Métricas de eficiência: interações por ticket fechado
    agent_interactions_per_ticket = defaultdict(lambda: {"total_interactions": 0, "tickets_closed": 0})
    
    # Trocas de estado por agente
    agent_state_changes = defaultdict(lambda: {
        "overall": make_bucket(),
        "priorities": defaultdict(make_bucket)
    })
    
    # Análise temporal - carga de trabalho (criação)
    created_by_weekday = defaultdict(int)  # 0=Segunda, 6=Domingo
    created_by_hour = defaultdict(int)     # 0-23h
    created_by_weekday_hour = defaultdict(lambda: defaultdict(int))  # [weekday][hour]
    
    # Análise temporal - resolução (fechamento)
    closed_by_weekday = defaultdict(int)
    closed_by_hour = defaultdict(int)
    closed_by_weekday_hour = defaultdict(lambda: defaultdict(int))

    for t in tickets_closed:
        owner_id = t.get("owner_id")
        created = t.get("created_at")
        closed = t.get("close_at")
        if not owner_id or not created or not closed:
            continue
        # Remover filtro restritivo de agentes para ver todos os tickets
        # if AGENT_IDS and owner_id not in AGENT_IDS:
        #     continue

        try:
            dt_created = iso_date(created)
            dt_closed = iso_date(closed)
        except Exception:
            continue

        day = dt_closed.date().isoformat()
        if day < FROM_DATE:
            continue

        delta = (dt_closed - dt_created).total_seconds() / 3600.0
        agent = user_by_id.get(owner_id, AGENT_NAME_OVERRIDES.get(owner_id, f"id_{owner_id}"))
        if agent is None:
            continue
        priority_id = t.get("priority_id")
        priority_name = t.get("priority") or priority_by_id.get(priority_id) or (f"priority_{priority_id}" if priority_id else "unknown")
        state_id = t.get("state_id")
        state_label = format_state_label(state_by_id.get(state_id) if state_id else None)

        agent_bucket = per_agent[agent]
        record_entity(agent_bucket, day, priority_name, state_label, delta)

        customer_id = t.get("customer_id")
        customer_label = (t.get("customer") or "").strip()
        if customer_id:
            customer_label = user_by_id.get(customer_id, customer_label or f"cliente_{customer_id}")
        if customer_label:
            customer_bucket = per_customer[customer_label]
            record_entity(customer_bucket, day, priority_name, state_label, delta)

        record_entity(per_state[state_label], day, priority_name, state_label, delta)

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
        # Remover filtro restritivo de agentes para ver todos os tickets
        # if owner_id and AGENT_IDS and owner_id not in AGENT_IDS:
        #     continue
        open_by_day[day_created] += 1

        priority_id = t.get("priority_id")
        priority_name = t.get("priority") or priority_by_id.get(priority_id) or (f"priority_{priority_id}" if priority_id else "unknown")
        state_id = t.get("state_id")
        state_label = format_state_label(state_by_id.get(state_id) if state_id else None)

        if owner_id:
            agent = user_by_id.get(owner_id, AGENT_NAME_OVERRIDES.get(owner_id, f"id_{owner_id}"))
            if agent:
                record_entity(per_agent[agent], day_created, priority_name, state_label, None)

        customer_id = t.get("customer_id")
        customer_label = (t.get("customer") or "").strip()
        if customer_id:
            customer_label = user_by_id.get(customer_id, customer_label or f"cliente_{customer_id}")
        if customer_label:
            record_entity(per_customer[customer_label], day_created, priority_name, state_label, None)

        record_entity(per_state[state_label], day_created, priority_name, state_label, None)

    # Análise temporal - CRIAÇÃO de tickets (todos)
    all_tickets = tickets_closed + tickets_open
    for t in all_tickets:
        created_at = t.get("created_at")
        if not created_at:
            continue
        
        try:
            dt_created = iso_date(created_at)
            # Garantir que está em UTC e converter para Portugal (UTC+1)
            if dt_created.tzinfo is None:
                dt_created = dt_created.replace(tzinfo=timezone.utc)
            
            # Converter para timezone Portugal
            portugal_tz = timezone(timedelta(hours=1))  # UTC+1
            local_dt = dt_created.astimezone(portugal_tz)
            
            weekday = local_dt.weekday()  # 0=Segunda, 6=Domingo
            hour = local_dt.hour
            
            created_by_weekday[weekday] += 1
            created_by_hour[hour] += 1
            created_by_weekday_hour[weekday][hour] += 1
            
        except Exception:
            continue
    
    # Análise temporal - FECHAMENTO de tickets (só fechados)
    for t in tickets_closed:
        closed_at = t.get("close_at")
        if not closed_at:
            continue
        
        try:
            dt_closed = iso_date(closed_at)
            # Garantir que está em UTC e converter para Portugal (UTC+1)
            if dt_closed.tzinfo is None:
                dt_closed = dt_closed.replace(tzinfo=timezone.utc)
            
            # Converter para timezone Portugal
            portugal_tz = timezone(timedelta(hours=1))  # UTC+1
            local_dt = dt_closed.astimezone(portugal_tz)
            
            weekday = local_dt.weekday()  # 0=Segunda, 6=Domingo
            hour = local_dt.hour
            
            closed_by_weekday[weekday] += 1
            closed_by_hour[hour] += 1
            closed_by_weekday_hour[weekday][hour] += 1
            
        except Exception:
            continue

    # Buscar trocas de estado dos tickets
    log("Buscando trocas de estado dos tickets...")
    
    all_tickets_for_history = tickets_closed + tickets_open
    total_state_changes_found = 0
    tickets_with_changes = 0
    
    # Debug: testar diferentes endpoints de histórico
    if all_tickets_for_history:
        first_ticket = all_tickets_for_history[0]
        test_id = first_ticket.get("id")
        log(f"DEBUG: Testando histórico do ticket {test_id}")
        
        # Tentar endpoint 1: /tickets/{id}/history
        try:
            test_url = f"{BASE_URL}/api/v1/tickets/{test_id}/history"
            test_response = S.get(test_url, timeout=30)
            log(f"DEBUG: Endpoint 1 (/tickets/{test_id}/history): {test_response.status_code}")
        except Exception as e:
            log(f"DEBUG: Erro endpoint 1: {e}")
        
        # Tentar endpoint 2: /ticket_history/by_ticket/{id}
        try:
            test_url2 = f"{BASE_URL}/api/v1/ticket_history/by_ticket/{test_id}"
            test_response2 = S.get(test_url2, timeout=30)
            log(f"DEBUG: Endpoint 2 (/ticket_history/by_ticket/{test_id}): {test_response2.status_code}")
            if test_response2.status_code == 200:
                test_history = test_response2.json()
                log(f"DEBUG: Histórico tem {len(test_history)} entradas")
                if test_history:
                    log(f"DEBUG: Primeira entrada: {test_history[0]}")
                    # Verificar atributos disponíveis
                    attributes = set()
                    for h in test_history:
                        if h.get("attribute"):
                            attributes.add(h.get("attribute"))
                    log(f"DEBUG: Atributos encontrados no histórico: {attributes}")
        except Exception as e:
            log(f"DEBUG: Erro endpoint 2: {e}")
        
        # Tentar endpoint 3: buscar o ticket completo com expand
        try:
            test_url3 = f"{BASE_URL}/api/v1/tickets/{test_id}?expand=true"
            test_response3 = S.get(test_url3, timeout=30)
            log(f"DEBUG: Endpoint 3 (/tickets/{test_id}?expand=true): {test_response3.status_code}")
            if test_response3.status_code == 200:
                ticket_data = test_response3.json()
                log(f"DEBUG: Campos disponíveis no ticket: {list(ticket_data.keys())}")
        except Exception as e:
            log(f"DEBUG: Erro endpoint 3: {e}")
    
    # SOLUÇÃO ALTERNATIVA: Usar artigos do ticket para estimar trocas de estado
    # Como a API de histórico não está disponível, vamos contar artigos internos
    # que geralmente indicam mudanças de estado
    log("AVISO: API de histórico não disponível. Usando método alternativo baseado em artigos.")
    
    for t in all_tickets_for_history:
        ticket_id = t.get("id")
        owner_id = t.get("owner_id")
        if not ticket_id:
            continue
        
        try:
            # Buscar artigos do ticket
            articles_url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
            articles_response = S.get(articles_url, timeout=30)
            
            if articles_response.status_code == 200:
                articles = articles_response.json()
                
                # Filtrar artigos internos (geralmente indicam mudanças de estado/gestão)
                internal_articles = [a for a in articles if a.get("internal", False) == True]
                
                if internal_articles:
                    tickets_with_changes += 1
                    priority_id = t.get("priority_id")
                    priority_name = t.get("priority") or priority_by_id.get(priority_id) or (f"priority_{priority_id}" if priority_id else "unknown")
                    
                    # Contar cada artigo interno como uma possível troca de estado
                    for article in internal_articles:
                        created_by_id = article.get("created_by_id")
                        if created_by_id:
                            # Obter nome do agente
                            agent_name = AGENT_NAME_OVERRIDES.get(created_by_id) or user_by_id.get(created_by_id, f"Agente_{created_by_id}")
                            
                            # Obter data do artigo
                            created_at = article.get("created_at")
                            if created_at:
                                try:
                                    dt = iso_date(created_at)
                                    day = dt.date().isoformat()
                                    
                                    if day >= FROM_DATE:
                                        # Registrar como troca de estado
                                        update_bucket(agent_state_changes[agent_name]["overall"], day, None)
                                        update_bucket(agent_state_changes[agent_name]["priorities"][priority_name], day, None)
                                        total_state_changes_found += 1
                                except Exception as e:
                                    log(f"DEBUG: Erro ao processar data: {e}")
                    
                    if len(internal_articles) > 0:
                        log(f"Ticket {ticket_id}: {len(internal_articles)} artigos internos (trocas estimadas)")
                        
                # Se não houver artigos internos mas houver owner, contar pelo menos 1 troca
                elif owner_id:
                    agent_name = AGENT_NAME_OVERRIDES.get(owner_id) or user_by_id.get(owner_id, f"Agente_{owner_id}")
                    priority_id = t.get("priority_id")
                    priority_name = t.get("priority") or priority_by_id.get(priority_id) or (f"priority_{priority_id}" if priority_id else "unknown")
                    
                    created_at = t.get("created_at")
                    if created_at:
                        try:
                            dt = iso_date(created_at)
                            day = dt.date().isoformat()
                            
                            if day >= FROM_DATE:
                                update_bucket(agent_state_changes[agent_name]["overall"], day, None)
                                update_bucket(agent_state_changes[agent_name]["priorities"][priority_name], day, None)
                                total_state_changes_found += 1
                                tickets_with_changes += 1
                        except Exception:
                            pass
                            
        except Exception as e:
            log(f"Erro ao buscar artigos do ticket {ticket_id}: {e}")
    
    log(f"RESUMO: {tickets_with_changes} tickets com trocas, {total_state_changes_found} trocas registradas")
    log(f"DEBUG: agent_state_changes = {dict(agent_state_changes)}")
    
    # Buscar interações reais dos tickets
    log("Buscando interações reais dos tickets...")
    
    for t in tickets_closed:
        owner_id = t.get("owner_id")
        if owner_id and owner_id in AGENT_IDS:
            agent_name = AGENT_NAME_OVERRIDES.get(owner_id, f"Agente_{owner_id}")
            ticket_id = t.get("id")
            
            if ticket_id:
                try:
                    # Buscar artigos (interações) do ticket
                    articles_url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
                    articles_response = S.get(articles_url, timeout=30)
                    
                    if articles_response.status_code == 200:
                        articles = articles_response.json()
                        # Contar apenas artigos públicos (interações com o cliente)
                        public_articles = [a for a in articles if a.get("internal", False) == False]
                        interactions_count = len(public_articles)
                        
                        # Garantir pelo menos 1 interação (o ticket foi criado)
                        if interactions_count == 0:
                            interactions_count = 1
                            
                        agent_responses[agent_name] += interactions_count
                        agent_interactions_per_ticket[agent_name]["total_interactions"] += interactions_count
                        agent_interactions_per_ticket[agent_name]["tickets_closed"] += 1
                        
                        log(f"Ticket {ticket_id}: {interactions_count} interações")
                    else:
                        log(f"Erro ao buscar artigos do ticket {ticket_id}: {articles_response.status_code}")
                        # Fallback para estimativa se não conseguir buscar
                        priority_id = t.get("priority_id", 3)
                        estimated_interactions = max(1, 4 - priority_id) if priority_id <= 4 else 1
                        agent_responses[agent_name] += estimated_interactions
                        agent_interactions_per_ticket[agent_name]["total_interactions"] += estimated_interactions
                        agent_interactions_per_ticket[agent_name]["tickets_closed"] += 1
                        
                except Exception as e:
                    log(f"Erro ao processar ticket {ticket_id}: {e}")
                    # Fallback para estimativa
                    priority_id = t.get("priority_id", 3)
                    estimated_interactions = max(1, 4 - priority_id) if priority_id <= 4 else 1
                    agent_responses[agent_name] += estimated_interactions
                    agent_interactions_per_ticket[agent_name]["total_interactions"] += estimated_interactions
                    agent_interactions_per_ticket[agent_name]["tickets_closed"] += 1
    
    # Calcular média de interações por ticket para cada agente
    agent_efficiency = {}
    for agent_name, data in agent_interactions_per_ticket.items():
        if data["tickets_closed"] > 0:
            avg_interactions = data["total_interactions"] / data["tickets_closed"]
            agent_efficiency[agent_name] = {
                "avg_interactions_per_ticket": round(avg_interactions, 2),
                "total_interactions": data["total_interactions"],
                "tickets_closed": data["tickets_closed"]
            }
    
    # Ordenar por eficiência (menos interações = mais eficiente)
    agent_efficiency = dict(sorted(agent_efficiency.items(), key=lambda x: x[1]["avg_interactions_per_ticket"]))
    
    log(f"Respostas estimadas: {dict(agent_responses)}")
    log(f"Eficiência por agente: {agent_efficiency}")

    def format_bucket(bucket):
        avg_time = bucket["total_time"] / bucket["time_count"] if bucket["time_count"] else None
        return {
            "avg_time_hours": round(avg_time, 2) if avg_time is not None else None,
            "tickets_count": bucket["count"],
            "tickets_per_day": dict(sorted(bucket["tickets_per_day"].items())),
        }

    def sort_bucket_map(bucket_map):
        return {key: format_bucket(b) for key, b in sorted(bucket_map.items())}

    def format_state_map(state_map):
        formatted = {}
        for state_label, state_holder in sorted(state_map.items()):
            formatted[state_label] = {
                "overall": format_bucket(state_holder["overall"]),
                "priorities": sort_bucket_map(state_holder["priorities"]),
            }
        return formatted

    agents_result = {
        agent: {
            "overall": format_bucket(buckets["overall"]),
            "priorities": sort_bucket_map(buckets["priorities"]),
            "states": format_state_map(buckets["states"]),
        }
        for agent, buckets in per_agent.items()
    }

    customers_result = {
        customer: {
            "overall": format_bucket(buckets["overall"]),
            "priorities": sort_bucket_map(buckets["priorities"]),
            "states": format_state_map(buckets["states"]),
        }
        for customer, buckets in per_customer.items()
    }

    states_result = {
        state_label: {
            "overall": format_bucket(buckets["overall"]),
            "priorities": sort_bucket_map(buckets["priorities"]),
        }
        for state_label, buckets in per_state.items()
    }

    all_days = sorted(set(closed_by_day.keys()) | set(open_by_day.keys()))
    daily_summary = {day: {"closed": closed_by_day.get(day, 0), "open": open_by_day.get(day, 0)} for day in all_days}

    # Formatar dados temporais - CRIAÇÃO (dados brutos para calcular médias na interface)
    weekday_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    created_weekdays = {weekday_names[i]: created_by_weekday[i] for i in range(7)}
    created_hours = {f"{h:02d}h": created_by_hour[h] for h in range(24)}
    
    # Heatmap criação: dia da semana x hora
    created_heatmap = []
    for weekday in range(7):
        for hour in range(24):
            created_heatmap.append({
                "weekday": weekday_names[weekday],
                "hour": f"{hour:02d}h",
                "tickets": created_by_weekday_hour[weekday][hour]
            })
    
    # Formatar dados temporais - FECHAMENTO (dados brutos para calcular médias na interface)
    closed_weekdays = {weekday_names[i]: closed_by_weekday[i] for i in range(7)}
    closed_hours = {f"{h:02d}h": closed_by_hour[h] for h in range(24)}
    
    # Heatmap fechamento: dia da semana x hora
    closed_heatmap = []
    for weekday in range(7):
        for hour in range(24):
            closed_heatmap.append({
                "weekday": weekday_names[weekday],
                "hour": f"{hour:02d}h",
                "tickets": closed_by_weekday_hour[weekday][hour]
            })

    output = {
        "filters": {"from_date": FROM_DATE},
        "agents": agents_result,
        "customers": customers_result,
        "daily_summary": daily_summary,
        "states": states_result,
        "workload_analysis": {
            "created": {
                "by_weekday": created_weekdays,
                "by_hour": created_hours,
                "heatmap": created_heatmap,
                "total_tickets": sum(created_by_weekday),
                "period_info": {
                    "from_date": FROM_DATE,
                    "days_in_period": len(all_days)
                }
            },
            "closed": {
                "by_weekday": closed_weekdays,
                "by_hour": closed_hours,
                "heatmap": closed_heatmap,
                "total_tickets": sum(closed_by_weekday),
                "period_info": {
                    "from_date": FROM_DATE,
                    "days_in_period": len(all_days)
                }
            }
        },
        "agent_responses": dict(sorted(agent_responses.items(), key=lambda x: x[1], reverse=True)),
        "agent_efficiency": agent_efficiency,
        "agent_state_changes": {
            agent: {
                "overall": format_bucket(data["overall"]),
                "priorities": sort_bucket_map(data["priorities"])
            }
            for agent, data in agent_state_changes.items()
        }
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("// Dados gerados automaticamente - não editar\n")
        f.write("export const ZAMMAD_METRICS = ")
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    print(f"Resultados gravados em {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
