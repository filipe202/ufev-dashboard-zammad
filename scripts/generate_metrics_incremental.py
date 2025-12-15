# scripts/generate_metrics_incremental.py
"""
Versão incremental do generate_metrics.py

Lógica:
- Tickets fechados antes da última execução → não se mexe (usa cache)
- Tickets novos ou não fechados → processa sempre

Ficheiros:
- metrics_cache.json: cache dos tickets já processados
- zammad_metrics.js: output final (igual ao original)
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import calendar

# === Paths ===
ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(ROOT, "..", "src", "zammad_metrics.js")
CACHE_PATH = os.path.join(ROOT, "..", "data", "metrics_cache.json")

# === Config ===
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

FROM_DATE = "2025-09-30"
CLOSED_STATES = {"closed"}
IGNORED_STATES = {"merged", "removed"}

# === Session ===
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


def format_state_label(raw_state: str | None) -> str:
    raw_state = (raw_state or "").strip()
    if not raw_state:
        return "Desconhecido"
    return " ".join(word.capitalize() for word in raw_state.split())


def format_datetime(iso_string: str) -> str:
    if not iso_string:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        portugal_tz = timezone(timedelta(hours=1))
        local_dt = dt.astimezone(portugal_tz)
        return local_dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return iso_string


def iso_date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# === Cache Management ===
def load_cache():
    """Carrega o cache de tickets processados"""
    if not os.path.exists(CACHE_PATH):
        return {
            "last_run": None,
            "closed_tickets": {},  # ticket_id -> dados processados
            "version": 1
        }
    
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
            log(f"Cache carregado: {len(cache.get('closed_tickets', {}))} tickets fechados em cache")
            return cache
    except Exception as e:
        log(f"Erro ao carregar cache: {e}")
        return {
            "last_run": None,
            "closed_tickets": {},
            "version": 1
        }


def save_cache(cache):
    """Guarda o cache de tickets processados"""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    cache["last_run"] = datetime.now(timezone.utc).isoformat()
    
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    log(f"Cache guardado: {len(cache.get('closed_tickets', {}))} tickets fechados")


# === API Functions ===
def paged_get(path, params=None):
    out = []
    page = 1
    per_page = 100
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
        log(f"POST {url}")
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


def get_ticket_articles(ticket_id: int) -> list:
    """Busca todos os artigos de um ticket"""
    url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
    
    try:
        r = S.get(url, timeout=60)
        r.raise_for_status()
        
        response_data = r.json()
        
        if isinstance(response_data, list):
            articles = response_data
        else:
            articles = response_data.get("assets", {}).get("TicketArticle", {})
            if isinstance(articles, dict):
                articles = list(articles.values())
        
        return articles
    except Exception as e:
        log(f"Erro ao buscar artigos do ticket {ticket_id}: {e}")
        return []


def get_first_interaction_time(ticket_id: int) -> str:
    """Retorna o timestamp da primeira interação (segundo artigo)"""
    articles = get_ticket_articles(ticket_id)
    
    if not articles or len(articles) < 2:
        return None
    
    articles.sort(key=lambda x: x.get('created_at', ''))
    return articles[1].get('created_at')


def get_sla_target(priority_name: str) -> dict:
    """Determina o SLA aplicável baseado na prioridade"""
    priority_sla_config = {
        "P1": {"name": "SLA P1", "first_response_time_hours": 0.25},
        "P2": {"name": "SLA P2", "first_response_time_hours": 4},
        "P3": {"name": "SLA P3", "first_response_time_hours": 24},
        "Reservas sem Formulário / sem pedido RGPD e CVO": {
            "name": "Reservas sem formulário",
            "first_response_time_hours": 24,
        },
    }
    
    if priority_name in priority_sla_config:
        return priority_sla_config[priority_name]
    
    return {"name": "SLA Padrão", "first_response_time_hours": 24}


# === Ticket Processing ===
def process_ticket_for_cache(ticket: dict, priority_name: str, state_label: str, 
                             user_by_id: dict, sla_targets: dict) -> dict:
    """
    Processa um ticket e retorna os dados para cache.
    Esta função faz as chamadas à API necessárias (artigos, etc.)
    """
    ticket_id = ticket.get("id")
    owner_id = ticket.get("owner_id")
    created_at = ticket.get("created_at")
    closed_at = ticket.get("close_at")
    customer_id = ticket.get("customer_id")
    
    # Calcular tempo de resolução
    delta_hours = None
    if created_at and closed_at:
        try:
            dt_created = iso_date(created_at)
            dt_closed = iso_date(closed_at)
            delta_hours = (dt_closed - dt_created).total_seconds() / 3600.0
        except Exception:
            pass
    
    # Obter nome do agente
    agent_name = None
    if owner_id:
        agent_name = user_by_id.get(owner_id, AGENT_NAME_OVERRIDES.get(owner_id, f"id_{owner_id}"))
    
    # Obter nome do cliente
    customer_label = (ticket.get("customer") or "").strip()
    if customer_id:
        customer_label = user_by_id.get(customer_id, customer_label or f"cliente_{customer_id}")
    
    # Buscar artigos para SLA e interações
    articles = get_ticket_articles(ticket_id)
    
    # Primeira interação (segundo artigo)
    first_interaction_time = None
    if articles and len(articles) >= 2:
        sorted_articles = sorted(articles, key=lambda x: x.get('created_at', ''))
        first_interaction_time = sorted_articles[1].get('created_at')
    
    # Calcular SLA
    sla_data = calculate_sla_for_ticket(ticket, priority_name, first_interaction_time)
    
    # Contar interações
    public_articles = [a for a in articles if not a.get("internal", False)]
    internal_articles = [a for a in articles if a.get("internal", False)]
    interactions_count = max(1, len(public_articles))
    
    # Data de fechamento
    close_day = None
    if closed_at:
        try:
            close_day = iso_date(closed_at).date().isoformat()
        except Exception:
            pass
    
    # Data de criação
    create_day = None
    if created_at:
        try:
            create_day = iso_date(created_at).date().isoformat()
        except Exception:
            pass
    
    return {
        "ticket_id": ticket_id,
        "ticket_number": ticket.get("number"),
        "title": ticket.get("title", ""),
        "owner_id": owner_id,
        "agent_name": agent_name,
        "customer_id": customer_id,
        "customer_label": customer_label,
        "priority_name": priority_name,
        "state_label": state_label,
        "created_at": created_at,
        "create_day": create_day,
        "closed_at": closed_at,
        "close_day": close_day,
        "delta_hours": delta_hours,
        "sla_data": sla_data,
        "interactions_count": interactions_count,
        "internal_articles_count": len(internal_articles),
        "first_interaction_time": first_interaction_time,
    }


def calculate_sla_for_ticket(ticket: dict, priority_name: str, first_interaction_time: str) -> dict:
    """Calcula dados de SLA para um ticket"""
    sla_target = get_sla_target(priority_name)
    ticket_id = ticket.get("id")
    created_at = ticket.get("created_at")
    
    # Calcular tempo até primeira interação
    first_response_in_min = None
    
    if first_interaction_time and created_at:
        try:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            interaction_dt = datetime.fromisoformat(first_interaction_time.replace('Z', '+00:00'))
            delta = interaction_dt - created_dt
            first_response_in_min = int(delta.total_seconds() / 60)
        except Exception:
            pass
    
    # Fallback para dados do Zammad
    if first_response_in_min is None:
        first_response_in_min = ticket.get("first_response_in_min")
        if first_interaction_time is None:
            first_interaction_time = ticket.get("first_response_at")
    
    # Se ainda não há dados, usar data de fechamento
    if first_response_in_min is None and ticket.get("close_at"):
        first_interaction_time = ticket.get("close_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                closed_dt = datetime.fromisoformat(first_interaction_time.replace('Z', '+00:00'))
                delta = closed_dt - created_dt
                first_response_in_min = int(delta.total_seconds() / 60)
            except Exception:
                pass
    
    # Calcular tempo real em horas
    actual_time_hours = 0.0
    if first_response_in_min is not None and first_response_in_min >= 0:
        actual_time_hours = round(first_response_in_min / 60, 2)
    
    # Verificar SLA
    sla_target_hours = sla_target.get("first_response_time_hours")
    sla_met = None
    sla_breach_hours = None
    
    if sla_target_hours is not None:
        sla_met = actual_time_hours <= sla_target_hours
        sla_breach_hours = round(actual_time_hours - sla_target_hours, 2) if not sla_met else 0
    
    return {
        "sla_target_hours": sla_target_hours,
        "actual_time_hours": actual_time_hours,
        "sla_met": sla_met,
        "sla_breach_hours": sla_breach_hours,
        "sla_name": sla_target.get("name", "SLA Padrão"),
        "first_response_at": first_interaction_time,
    }


# === Aggregation Functions ===
def make_bucket():
    return {
        "tickets_per_day": defaultdict(int),
        "time_per_day": defaultdict(float),
        "time_count_per_day": defaultdict(int),
        "total_time": 0.0,
        "time_count": 0,
        "count": 0,
        "time_values": [],
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
        bucket["time_per_day"][day] += delta_hours
        bucket["time_count_per_day"][day] += 1
        bucket["time_values"].append(delta_hours)


def record_entity(holder, day: str, priority_name: str, state_label: str, delta_hours: float | None):
    update_bucket(holder["overall"], day, delta_hours)
    update_bucket(holder["priorities"][priority_name], day, delta_hours)
    state_holder = holder["states"][state_label]
    update_bucket(state_holder["overall"], day, delta_hours)
    update_bucket(state_holder["priorities"][priority_name], day, delta_hours)


def calculate_mode(time_values):
    if not time_values:
        return None, None
    
    bin_size = 2
    bins = defaultdict(int)
    
    for time_val in time_values:
        bin_index = int(time_val // bin_size)
        bins[bin_index] += 1
    
    if not bins:
        return None, None
    
    most_common_bin, frequency = max(bins.items(), key=lambda x: x[1])
    mode_center = (most_common_bin * bin_size) + (bin_size / 2)
    return round(mode_center, 2), frequency


def calculate_distribution(time_values):
    if not time_values:
        return {}
    
    bin_size = 2
    bins = defaultdict(int)
    
    for time_val in time_values:
        bin_index = int(time_val // bin_size)
        bins[bin_index] += 1
    
    distribution = {}
    for bin_index, count in bins.items():
        start = bin_index * bin_size
        end = start + bin_size
        label = f"{start}-{end}h"
        distribution[label] = count
    
    return dict(sorted(distribution.items(), key=lambda x: int(x[0].split('-')[0])))


def format_bucket(bucket):
    avg_time = bucket["total_time"] / bucket["time_count"] if bucket["time_count"] else None
    mode_time, mode_frequency = calculate_mode(bucket.get("time_values", []))
    distribution = calculate_distribution(bucket.get("time_values", []))
    
    return {
        "avg_time_hours": round(avg_time, 2) if avg_time is not None else None,
        "mode_time_hours": mode_time,
        "mode_frequency": mode_frequency,
        "time_distribution": distribution,
        "tickets_count": bucket["count"],
        "tickets_per_day": dict(sorted(bucket["tickets_per_day"].items())),
        "time_per_day": dict(sorted(bucket["time_per_day"].items())),
        "time_count_per_day": dict(sorted(bucket["time_count_per_day"].items())),
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


# === Main ===
def main():
    log("=== INÍCIO DA EXECUÇÃO INCREMENTAL ===")
    
    # Carregar cache
    cache = load_cache()
    cached_closed_tickets = cache.get("closed_tickets", {})
    last_run = cache.get("last_run")
    
    if last_run:
        log(f"Última execução: {last_run}")
        log(f"Tickets fechados em cache: {len(cached_closed_tickets)}")
    else:
        log("Primeira execução - sem cache")
    
    # Buscar agentes
    try:
        users = fetch_agents([2])
    except requests.HTTPError as err:
        log(f"WARN: falha ao obter agentes ({err}), usando mapeamento fixo")
        users = []

    user_by_id = {}
    for u in users:
        fullname = (u.get("fullname") or "").strip()
        name = fullname or f"{u.get('firstname','')} {u.get('lastname','')}".strip() or u.get("login") or f"id_{u['id']}"
        user_by_id[u["id"]] = name

    for agent_id, agent_name in AGENT_NAME_OVERRIDES.items():
        user_by_id[agent_id] = agent_name

    # Buscar prioridades
    try:
        priorities = paged_get("/ticket_priorities")
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 403:
            priorities = []
        else:
            raise
    priority_by_id = {p["id"]: p.get("name") or f"priority_{p['id']}" for p in priorities}

    # Buscar estados
    try:
        states = paged_get("/ticket_states")
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 403:
            states = []
        else:
            raise
    state_by_id = {s["id"]: s.get("name") or f"state_{s['id']}" for s in states}
    log(f"Estados mapeados: {state_by_id}")

    # Buscar SLAs
    try:
        slas = paged_get("/slas")
        sla_targets = {}
        for sla in slas:
            sla_id = sla.get("id")
            sla_name = sla.get("name") or f"sla_{sla_id}"
            first_response_time = sla.get("first_response_time")
            update_time = sla.get("update_time")
            solution_time = sla.get("solution_time")
            
            sla_targets[sla_id] = {
                "name": sla_name,
                "first_response_time_minutes": first_response_time,
                "update_time_minutes": update_time,
                "solution_time_minutes": solution_time,
                "first_response_time_hours": first_response_time / 60 if first_response_time and first_response_time > 0 else None,
                "update_time_hours": update_time / 60 if update_time and update_time > 0 else None,
                "solution_time_hours": solution_time / 60 if solution_time and solution_time > 0 else None,
            }
    except requests.HTTPError:
        sla_targets = {}

    # Buscar TODOS os tickets (apenas metadados básicos)
    log("Buscando lista de tickets...")
    tickets_raw = paged_get("/tickets")
    log(f"Total tickets encontrados: {len(tickets_raw)}")

    def is_after_from_date(iso_dt: str):
        try:
            return iso_date(iso_dt).date().isoformat() >= FROM_DATE
        except Exception:
            return False

    # Separar tickets
    tickets_to_process = []  # Tickets que precisam de processamento completo
    tickets_from_cache = []  # Tickets que vêm do cache
    tickets_open = []        # Tickets abertos (sempre processados)
    
    # IDs de tickets que estão atualmente na API (para limpar cache de tickets reabertos)
    current_closed_ids = set()
    current_open_ids = set()
    
    for t in tickets_raw:
        created_at = t.get("created_at")
        if not created_at or not is_after_from_date(created_at):
            continue
        
        state_id = t.get("state_id")
        state_name = state_by_id.get(state_id, "").lower() if state_id else ""
        
        # Ignorar tickets merged/removed
        if state_name in IGNORED_STATES:
            continue
        
        ticket_id = str(t.get("id"))
        
        if state_name in CLOSED_STATES:
            current_closed_ids.add(ticket_id)
            # Ticket fechado - verificar se está em cache
            if ticket_id in cached_closed_tickets:
                # Usar dados do cache
                tickets_from_cache.append(cached_closed_tickets[ticket_id])
            else:
                # Novo ticket fechado - processar
                tickets_to_process.append(t)
        else:
            current_open_ids.add(ticket_id)
            # Ticket aberto - sempre processar
            tickets_open.append(t)
    
    # IMPORTANTE: Remover do cache tickets que foram reabertos
    # (estavam fechados no cache mas agora estão abertos)
    reopened_tickets = []
    for ticket_id in list(cached_closed_tickets.keys()):
        if ticket_id in current_open_ids:
            reopened_tickets.append(ticket_id)
            del cached_closed_tickets[ticket_id]
    
    if reopened_tickets:
        log(f"Tickets reabertos (removidos do cache): {len(reopened_tickets)}")
    
    log(f"Tickets fechados em cache (reutilizar): {len(tickets_from_cache)}")
    log(f"Tickets fechados novos (processar): {len(tickets_to_process)}")
    log(f"Tickets abertos (processar): {len(tickets_open)}")
    
    # Processar tickets fechados novos
    new_closed_processed = []
    total_to_process = len(tickets_to_process)
    
    for idx, t in enumerate(tickets_to_process, 1):
        ticket_id = t.get("id")
        if idx % 10 == 0 or idx == total_to_process:
            log(f"Processando ticket fechado {idx}/{total_to_process} (ID: {ticket_id})")
        
        priority_id = t.get("priority_id")
        priority_name = t.get("priority") or priority_by_id.get(priority_id) or (f"priority_{priority_id}" if priority_id else "unknown")
        state_id = t.get("state_id")
        state_label = format_state_label(state_by_id.get(state_id) if state_id else None)
        
        processed = process_ticket_for_cache(t, priority_name, state_label, user_by_id, sla_targets)
        new_closed_processed.append(processed)
        
        # Adicionar ao cache
        cached_closed_tickets[str(ticket_id)] = processed
    
    log(f"Novos tickets fechados processados: {len(new_closed_processed)}")
    
    # Processar tickets abertos (sem cache, mas sem buscar artigos para todos)
    open_processed = []
    total_open = len(tickets_open)
    
    for idx, t in enumerate(tickets_open, 1):
        ticket_id = t.get("id")
        if idx % 50 == 0 or idx == total_open:
            log(f"Processando ticket aberto {idx}/{total_open}")
        
        priority_id = t.get("priority_id")
        priority_name = t.get("priority") or priority_by_id.get(priority_id) or (f"priority_{priority_id}" if priority_id else "unknown")
        state_id = t.get("state_id")
        state_label = format_state_label(state_by_id.get(state_id) if state_id else None)
        
        owner_id = t.get("owner_id")
        agent_name = None
        if owner_id:
            agent_name = user_by_id.get(owner_id, AGENT_NAME_OVERRIDES.get(owner_id, f"id_{owner_id}"))
        
        customer_id = t.get("customer_id")
        customer_label = (t.get("customer") or "").strip()
        if customer_id:
            customer_label = user_by_id.get(customer_id, customer_label or f"cliente_{customer_id}")
        
        created_at = t.get("created_at")
        create_day = None
        if created_at:
            try:
                create_day = iso_date(created_at).date().isoformat()
            except Exception:
                pass
        
        open_processed.append({
            "ticket_id": ticket_id,
            "owner_id": owner_id,
            "agent_name": agent_name,
            "customer_id": customer_id,
            "customer_label": customer_label,
            "priority_name": priority_name,
            "state_label": state_label,
            "created_at": created_at,
            "create_day": create_day,
        })
    
    # Guardar cache atualizado
    save_cache(cache)
    
    # === Agregar dados ===
    log("Agregando dados...")
    
    per_state = defaultdict(make_holder)
    per_agent = defaultdict(make_holder)
    per_customer = defaultdict(make_holder)
    closed_by_day = defaultdict(int)
    open_by_day = defaultdict(int)
    
    agent_responses = defaultdict(int)
    agent_interactions_per_ticket = defaultdict(lambda: {"total_interactions": 0, "tickets_closed": 0})
    agent_state_changes = defaultdict(lambda: {"overall": make_bucket(), "priorities": defaultdict(make_bucket)})
    agent_sla_compliance = defaultdict(lambda: {
        "total_tickets": 0,
        "sla_met": 0,
        "sla_missed": 0,
        "sla_compliance_rate": 0.0,
        "tickets": []
    })
    
    # Análise temporal
    created_by_weekday = defaultdict(int)
    created_by_hour = defaultdict(int)
    created_by_weekday_hour = defaultdict(lambda: defaultdict(int))
    closed_by_weekday = defaultdict(int)
    closed_by_hour = defaultdict(int)
    closed_by_weekday_hour = defaultdict(lambda: defaultdict(int))
    
    # Combinar tickets fechados (cache + novos)
    all_closed = tickets_from_cache + new_closed_processed
    
    for t in all_closed:
        agent_name = t.get("agent_name")
        close_day = t.get("close_day")
        delta_hours = t.get("delta_hours")
        priority_name = t.get("priority_name")
        state_label = t.get("state_label")
        customer_label = t.get("customer_label")
        
        if not close_day or close_day < FROM_DATE:
            continue
        
        # Registar por agente
        if agent_name:
            record_entity(per_agent[agent_name], close_day, priority_name, state_label, delta_hours)
        
        # Registar por cliente
        if customer_label:
            record_entity(per_customer[customer_label], close_day, priority_name, state_label, delta_hours)
        
        # Registar por estado
        record_entity(per_state[state_label], close_day, priority_name, state_label, delta_hours)
        
        # Contagem diária
        closed_by_day[close_day] += 1
        
        # SLA
        sla_data = t.get("sla_data", {})
        if agent_name and sla_data.get("sla_met") is not None:
            agent_sla_compliance[agent_name]["total_tickets"] += 1
            agent_sla_compliance[agent_name]["tickets"].append({
                "ticket_id": t.get("ticket_id"),
                "ticket_number": t.get("ticket_number"),
                "title": t.get("title", "")[:50],
                "priority": priority_name,
                "created_at": format_datetime(t.get("created_at")),
                "close_date": close_day,
                "sla_target_hours": sla_data.get("sla_target_hours"),
                "actual_time_hours": sla_data.get("actual_time_hours"),
                "sla_met": sla_data.get("sla_met"),
                "sla_breach_hours": sla_data.get("sla_breach_hours"),
                "sla_name": sla_data.get("sla_name"),
                "first_response_at": format_datetime(sla_data.get("first_response_at")),
            })
            
            if sla_data.get("sla_met"):
                agent_sla_compliance[agent_name]["sla_met"] += 1
            else:
                agent_sla_compliance[agent_name]["sla_missed"] += 1
        
        # Interações
        interactions = t.get("interactions_count", 1)
        if agent_name:
            agent_responses[agent_name] += interactions
            agent_interactions_per_ticket[agent_name]["total_interactions"] += interactions
            agent_interactions_per_ticket[agent_name]["tickets_closed"] += 1
        
        # State changes (artigos internos)
        internal_count = t.get("internal_articles_count", 0)
        if agent_name and internal_count > 0:
            for _ in range(internal_count):
                update_bucket(agent_state_changes[agent_name]["overall"], close_day, None)
                update_bucket(agent_state_changes[agent_name]["priorities"][priority_name], close_day, None)
        
        # Análise temporal - fechamento
        closed_at = t.get("closed_at")
        if closed_at:
            try:
                dt_closed = iso_date(closed_at)
                if dt_closed.tzinfo is None:
                    dt_closed = dt_closed.replace(tzinfo=timezone.utc)
                portugal_tz = timezone(timedelta(hours=1))
                local_dt = dt_closed.astimezone(portugal_tz)
                
                weekday = local_dt.weekday()
                hour = local_dt.hour
                
                closed_by_weekday[weekday] += 1
                closed_by_hour[hour] += 1
                closed_by_weekday_hour[weekday][hour] += 1
            except Exception:
                pass
    
    # Processar tickets abertos
    for t in open_processed:
        create_day = t.get("create_day")
        if not create_day or create_day < FROM_DATE:
            continue
        
        agent_name = t.get("agent_name")
        priority_name = t.get("priority_name")
        state_label = t.get("state_label")
        customer_label = t.get("customer_label")
        
        open_by_day[create_day] += 1
        
        if agent_name:
            record_entity(per_agent[agent_name], create_day, priority_name, state_label, None)
        
        if customer_label:
            record_entity(per_customer[customer_label], create_day, priority_name, state_label, None)
        
        record_entity(per_state[state_label], create_day, priority_name, state_label, None)
    
    # Análise temporal - criação (todos os tickets)
    all_tickets_for_temporal = all_closed + open_processed
    for t in all_tickets_for_temporal:
        created_at = t.get("created_at")
        if not created_at:
            continue
        
        try:
            dt_created = iso_date(created_at)
            if dt_created.tzinfo is None:
                dt_created = dt_created.replace(tzinfo=timezone.utc)
            portugal_tz = timezone(timedelta(hours=1))
            local_dt = dt_created.astimezone(portugal_tz)
            
            weekday = local_dt.weekday()
            hour = local_dt.hour
            
            created_by_weekday[weekday] += 1
            created_by_hour[hour] += 1
            created_by_weekday_hour[weekday][hour] += 1
        except Exception:
            pass
    
    # Calcular eficiência
    agent_efficiency = {}
    for agent_name, data in agent_interactions_per_ticket.items():
        if data["tickets_closed"] > 0:
            avg_interactions = data["total_interactions"] / data["tickets_closed"]
            agent_efficiency[agent_name] = {
                "avg_interactions_per_ticket": round(avg_interactions, 2),
                "total_interactions": data["total_interactions"],
                "tickets_closed": data["tickets_closed"]
            }
    agent_efficiency = dict(sorted(agent_efficiency.items(), key=lambda x: x[1]["avg_interactions_per_ticket"]))
    
    # Calcular taxas de SLA
    for agent_name, sla_data in agent_sla_compliance.items():
        total = sla_data["total_tickets"]
        if total > 0:
            sla_data["sla_compliance_rate"] = round((sla_data["sla_met"] / total) * 100, 2)
    
    # === Formatar output ===
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

    # Formatar dados temporais
    weekday_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    created_weekdays = {weekday_names[i]: created_by_weekday[i] for i in range(7)}
    created_hours = {f"{h:02d}h": created_by_hour[h] for h in range(24)}
    
    created_heatmap = []
    for weekday in range(7):
        for hour in range(24):
            created_heatmap.append({
                "weekday": weekday_names[weekday],
                "hour": f"{hour:02d}h",
                "tickets": created_by_weekday_hour[weekday][hour]
            })
    
    closed_weekdays = {weekday_names[i]: closed_by_weekday[i] for i in range(7)}
    closed_hours = {f"{h:02d}h": closed_by_hour[h] for h in range(24)}
    
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
                "total_tickets": sum(created_by_weekday.values()),
                "period_info": {
                    "from_date": FROM_DATE,
                    "days_in_period": len(all_days)
                }
            },
            "closed": {
                "by_weekday": closed_weekdays,
                "by_hour": closed_hours,
                "heatmap": closed_heatmap,
                "total_tickets": sum(closed_by_weekday.values()),
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
        },
        "agent_active_time": {},  # Simplificado na versão incremental
        "sla_analysis": {
            "sla_targets": sla_targets,
            "agent_sla_compliance": dict(agent_sla_compliance),
            "summary": {
                "total_tickets_analyzed": sum(data["total_tickets"] for data in agent_sla_compliance.values()),
                "total_sla_met": sum(data["sla_met"] for data in agent_sla_compliance.values()),
                "total_sla_missed": sum(data["sla_missed"] for data in agent_sla_compliance.values()),
                "overall_compliance_rate": round(
                    (sum(data["sla_met"] for data in agent_sla_compliance.values()) / 
                     max(1, sum(data["total_tickets"] for data in agent_sla_compliance.values()))) * 100, 2
                )
            }
        },
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cached_closed_tickets": len(tickets_from_cache),
            "new_closed_tickets": len(new_closed_processed),
            "open_tickets": len(open_processed),
            "incremental": True
        }
    }
    
    # Escrever output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("// Dados gerados automaticamente - não editar\n")
        f.write("export const ZAMMAD_METRICS = ")
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    
    log(f"Resultados gravados em {OUTPUT_PATH}")
    log(f"=== FIM DA EXECUÇÃO ===")
    log(f"Resumo: {len(tickets_from_cache)} tickets do cache + {len(new_closed_processed)} novos fechados + {len(open_processed)} abertos")


if __name__ == "__main__":
    main()
