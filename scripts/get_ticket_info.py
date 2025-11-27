#!/usr/bin/env python3
"""
Script para buscar informações detalhadas de um ticket específico do Zammad
"""

import os
import sys
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

BASE_URL = os.getenv("ZAMMAD_URL", "").rstrip("/")
TOKEN = os.getenv("ZAMMAD_TOKEN", "")
VERIFY_SSL = os.getenv("VERIFY_SSL", "false").lower() == "true"
CA_BUNDLE = os.getenv("CA_BUNDLE")

if not BASE_URL or not TOKEN:
    print("❌ Erro: ZAMMAD_URL e ZAMMAD_TOKEN devem estar definidos no .env")
    sys.exit(1)

# Configurar sessão
S = requests.Session()
S.headers.update({"Authorization": f"Token token={TOKEN}"})

if CA_BUNDLE:
    S.verify = CA_BUNDLE
elif not VERIFY_SSL:
    S.verify = False
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def get_ticket_articles(ticket_id: int) -> list:
    """Busca todos os artigos de um ticket"""
    url = f"{BASE_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
    
    print(f"🔍 Buscando artigos do ticket #{ticket_id}...")
    r = S.get(url, timeout=60)
    r.raise_for_status()
    
    response_data = r.json()
    
    # A API pode retornar lista diretamente ou com assets
    if isinstance(response_data, list):
        articles = response_data
    else:
        articles = response_data.get("assets", {}).get("TicketArticle", {})
        if isinstance(articles, dict):
            articles = list(articles.values())
    
    return articles


def get_first_agent_response(ticket_id: int) -> dict:
    """Encontra a primeira interação/resposta (segundo artigo)"""
    articles = get_ticket_articles(ticket_id)
    
    if not articles:
        return None
    
    # Ordenar por data de criação
    articles.sort(key=lambda x: x.get('created_at', ''))
    
    print(f"\n📋 LISTA DE ARTIGOS (em ordem cronológica):")
    for i, article in enumerate(articles, 1):
        sender_type = article.get('sender_id')
        article_type = article.get('type_id')
        created_at = article.get('created_at')
        article_id = article.get('id')
        from_email = article.get('from', 'N/A')
        
        # Mapear tipos para nomes
        sender_names = {1: "Customer", 2: "Agent", 3: "System"}
        type_names = {1: "web", 2: "email", 3: "phone", 4: "internal", 5: "note", 10: "twitter"}
        
        sender_name = sender_names.get(sender_type, f"Unknown({sender_type})")
        type_name = type_names.get(article_type, f"Unknown({article_type})")
        
        print(f"   {i}. [{sender_name}] {type_name} - {format_datetime(created_at)} (ID: {article_id})")
        print(f"      From: {from_email}")
    
    # A primeira interação é o segundo artigo (índice 1)
    if len(articles) >= 2:
        first_interaction = articles[1]  # Segundo artigo
        print(f"\n✅ PRIMEIRA INTERAÇÃO é o artigo #2: {first_interaction.get('created_at')}")
        
        sender_type = first_interaction.get('sender_id')
        article_type = first_interaction.get('type_id')
        from_email = first_interaction.get('from', 'N/A')
        
        sender_names = {1: "Customer", 2: "Agent", 3: "System"}
        type_names = {1: "web", 2: "email", 3: "phone", 4: "internal", 5: "note", 10: "twitter"}
        
        print(f"   Tipo: {type_names.get(article_type, 'Unknown')}, Sender: {sender_names.get(sender_type, 'Unknown')}")
        print(f"   From: {from_email}")
        
        return first_interaction
    
    print(f"\n❌ Apenas um artigo encontrado, sem interação")
    return None


def get_ticket_by_number(ticket_number: str) -> dict:
    """Busca um ticket pelo número"""
    url = f"{BASE_URL}/api/v1/tickets/search"
    params = {
        "query": f"number:{ticket_number}",
        "limit": 1
    }
    
    print(f"🔍 Buscando ticket #{ticket_number}...")
    r = S.get(url, params=params, timeout=60)
    r.raise_for_status()
    
    response_data = r.json()
    
    # Debug: mostrar estrutura da resposta
    print(f"🐛 Estrutura da resposta: {type(response_data)}")
    if isinstance(response_data, list):
        print(f"🐛 Resposta é lista com {len(response_data)} itens")
        if response_data:
            print(f"🐛 Primeiro item: {response_data[0]}")
    elif isinstance(response_data, dict):
        print(f"🐛 Chaves: {list(response_data.keys())}")
    
    # A API pode retornar diretamente uma lista de tickets
    if isinstance(response_data, list):
        if not response_data:
            print(f"❌ Ticket #{ticket_number} não encontrado")
            return None
        ticket = response_data[0]
    else:
        # Estrutura original com assets
        tickets = response_data.get("assets", {}).get("Ticket", {})
        
        if not tickets:
            print(f"❌ Ticket #{ticket_number} não encontrado")
            return None
        
        # Pegar o primeiro ticket encontrado
        ticket_id = list(tickets.keys())[0]
        ticket = tickets[ticket_id]
    
    return ticket


def format_datetime(dt_str: str) -> str:
    """Formata datetime ISO para formato legível"""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    except:
        return dt_str


