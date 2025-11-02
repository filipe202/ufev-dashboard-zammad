# scripts/mark_articles_internal.py
import os
import json
import requests
from datetime import datetime, timezone
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

def log(message):
    """Log com timestamp"""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def paged_get(path, params=None):
    """Buscar dados paginados da API"""
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
        log(f"Página {page}: {len(data)} itens, total acumulado: {len(out)}")
        if len(data) < per_page:
            break
        page += 1
    return out

def extract_emails_from_text(text):
    """Extrair emails de um texto usando regex"""
    if not text:
        return []
    
    # Regex para encontrar emails
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    return [email.lower() for email in emails]

def has_client_email(from_field, to_field, cc_field=None):
    """Verificar se algum dos campos contém email do cliente (@umafamiliaemviagem.com)"""
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
    
    log(f"Atualizando artigo {article_id} para internal...")
    
    try:
        response = S.put(url, json=update_data, timeout=60)
        log(f"<- {response.status_code} {url}")
        
        if response.status_code == 200:
            log(f"✓ Artigo {article_id} marcado como internal com sucesso")
            return True
        else:
            log(f"✗ Erro ao atualizar artigo {article_id}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        log(f"✗ Exceção ao atualizar artigo {article_id}: {e}")
        return False

def process_ticket_articles(ticket_id):
    """Processar todos os artigos de um ticket"""
    log(f"Processando artigos do ticket {ticket_id}...")
    
    try:
        # Buscar artigos do ticket
        articles_url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
        response = S.get(articles_url, timeout=60)
        
        if response.status_code != 200:
            log(f"✗ Erro ao buscar artigos do ticket {ticket_id}: {response.status_code}")
            return 0, 0
        
        articles = response.json()
        log(f"Encontrados {len(articles)} artigos no ticket {ticket_id}")
        
        processed = 0
        updated = 0
        
        for article in articles:
            article_id = article.get("id")
            if not article_id:
                continue
                
            processed += 1
            
            # Verificar se já é internal
            if article.get("internal", False):
                log(f"Artigo {article_id} já é internal, pulando...")
                continue
            
            # Verificar campos from, to e cc
            from_field = article.get("from", "")
            to_field = article.get("to", "")
            cc_field = article.get("cc", "")
            
            log(f"Artigo {article_id}: from='{from_field}', to='{to_field}', cc='{cc_field}'")
            
            # Se não tem email do cliente, marcar como internal
            if not has_client_email(from_field, to_field, cc_field):
                log(f"Artigo {article_id} não tem email do cliente, marcando como internal...")
                if update_article_to_internal(article_id, article):
                    updated += 1
            else:
                log(f"Artigo {article_id} tem email do cliente, mantendo público")
        
        return processed, updated
        
    except Exception as e:
        log(f"✗ Erro ao processar artigos do ticket {ticket_id}: {e}")
        return 0, 0

def main():
    """Função principal"""
    mode_text = "MODO TESTE (DRY-RUN)" if DRY_RUN else "MODO EXECUÇÃO"
    log(f"Iniciando processo de marcação de artigos como internal... [{mode_text}]")
    log(f"Domínio do cliente: {CLIENT_DOMAIN}")
    
    if DRY_RUN:
        log("⚠️  ATENÇÃO: Executando em modo teste - nenhuma alteração será feita!")
        log("   Para executar as alterações reais, execute sem --dry-run")
    else:
        log("⚠️  ATENÇÃO: Executando em modo real - alterações serão feitas no Zammad!")
    
    # Buscar todos os tickets
    log("Buscando todos os tickets...")
    try:
        tickets = paged_get("/tickets")
        log(f"Total de tickets encontrados: {len(tickets)}")
    except Exception as e:
        log(f"✗ Erro ao buscar tickets: {e}")
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
            
        log(f"\n--- Processando ticket {ticket_id} ({i}/{total_tickets}) ---")
        
        try:
            processed, updated = process_ticket_articles(ticket_id)
            total_articles_processed += processed
            total_articles_updated += updated
            tickets_processed += 1
            
            if i % 10 == 0:  # Log de progresso a cada 10 tickets
                log(f"Progresso: {i}/{total_tickets} tickets processados")
                
        except Exception as e:
            log(f"✗ Erro ao processar ticket {ticket_id}: {e}")
            continue
    
    # Resumo final
    log(f"\n=== RESUMO FINAL ===")
    log(f"Tickets processados: {tickets_processed}/{total_tickets}")
    log(f"Artigos processados: {total_articles_processed}")
    log(f"Artigos marcados como internal: {total_articles_updated}")
    log(f"Processo concluído!")

if __name__ == "__main__":
    main()
