# scripts/mark_articles_internal_fast.py
# Versão otimizada para execução periódica - apenas tickets abertos
import os
import json
import requests
from datetime import datetime, timezone, timedelta
import re
import sys

# Configuração da API do Zammad
BASE_URL = os.environ.get("ZAMMAD_BASE_URL", "https://ufevsuporte.zammad.com").rstrip("/")
TOKEN = os.environ.get("ZAMMAD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing ZAMMAD_TOKEN environment variable")

CA_BUNDLE = os.environ.get("ZAMMAD_CA_BUNDLE")
VERIFY_SSL = os.environ.get("ZAMMAD_VERIFY_SSL", "false").strip().lower() not in {"0", "false", "no"}

# Configuração da sessão HTTP
S = requests.Session()
S.headers.update({"Authorization": f"Token token={TOKEN}"})

if CA_BUNDLE:
    S.verify = CA_BUNDLE
elif not VERIFY_SSL:
    S.verify = False
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Domínio do cliente para verificação
CLIENT_DOMAIN = "@familiaemviagem.com"

# Modo dry-run (teste sem fazer alterações)
DRY_RUN = "--dry-run" in sys.argv or "-d" in sys.argv

# Estados considerados "abertos" (não fechados)
OPEN_STATES = {"new", "open", "pending reminder", "pending close"}

# Cache para evitar reprocessar artigos já verificados
CACHE_FILE = os.path.join(os.path.dirname(__file__), "processed_articles_cache.json")

def log(message):
    """Log com timestamp"""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def load_cache():
    """Carregar cache de artigos já processados"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                # Limpar entradas antigas (mais de 7 dias)
                cutoff = (datetime.now() - timedelta(days=7)).isoformat()
                cache = {k: v for k, v in cache.items() if v.get('processed_at', '') > cutoff}
                return cache
    except Exception as e:
        log(f"Erro ao carregar cache: {e}")
    return {}

def save_cache(cache):
    """Salvar cache de artigos processados"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        log(f"Erro ao salvar cache: {e}")

def get_all_tickets_and_filter():
    """Buscar todos os tickets e filtrar apenas os abertos"""
    log("Buscando todos os tickets para filtrar apenas os abertos...")
    
    # Usar a mesma função do script original
    out = []
    page = 1
    per_page = 100
    
    while True:
        params = {"per_page": per_page, "page": page}
        url = f"{BASE_URL}/api/v1/tickets"
        log(f"GET {url} params={params}")
        r = S.get(url, params=params, timeout=60)
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
    
    # Agora filtrar apenas tickets abertos
    log(f"Filtrando tickets abertos de {len(out)} tickets totais...")
    
    # Buscar estados da API para mapear IDs
    try:
        states_response = S.get(f"{BASE_URL}/api/v1/ticket_states", timeout=30)
        if states_response.status_code == 200:
            states = states_response.json()
            state_by_id = {s["id"]: s.get("name", "").lower() for s in states}
            log(f"Estados mapeados: {state_by_id}")
        else:
            log(f"Erro ao buscar estados: {states_response.status_code}")
            state_by_id = {}
    except Exception as e:
        log(f"Erro ao buscar estados: {e}")
        state_by_id = {}
    
    # Estados considerados abertos
    open_states = {"new", "open", "pending reminder", "pending close"}
    
    open_tickets = []
    for ticket in out:
        state_id = ticket.get("state_id")
        if state_id and state_id in state_by_id:
            state_name = state_by_id[state_id]
            if state_name in open_states:
                open_tickets.append(ticket)
        else:
            # Se não conseguimos determinar o estado, incluir por segurança
            log(f"Ticket {ticket.get('id')} sem estado conhecido, incluindo por segurança")
            open_tickets.append(ticket)
    
    log(f"Tickets abertos encontrados: {len(open_tickets)} de {len(out)} totais")
    return open_tickets

def extract_emails_from_text(text):
    """Extrair emails de um texto usando regex"""
    if not text:
        return []
    
    # Regex para encontrar emails
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    return [email.lower() for email in emails]

def has_client_email(from_field, to_field, cc_field=None):
    """Verificar se algum dos campos contém email do cliente"""
    all_emails = []
    
    # Extrair emails dos campos
    all_emails.extend(extract_emails_from_text(from_field))
    all_emails.extend(extract_emails_from_text(to_field))
    if cc_field:
        all_emails.extend(extract_emails_from_text(cc_field))
    
    # Verificar se algum email termina com o domínio do cliente
    for email in all_emails:
        if email.endswith(CLIENT_DOMAIN.lower()):
            return True
    
    return False

def update_article_to_internal(article_id, article_data):
    """Atualizar artigo para internal via API PUT"""
    if DRY_RUN:
        log(f"[DRY-RUN] Artigo {article_id} seria marcado como internal")
        return True
    
    url = f"{BASE_URL}/api/v1/ticket_articles/{article_id}"
    
    # Preparar dados para atualização - manter todos os campos existentes
    update_data = {
        "from": article_data.get("from", ""),
        "to": article_data.get("to", ""),
        "cc": article_data.get("cc"),
        "subject": article_data.get("subject", ""),
        "body": article_data.get("body", ""),
        "content_type": article_data.get("content_type", "text/html"),
        "ticket_id": article_data.get("ticket_id"),
        "type_id": article_data.get("type_id", 1),
        "sender_id": article_data.get("sender_id", 2),
        "internal": True,  # Marcar como internal
        "in_reply_to": article_data.get("in_reply_to"),
        "time_unit": article_data.get("time_unit"),
        "preferences": article_data.get("preferences", {}),
        "updated_at": article_data.get("updated_at"),
        "detected_language": article_data.get("detected_language"),
        "id": article_id
    }
    
    try:
        response = S.put(url, json=update_data, timeout=30)
        
        if response.status_code == 200:
            log(f"✓ Artigo {article_id} marcado como internal")
            return True
        else:
            log(f"✗ Erro ao atualizar artigo {article_id}: {response.status_code}")
            return False
            
    except Exception as e:
        log(f"✗ Exceção ao atualizar artigo {article_id}: {e}")
        return False