def display_ticket_info(ticket: dict):
    """Exibe informações do ticket de forma formatada"""
    if not ticket:
        return
    
    print("\n" + "="*80)
    print("INFORMAÇÕES DO TICKET")
    print("="*80)
    print(ticket)
    
    print(f"\n📋 DADOS BÁSICOS:")
    print(f"   ID: {ticket.get('id')}")
    print(f"   Número: #{ticket.get('number')}")
    print(f"   Título: {ticket.get('title')}")
    print(f"   Estado: {ticket.get('state_id')}")
    print(f"   Prioridade: {ticket.get('priority_id')}")
    print(f"   Grupo: {ticket.get('group_id')}")
    print(f"   Owner: {ticket.get('owner_id')}")
    
    print(f"\n📅 DATAS:")
    print(f"   Criado em: {format_datetime(ticket.get('created_at'))}")
    print(f"   Atualizado em: {format_datetime(ticket.get('updated_at'))}")
    print(f"   Fechado em: {format_datetime(ticket.get('close_at'))}")
    
    print(f"\n⏱️  SLA - PRIMEIRA RESPOSTA:")
    print(f"   First Response At: {format_datetime(ticket.get('first_response_at'))}")
    print(f"   First Response Escalation At: {format_datetime(ticket.get('first_response_escalation_at'))}")
    print(f"   First Response In Min: {ticket.get('first_response_in_min')}")
    print(f"   First Response Diff In Min: {ticket.get('first_response_diff_in_min')}")
    
    print(f"\n⏱️  SLA - ATUALIZAÇÃO:")
    print(f"   Update Escalation At: {format_datetime(ticket.get('update_escalation_at'))}")
    print(f"   Update In Min: {ticket.get('update_in_min')}")
    print(f"   Update Diff In Min: {ticket.get('update_diff_in_min')}")
    
    print(f"\n⏱️  SLA - SOLUÇÃO:")
    print(f"   Solution Escalation At: {format_datetime(ticket.get('solution_escalation_at'))}")
    print(f"   Solution In Min: {ticket.get('solution_in_min')}")
    print(f"   Solution Diff In Min: {ticket.get('solution_diff_in_min')}")
    
    print(f"\n🔧 OUTROS:")
    print(f"   Pending Time: {format_datetime(ticket.get('pending_time'))}")
    print(f"   Last Contact At: {format_datetime(ticket.get('last_contact_at'))}")
    print(f"   Last Contact Agent At: {format_datetime(ticket.get('last_contact_agent_at'))}")
    print(f"   Last Contact Customer At: {format_datetime(ticket.get('last_contact_customer_at'))}")
    
    print("\n" + "="*80)
    
    # Buscar primeira interação (segundo artigo)
    print(f"\n🔍 VERIFICANDO PRIMEIRA INTERAÇÃO...")
    first_agent_article = get_first_agent_response(ticket.get('id'))
    
    if first_agent_article:
        interaction_time = first_agent_article.get('created_at')
        print(f"   Primeira interação: {format_datetime(interaction_time)}")
        
        # Calcular tempo real até primeira interação
        if ticket.get('created_at') and interaction_time:
            created = datetime.fromisoformat(ticket.get('created_at').replace('Z', '+00:00'))
            interaction_occurred = datetime.fromisoformat(interaction_time.replace('Z', '+00:00'))
            real_delta = interaction_occurred - created
            
            print(f"\n📊 ANÁLISE COMPARATIVA:")
            print(f"   Tempo até primeira resposta (Zammad API): {ticket.get('first_response_in_min')} minutos")
            print(f"   Tempo até primeira interação (real): {real_delta}")
            print(f"   Diferença SLA (Zammad): {ticket.get('first_response_diff_in_min')} minutos")
            
            # Converter para minutos para comparação
            real_minutes = int(real_delta.total_seconds() / 60)
            print(f"   Tempo real em minutos: {real_minutes}")
            
            if ticket.get('first_response_diff_in_min'):
                if ticket.get('first_response_diff_in_min') <= 0:
                    print(f"   ✅ SLA CUMPRIDO (segundo Zammad)")
                else:
                    print(f"   ❌ SLA VIOLADO em {ticket.get('first_response_diff_in_min')} minutos (segundo Zammad)")
    else:
        print(f"   ❌ Nenhuma interação encontrada")
    
    # Análise original do Zammad
    if ticket.get('first_response_in_min') and ticket.get('created_at') and ticket.get('first_response_at'):
        created = datetime.fromisoformat(ticket.get('created_at').replace('Z', '+00:00'))
        responded = datetime.fromisoformat(ticket.get('first_response_at').replace('Z', '+00:00'))
        delta = responded - created
        
        print(f"\n📊 ANÁLISE ORIGINAL (Zammad):")
        print(f"   Tempo até primeira resposta (calculado): {delta}")
        print(f"   Tempo até primeira resposta (Zammad): {ticket.get('first_response_in_min')} minutos")
        print(f"   Diferença SLA: {ticket.get('first_response_diff_in_min')} minutos")
        
        if ticket.get('first_response_diff_in_min'):
            if ticket.get('first_response_diff_in_min') <= 0:
                print(f"   ✅ SLA CUMPRIDO")
            else:
                print(f"   ❌ SLA VIOLADO em {ticket.get('first_response_diff_in_min')} minutos")
        
        print("="*80 + "\n")


def main():
    if len(sys.argv) < 2:
        print("Uso: python get_ticket_info.py <numero_ticket>")
        print("Exemplo: python get_ticket_info.py 351814")
        sys.exit(1)
    
    ticket_number = sys.argv[1].replace('#', '')
    
    try:
        ticket = get_ticket_by_number(ticket_number)
        display_ticket_info(ticket)
    except Exception as e:
        print(f"❌ Erro ao buscar ticket: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
