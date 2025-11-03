#!/usr/bin/env python3
"""
Script para redefinir senhas de clientes com domínio @familiaemviagem.com via API Zammad

Funcionalidades:
- Busca todos os usuários com email @familiaemviagem.com
- Define nova senha para cada usuário
- Modo dry-run para testar sem fazer alterações
- Log detalhado de todas as operações
- Geração de senhas aleatórias ou senha fixa
"""

import os
import sys
import json
import csv
import requests
import secrets
import string
from datetime import datetime, timezone, timedelta
from urllib3.exceptions import InsecureRequestWarning

# Desabilitar avisos SSL se necessário
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Configuração da API do Zammad
BASE_URL = os.environ.get("ZAMMAD_BASE_URL", "https://ufevsuporte.zammad.com").rstrip("/")
TOKEN = os.environ.get("ZAMMAD_TOKEN")
VERIFY_SSL = os.environ.get("ZAMMAD_VERIFY_SSL", "false").lower() == "true"
CLIENT_DOMAIN = os.environ.get("CLIENT_DOMAIN", "@familiaemviagem.com")

# Configuração do script
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
DEFAULT_PASSWORD = os.environ.get("DEFAULT_PASSWORD", "")  # Se vazio, gera senhas aleatórias
PASSWORD_LENGTH = int(os.environ.get("PASSWORD_LENGTH", "12"))
CLIENT_ROLE_ID = int(os.environ.get("CLIENT_ROLE_ID", "3"))  # Role ID para Cliente
CREATED_AFTER = os.environ.get("CREATED_AFTER", "")  # Filtrar por data de criação (formato: YYYY-MM-DD)

if not TOKEN:
    print("❌ Erro: ZAMMAD_TOKEN não configurado")
    sys.exit(1)

# Configuração da sessão HTTP
S = requests.Session()
S.headers.update({"Authorization": f"Token token={TOKEN}"})
S.verify = VERIFY_SSL

def log(message):
    """Log com timestamp"""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def get_last_execution_date():
    """Ler data da última execução do arquivo de controle"""
    control_file = os.path.join(os.path.dirname(__file__), "last_reset_date.txt")
    if os.path.exists(control_file):
        try:
            with open(control_file, 'r') as f:
                date_str = f.read().strip()
                return date_str
        except:
            pass
    return None

def save_execution_date():
    """Salvar data e hora da execução atual"""
    control_file = os.path.join(os.path.dirname(__file__), "last_reset_date.txt")
    try:
        # Salvar data e hora atual em formato ISO
        now = datetime.now(timezone.utc).isoformat()
        with open(control_file, 'w') as f:
            f.write(now)
        log(f"✓ Data/hora de execução salva: {now}")
        return True
    except Exception as e:
        log(f"⚠️  Erro ao salvar data de execução: {e}")
        return False

def generate_password(length=12):
    """Gerar senha aleatória segura com requisitos específicos:
    - Mínimo 2 caracteres maiúsculos
    - Mínimo 2 caracteres minúsculos  
    - Mínimo 2 números
    - Mínimo 8 caracteres total
    """
    if length < 8:
        length = 8  # Mínimo 8 caracteres
    
    # Garantir requisitos mínimos
    password_chars = []
    
    # 2 maiúsculas obrigatórias
    password_chars.extend(secrets.choice(string.ascii_uppercase) for _ in range(2))
    
    # 2 minúsculas obrigatórias
    password_chars.extend(secrets.choice(string.ascii_lowercase) for _ in range(2))
    
    # 2 números obrigatórios
    password_chars.extend(secrets.choice(string.digits) for _ in range(2))
    
    # Preencher o resto com caracteres aleatórios (já temos 6 obrigatórios: 2+2+2)
    remaining_length = length - 6
    if remaining_length > 0:
        all_chars = string.ascii_letters + string.digits 
        password_chars.extend(secrets.choice(all_chars) for _ in range(remaining_length))
    
    # Embaralhar para não ter padrão previsível
    secrets.SystemRandom().shuffle(password_chars)
    
    return ''.join(password_chars)

def get_all_roles():
    """Buscar todos os roles do Zammad para debug"""
    try:
        log("Buscando roles disponíveis...")
        response = S.get(f"{BASE_URL}/api/v1/roles", timeout=30)
        if response.status_code == 200:
            roles = response.json()
            log("Roles encontrados:")
            for role in roles:
                log(f"  ID {role.get('id')}: {role.get('name')} - {role.get('note', '')}")
            return roles
        else:
            log(f"Erro ao buscar roles: {response.status_code}")
            return []
    except Exception as e:
        log(f"Erro ao buscar roles: {e}")
        return []

