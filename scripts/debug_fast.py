# scripts/debug_fast.py
# Script de debug para verificar por que o fast não está retornando artigos
import os
import json
import requests
from datetime import datetime, timezone

# Configuração da API do Zammad
BASE_URL = os.environ.get("ZAMMAD_BASE_URL", "https://ufevsuporte.zammad.com").rstrip("/")
TOKEN = os.environ.get("ZAMMAD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing ZAMMAD_TOKEN environment variable")

# Configuração da sessão HTTP
S = requests.Session()
S.headers.update({"Authorization": f"Token token={TOKEN}"})
S.verify = False
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def log(message):
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def debug_tickets():
    """Debug: verificar tickets e seus artigos"""
    
    # 1. Buscar alguns tickets para teste
    log("=== STEP 1: Buscando primeiros 5 tickets ===")
    url = f"{BASE_URL}/api/v1/tickets"
    params = {"per_page": 5, "page": 1}
    
    response = S.get(url, params=params, timeout=30)
    log(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        log(f"Erro: {response.text}")
        return
    
    tickets = response.json()
    log(f"Tickets encontrados: {len(tickets)}")
    
    # 2. Verificar estados
    log("\n=== STEP 2: Verificando estados ===")
    states_response = S.get(f"{BASE_URL}/api/v1/ticket_states", timeout=30)
    if states_response.status_code == 200:
        states = states_response.json()
        state_by_id = {s["id"]: s.get("name", "") for s in states}
        log(f"Estados disponíveis: {state_by_id}")
    else:
        log(f"Erro ao buscar estados: {states_response.status_code}")
        state_by_id = {}
    
    # 3. Analisar cada ticket
    log("\n=== STEP 3: Analisando tickets ===")
    for i, ticket in enumerate(tickets[:3]):  # Apenas primeiros 3
        ticket_id = ticket.get("id")
        state_id = ticket.get("state_id")
        state_name = state_by_id.get(state_id, "unknown")
        
        log(f"\nTicket {ticket_id}:")
        log(f"  - Estado ID: {state_id}")
        log(f"  - Estado Nome: {state_name}")
        log(f"  - Título: {ticket.get('title', 'N/A')[:50]}...")
        
        # 4. Buscar artigos deste ticket
        articles_url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
        articles_response = S.get(articles_url, timeout=30)
        
        if articles_response.status_code == 200:
            articles = articles_response.json()
            log(f"  - Artigos encontrados: {len(articles)}")
            
            # Analisar primeiros 2 artigos
            for j, article in enumerate(articles[:2]):
                article_id = article.get("id")
                is_internal = article.get("internal", False)
                from_field = article.get("from", "")
                to_field = article.get("to", "")
                
                log(f"    Artigo {article_id}:")
                log(f"      - Internal: {is_internal}")
                log(f"      - From: {from_field[:50]}...")
                log(f"      - To: {to_field[:50]}...")
        else:
            log(f"  - Erro ao buscar artigos: {articles_response.status_code}")
    
    # 5. Testar filtro de tickets abertos
    log("\n=== STEP 4: Testando filtro de tickets abertos ===")
    open_states = {"new", "open", "pending reminder", "pending close"}
    
    open_tickets = []
    for ticket in tickets:
        state_id = ticket.get("state_id")
        if state_id and state_id in state_by_id:
            state_name = state_by_id[state_id].lower()
            if state_name in open_states:
                open_tickets.append(ticket)
                log(f"Ticket {ticket.get('id')} é ABERTO (estado: {state_name})")
            else:
                log(f"Ticket {ticket.get('id')} é FECHADO (estado: {state_name})")
    
    log(f"\nRESUMO:")
    log(f"Total tickets testados: {len(tickets)}")
    log(f"Tickets abertos: {len(open_tickets)}")
    
    return open_tickets

if __name__ == "__main__":
    debug_tickets()
