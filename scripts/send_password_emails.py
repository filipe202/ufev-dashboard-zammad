#!/usr/bin/env python3
"""
Script para enviar emails com as novas senhas dos clientes

Funcionalidades:
- Lê o relatório CSV gerado pelo reset de senhas
- Envia email personalizado para cada cliente
- Suporte para Gmail, Outlook e SMTP customizado
- Templates de email personalizáveis
- Modo dry-run para testar
"""

import os
import sys
import csv
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timezone

# Configuração SMTP
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")  # Seu email
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # Sua senha/app password
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

# Configuração do email
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USERNAME)
FROM_NAME = os.environ.get("FROM_NAME", "Carolina Ferreirinha")
SUBJECT = os.environ.get("EMAIL_SUBJECT", "Acessos à plataforma de suporte UFEV")

# Configuração do script
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
CSV_FILE = os.environ.get("CSV_FILE", "scripts/password_reset_report.csv")

def log(message):
    """Log com timestamp"""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def get_email_template():
    """Template do email"""
    return """
Olá {name},

Bem-vindo(a) a nossa plataforma de suporte da UFEV! 

A tua conta ja esta pronta - aqui estao os teus dados de acesso:

 Utilizador: {email}
 Palavra-passe temporária: {password}

Por favor, acede à plataforma e altera a tua palavra-passe no primeiro login:
 https://ufevsuporte.zammad.com

Se precisares de ajuda, estamos deste lado para o que for preciso! 

#somosfamilia

Equipa de Suporte UFEV

Aqui pode consultar a ficha de informação normalizada da empresa:
https://drive.google.com/file/d/1tILG1w3tkLPJjj-DDhvfwjcDnPLmp2gJ/view?usp=drive_link

Aqui pode consultar as condições gerais de venda da empresa:
https://drive.google.com/file/d/1QsfLAhpmpOL8R_zPaUg-k60_O_zxNd2q/view?usp=drive_link
"""

def get_html_email_template():
    """Template HTML do email de teste"""
    html = "<html><body style='font-family:Arial,sans-serif;color:#333;'>"
    html += "<p>Ola {name},</p>"
    html += "<p>Aqui vão os teus dados de acesso para a plataforma de suporte:</p>"
    html += "<p><strong>Utilizador:</strong> {email}<br>"
    html += "<strong>Palavra-passe:</strong> {password}</p>"
    html += "<p>Acede aqui à plataforma: <a href='https://ufevsuporte.zammad.com'>https://ufevsuporte.zammad.com</a></p>"
    html += "<p>#somosfamilia</p>"
    html += "<p>Obrigada!</p>"
    html += "<span class='im'><table style='border:none;border-collapse:collapse'>"
    html += "<colgroup><col width='186'><col width='254'></colgroup><tbody><tr style='height:82.206pt'>"
    html += "<td style='vertical-align:top;padding:5pt;overflow:hidden'>"
    html += "<img src='cid:signature_image' alt='Assinatura' style='max-width:186px;height:auto;'></td>"
    html += "<td style='vertical-align:top;padding:5pt;overflow:hidden'>"
    html += "<p style='line-height:1.2;margin-top:0pt;margin-bottom:0pt'><span style='font-size:11pt;font-family:Arial,sans-serif;color:rgb(0,172,254);background-color:transparent;font-weight:700;vertical-align:baseline'><br></span></p>"
    html += "<p style='line-height:1.2;margin-top:0pt;margin-bottom:0pt'><span style='font-size:11pt;font-family:Arial,sans-serif;color:rgb(0,172,254);background-color:transparent;font-weight:700;vertical-align:baseline'>Carolina Ferreirinha&nbsp;</span></p><br>"
    html += "<p style='line-height:1.2;margin-top:0pt;margin-bottom:0pt'><span style='font-size:11pt;font-family:Arial,sans-serif;color:rgb(102,102,102);background-color:transparent;font-weight:700;vertical-align:baseline'>Diretora de Operações</span></p>"
    html += "<p style='line-height:1.2;margin-top:0pt;margin-bottom:0pt'><span style='font-size:9pt;font-family:Arial,sans-serif;color:rgb(102,102,102);background-color:transparent;vertical-align:baseline'>+351 913 522 185</span></p>"
    html += "<p style='line-height:1.2;margin-top:0pt;margin-bottom:0pt'><span style='background-color:transparent;color:rgb(102,102,102);font-family:Arial,sans-serif;font-size:8pt'>RNAVT 11763</span></p></td></tr></tbody></table></span>"
    html += "</p></body></html>"
    return html

def read_csv_report(csv_file):
    """Ler relatório CSV com as senhas"""
    log(f"Lendo relatório: {csv_file}")
    
    if not os.path.exists(csv_file):
        log(f"❌ Arquivo não encontrado: {csv_file}")
        return []
    
    users = []
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('success', '').lower() == 'true':
                    users.append({
                        'email': row.get('email', ''),
                        'name': row.get('name', '').strip() or row.get('email', '').split('@')[0],
                        'password': row.get('new_password', '')
                    })
                else:
                    log(f"Ignorando {row.get('email', '')} - reset falhou")
        
        log(f"Usuários para envio: {len(users)}")
        return users
        
    except Exception as e:
        log(f"❌ Erro ao ler CSV: {e}")
        return []