def get_all_users():
    """Buscar todos os usuários do Zammad"""
    log("Buscando todos os usuários...")
    
    users = []
    page = 1
    per_page = 100
    max_pages = 100  # Limite de segurança
    
    while page <= max_pages:
        params = {"per_page": per_page, "page": page}
        url = f"{BASE_URL}/api/v1/users"
        
        try:
            log(f"Buscando página {page}...")
            response = S.get(url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            if not data or len(data) == 0:
                log(f"Página {page} vazia - fim da paginação")
                break
                
            users.extend(data)
            log(f"Página {page}: {len(data)} usuários | Total: {len(users)}")
            
            if len(data) < per_page:
                log(f"Última página encontrada")
                break
                
            page += 1
            
        except Exception as e:
            log(f"Erro na página {page}: {e}")
            break
    
    log(f"Total de usuários encontrados: {len(users)}")
    return users

def filter_client_users(users):
    """Filtrar usuários com email do domínio cliente e role 'Cliente'"""
    filter_msg = f"Filtrando usuários com email {CLIENT_DOMAIN} e role 'Cliente'"
    if CREATED_AFTER:
        filter_msg += f" criados após {CREATED_AFTER}"
    log(filter_msg + "...")
    
    client_users = []
    users_with_password = []
    users_before_date = []
    
    # Parse da data de filtro se fornecida
    created_after_dt = None
    if CREATED_AFTER:
        try:
            from dateutil import parser
            created_after_dt = parser.parse(CREATED_AFTER)
            # Garantir que tem timezone
            if created_after_dt.tzinfo is None:
                created_after_dt = created_after_dt.replace(tzinfo=timezone.utc)
            log(f"Filtrando usuários criados após: {created_after_dt}")
        except:
            try:
                # Tentar formato simples YYYY-MM-DD
                created_after_dt = datetime.strptime(CREATED_AFTER, "%Y-%m-%d")
                # Adicionar timezone UTC
                created_after_dt = created_after_dt.replace(tzinfo=timezone.utc)
                log(f"Filtrando usuários criados após: {created_after_dt}")
            except:
                log(f"⚠️  Formato de data inválido: {CREATED_AFTER}. Ignorando filtro de data.")
    
    for user in users:
        email = user.get("email", "")
        roles = user.get("role_ids", [])
        created_at = user.get("created_at", "")
        
        # Verificar se tem email do domínio
        if not (email and email.lower().endswith(CLIENT_DOMAIN.lower())):
            continue
            
        # Verificar se tem role de Cliente
        if CLIENT_ROLE_ID not in roles:
            log(f"  Ignorando {email} - não tem role Cliente ID {CLIENT_ROLE_ID} (roles: {roles})")
            continue
        
        # Filtrar por data de criação se especificado
        if created_after_dt and created_at:
            try:
                from dateutil import parser
                user_created_dt = parser.parse(created_at)
                # Garantir que tem timezone
                if user_created_dt.tzinfo is None:
                    user_created_dt = user_created_dt.replace(tzinfo=timezone.utc)
            except:
                try:
                    user_created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except:
                    log(f"  ⚠️  Não foi possível parsear data de criação para {email}: {created_at}")
                    continue
            
            if user_created_dt < created_after_dt:
                users_before_date.append(user)
                continue
        
        # Verificar se já tem password definida (verificando se já fez login)
        last_login = user.get("last_login")
        login_failed = user.get("login_failed", 0)
        
        # Se já fez login ou teve tentativas de login, assume que tem password
        if last_login or login_failed > 0:
            log(f"  Ignorando {email} - já tem password definida (último login: {last_login})")
            users_with_password.append(user)
            continue
            
        client_users.append(user)
    
    log(f"Usuários do domínio {CLIENT_DOMAIN} com role Cliente SEM password: {len(client_users)}")
    log(f"Usuários do domínio {CLIENT_DOMAIN} com role Cliente COM password: {len(users_with_password)}")
    if created_after_dt:
        log(f"Usuários criados ANTES de {CREATED_AFTER} (ignorados): {len(users_before_date)}")
    
    # Mostrar alguns exemplos
    for i, user in enumerate(client_users[:5]):
        roles = user.get("role_ids", [])
        created = user.get("created_at", "")[:10] if user.get("created_at") else "?"
        log(f"  {i+1}. {user.get('firstname', '')} {user.get('lastname', '')} - {user.get('email', '')} (criado: {created}, roles: {roles})")
    
    if len(client_users) > 5:
        log(f"  ... e mais {len(client_users) - 5} usuários")
    
    return client_users

def update_user_password(user_id, new_password, user_email):
    """Atualizar senha de um usuário"""
    if DRY_RUN:
        log(f"[DRY-RUN] Senha do usuário {user_id} ({user_email}) seria alterada")
        return True
    
    url = f"{BASE_URL}/api/v1/users/{user_id}"
    
    # Dados para atualização - apenas a senha
    update_data = {
        "password": new_password
    }
    
    try:
        response = S.put(url, json=update_data, timeout=30)
        
        if response.status_code == 200:
            log(f"✓ Senha do usuário {user_id} ({user_email}) atualizada")
            return True
        else:
            log(f"✗ Erro ao atualizar usuário {user_id} ({user_email}): {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        log(f"✗ Erro ao atualizar usuário {user_id} ({user_email}): {e}")
        return False

def save_password_report(results):
    """Salvar relatório com as senhas geradas em JSON e CSV"""
    if DRY_RUN:
        json_filename = "password_reset_report_dry_run.json"
        csv_filename = "password_reset_report_dry_run.csv"
    else:
        json_filename = "password_reset_report.json"
        csv_filename = "password_reset_report.csv"
    
    json_filepath = os.path.join("scripts", json_filename)
    csv_filepath = os.path.join("scripts", csv_filename)
    
    # Salvar JSON
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        log(f"Relatório JSON salvo em: {json_filepath}")
    except Exception as e:
        log(f"Erro ao salvar relatório JSON: {e}")
    
    # Salvar CSV
    try:
        with open(csv_filepath, 'w', newline='', encoding='utf-8') as f:
            if results:
                fieldnames = ['email', 'name', 'new_password', 'success', 'processed_at']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                # Cabeçalho
                writer.writeheader()
                
                # Dados
                for result in results:
                    writer.writerow({
                        'email': result.get('email', ''),
                        'name': result.get('name', ''),
                        'new_password': result.get('new_password', ''),
                        'success': result.get('success', False),
                        'processed_at': result.get('processed_at', '')
                    })
        
        log(f"Relatório CSV salvo em: {csv_filepath}")
        log(f"📋 CSV pronto para importar: email,nome,senha,sucesso,data")
    except Exception as e:
        log(f"Erro ao salvar relatório CSV: {e}")

def main():
    """Função principal"""
    global CREATED_AFTER
    
    log("========================================")
    log("  REDEFINIÇÃO DE SENHAS - CLIENTES")
    log("========================================")
    log(f"Modo: {'DRY-RUN (teste)' if DRY_RUN else 'PRODUÇÃO'}")
    log(f"Domínio: {CLIENT_DOMAIN}")
    log(f"Role Cliente ID: {CLIENT_ROLE_ID}")
    log(f"Senha: {'Aleatória' if not DEFAULT_PASSWORD else 'Fixa'}")
    
    # Verificar se deve usar data da última execução
    if not CREATED_AFTER:
        last_date = get_last_execution_date()
        if last_date:
            CREATED_AFTER = last_date
            log(f"📅 Usando data/hora da última execução: {CREATED_AFTER}")
        else:
            log("📅 Primeira execução - processará todos os usuários")
    else:
        log(f"📅 Data/hora de filtro configurada: {CREATED_AFTER}")
    
    log("")
    
    if not DRY_RUN:
        log("⚠️  ATENÇÃO: Modo PRODUÇÃO ativo!")
        log("⚠️  As senhas serão realmente alteradas!")
        log("")
    
    # 0. Buscar roles para debug
    get_all_roles()
    log("")
    
    # 1. Buscar todos os usuários
    try:
        all_users = get_all_users()
    except Exception as e:
        log(f"✗ Erro ao buscar usuários: {e}")
        return
    
    # 2. Filtrar usuários do domínio cliente
    client_users = filter_client_users(all_users)
    
    if not client_users:
        log("Nenhum usuário encontrado com o domínio especificado")
        return
    
    # 3. Confirmar operação
    log("")
    log(f"Serão processados {len(client_users)} usuários")
    
    if not DRY_RUN:
        confirm = input("Continuar? (digite 'SIM' para confirmar): ")
        if confirm != "SIM":
            log("Operação cancelada pelo usuário")
            return
    
    # 4. Processar cada usuário
    log("")
    log("Iniciando processamento...")
    
    results = []
    success_count = 0
    error_count = 0
    
    for i, user in enumerate(client_users, 1):
        user_id = user.get("id")
        user_email = user.get("email", "")
        user_name = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip()
        
        log(f"[{i}/{len(client_users)}] Processando: {user_name} ({user_email})")
        
        # Gerar ou usar senha padrão
        if DEFAULT_PASSWORD:
            new_password = DEFAULT_PASSWORD
        else:
            new_password = generate_password(PASSWORD_LENGTH)
        
        # Atualizar senha
        success = update_user_password(user_id, new_password, user_email)
        
        # Registrar resultado
        result = {
            "user_id": user_id,
            "email": user_email,
            "name": user_name,
            "new_password": new_password,
            "success": success,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        results.append(result)
        
        if success:
            success_count += 1
        else:
            error_count += 1
    
    # 5. Relatório final
    log("")
    log("========================================")
    log("  RELATÓRIO FINAL")
    log("========================================")
    log(f"Total processado: {len(client_users)}")
    log(f"Sucessos: {success_count}")
    log(f"Erros: {error_count}")
    
    # Salvar relatório
    save_password_report(results)
    
    # Salvar data de execução se houve sucesso em modo produção
    if not DRY_RUN and success_count > 0:
        log("")
        save_execution_date()
        log("⚠️  IMPORTANTE: Senhas foram alteradas!")
        log("⚠️  Verifique o relatório para as novas senhas")
        log("⚠️  Comunique os usuários sobre a alteração")
        log("📅 Próxima execução processará apenas usuários criados após este momento")

if __name__ == "__main__":
    main()