def process_ticket_articles_fast(ticket_id, cache):
    """Processar artigos de um ticket com cache otimizado"""
    try:
        # Buscar artigos do ticket
        articles_url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
        response = S.get(articles_url, timeout=30)
        
        if response.status_code != 200:
            log(f"✗ Erro ao buscar artigos do ticket {ticket_id}: {response.status_code}")
            return 0, 0
        
        articles = response.json()
        log(f"DEBUG: Ticket {ticket_id} tem {len(articles)} artigos")
        
        processed = 0
        updated = 0
        current_time = datetime.now().isoformat()
        
        for article in articles:
            article_id = article.get("id")
            if not article_id:
                continue
                
            # Verificar cache primeiro
            cache_key = str(article_id)
            if cache_key in cache:
                # Artigo já foi processado, pular
                continue
            
            processed += 1
            
            # Verificar se já é internal
            if article.get("internal", False):
                # Marcar no cache como já processado
                cache[cache_key] = {
                    "processed_at": current_time,
                    "was_internal": True,
                    "action": "skipped_already_internal"
                }
                continue
            
            # Verificar campos from, to e cc
            from_field = article.get("from", "")
            to_field = article.get("to", "")
            cc_field = article.get("cc", "")
            
            # Se não tem email do cliente, marcar como internal
            if not has_client_email(from_field, to_field, cc_field):
                if update_article_to_internal(article_id, article):
                    updated += 1
                    cache[cache_key] = {
                        "processed_at": current_time,
                        "was_internal": False,
                        "action": "marked_internal"
                    }
                else:
                    cache[cache_key] = {
                        "processed_at": current_time,
                        "was_internal": False,
                        "action": "failed_to_update"
                    }
            else:
                # Tem email do cliente, manter público
                cache[cache_key] = {
                    "processed_at": current_time,
                    "was_internal": False,
                    "action": "kept_public"
                }
        
        return processed, updated
        
    except Exception as e:
        log(f"✗ Erro ao processar artigos do ticket {ticket_id}: {e}")
        return 0, 0

def main():
    """Função principal otimizada"""
    mode_text = "MODO TESTE (DRY-RUN)" if DRY_RUN else "MODO EXECUÇÃO"
    log(f"Iniciando processo RÁPIDO de marcação de artigos... [{mode_text}]")
    log(f"Domínio do cliente: {CLIENT_DOMAIN}")
    log("🚀 Versão otimizada - apenas tickets abertos + cache")
    
    if DRY_RUN:
        log("⚠️  ATENÇÃO: Executando em modo teste - nenhuma alteração será feita!")
    else:
        log("⚠️  ATENÇÃO: Executando em modo real - alterações serão feitas no Zammad!")
    
    # Carregar cache
    log("Carregando cache de artigos processados...")
    cache = load_cache()
    log(f"Cache carregado: {len(cache)} artigos já processados")
    
    # Buscar apenas tickets abertos
    try:
        tickets = get_all_tickets_and_filter()
    except Exception as e:
        log(f"✗ Erro ao buscar tickets: {e}")
        return
    
    if not tickets:
        log("Nenhum ticket aberto encontrado. Finalizando.")
        return
    
    total_tickets = len(tickets)
    total_articles_processed = 0
    total_articles_updated = 0
    tickets_processed = 0
    
    # Processar cada ticket
    for i, ticket in enumerate(tickets, 1):
        ticket_id = ticket.get("id")
        if not ticket_id:
            continue
            
        try:
            processed, updated = process_ticket_articles_fast(ticket_id, cache)
            total_articles_processed += processed
            total_articles_updated += updated
            tickets_processed += 1
            
            if processed > 0:
                log(f"Ticket {ticket_id}: {processed} artigos processados, {updated} marcados como internal")
            
            # Log de progresso a cada 50 tickets ou no final
            if i % 50 == 0 or i == total_tickets:
                log(f"Progresso: {i}/{total_tickets} tickets ({(i/total_tickets)*100:.1f}%)")
                # Salvar cache periodicamente
                save_cache(cache)
                
        except Exception as e:
            log(f"✗ Erro ao processar ticket {ticket_id}: {e}")
            continue
    
    # Salvar cache final
    save_cache(cache)
    
    # Resumo final
    log(f"\n=== RESUMO FINAL (VERSÃO RÁPIDA) ===")
    log(f"Tickets abertos processados: {tickets_processed}/{total_tickets}")
    log(f"Artigos novos processados: {total_articles_processed}")
    log(f"Artigos marcados como internal: {total_articles_updated}")
    log(f"Cache atualizado: {len(cache)} artigos")
    log(f"Processo concluído em modo otimizado!")

if __name__ == "__main__":
    main()