def create_smtp_connection():
    """Criar conexão SMTP"""
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        return server
    except Exception as e:
        log(f"✗ Erro ao conectar ao SMTP: {e}")
        return None

def send_email(server, user_data, signature_path):
    """Enviar email para um usuário usando conexão SMTP existente"""
    email = user_data['email']
    name = user_data['name']
    password = user_data['password']
    
    if DRY_RUN:
        log(f"[DRY-RUN] Email seria enviado para {email} ({name})")
        return True
    
    try:
        # Criar mensagem
        msg = MIMEMultipart('related')
        msg['Subject'] = SUBJECT
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg['To'] = email
        
        # Criar parte alternativa para texto/HTML
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        
        # Texto simples
        text_content = get_email_template().format(
            name=name,
            email=email,
            password=password
        )
        
        # HTML
        html_content = get_html_email_template().format(
            name=name,
            email=email,
            password=password
        )
        
        # Anexar conteúdos
        msg_alternative.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        # Anexar imagem da assinatura
        if os.path.exists(signature_path):
            with open(signature_path, 'rb') as img_file:
                img = MIMEImage(img_file.read())
                img.add_header('Content-ID', '<signature_image>')
                img.add_header('Content-Disposition', 'inline', filename='signature.png')
                msg.attach(img)
        
        # Enviar usando conexão existente
        server.send_message(msg)
        
        log(f"✓ Email enviado para {email} ({name})")
        return True
        
    except Exception as e:
        log(f"✗ Erro ao enviar email para {email}: {e}")
        return False

def main():
    """Função principal"""
    log("========================================")
    log("  ENVIO DE EMAILS - NOVAS SENHAS")
    log("========================================")
    log(f"Modo: {'DRY-RUN (teste)' if DRY_RUN else 'PRODUÇÃO'}")
    log(f"Arquivo CSV: {CSV_FILE}")
    log(f"SMTP: {SMTP_SERVER}:{SMTP_PORT}")
    log(f"De: {FROM_NAME} <{FROM_EMAIL}>")
    log("")
    
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        log("❌ Erro: SMTP_USERNAME e SMTP_PASSWORD devem ser configurados")
        return
    
    if not DRY_RUN:
        log("⚠️  ATENÇÃO: Modo PRODUÇÃO ativo!")
        log("⚠️  Os emails serão realmente enviados!")
        log("")
        confirm = input("Continuar? (digite 'SIM' para confirmar): ")
        if confirm != "SIM":
            log("Operação cancelada pelo usuário")
            return
    
    # Ler dados do CSV
    users = read_csv_report(CSV_FILE)
    if not users:
        log("❌ Nenhum usuário encontrado para envio")
        return
    
    log(f"Enviando emails para {len(users)} usuários...")
    log("")
    
    # Caminho da assinatura
    signature_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'image.png')
    if not os.path.exists(signature_path):
        log(f"⚠️  Imagem de assinatura não encontrada: {signature_path}")
    
    # Enviar emails com reconexão automática
    success_count = 0
    error_count = 0
    server = None
    emails_sent_in_session = 0
    MAX_EMAILS_PER_SESSION = 50  # Reconectar a cada 50 emails
    
    for i, user in enumerate(users, 1):
        log(f"[{i}/{len(users)}] Enviando para: {user['email']} ({user['name']})")
        
        # Criar conexão se necessário
        if server is None or emails_sent_in_session >= MAX_EMAILS_PER_SESSION:
            if server:
                try:
                    server.quit()
                    log("🔄 Reconectando ao servidor SMTP...")
                except:
                    pass
            
            server = create_smtp_connection()
            if not server:
                log("❌ Não foi possível conectar ao servidor SMTP")
                error_count += len(users) - i + 1
                break
            emails_sent_in_session = 0
        
        # Tentar enviar com retry
        max_retries = 3
        sent = False
        
        for attempt in range(max_retries):
            try:
                if send_email(server, user, signature_path):
                    success_count += 1
                    emails_sent_in_session += 1
                    sent = True
                    break
            except Exception as e:
                log(f"⚠️  Tentativa {attempt + 1}/{max_retries} falhou: {e}")
                # Reconectar e tentar novamente
                try:
                    server.quit()
                except:
                    pass
                server = create_smtp_connection()
                if not server:
                    break
                emails_sent_in_session = 0
        
        if not sent:
            error_count += 1
    
    # Fechar conexão
    if server:
        try:
            server.quit()
        except:
            pass
    
    # Relatório final
    log("")
    log("========================================")
    log("  RELATÓRIO FINAL")
    log("========================================")
    log(f"Total processado: {len(users)}")
    log(f"Emails enviados: {success_count}")
    log(f"Erros: {error_count}")
    
    if not DRY_RUN and success_count > 0:
        log("")
        log("✅ Emails enviados com sucesso!")
        log("📧 Os clientes receberam as novas senhas")

if __name__ == "__main__":
    main()
