import os
import time
import re
import html
import threading
import requests
from datetime import datetime, timezone, timedelta
import holidays
from flask import Flask
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

load_dotenv()

app = Flask(__name__)

# Controladores globais de estado
chamados_notificados = set()
primeira_varredura_global = True
mensagem_boas_vindas_enviada = False

@app.route('/')
def health_check():
    return "Bot TJSP ativo e monitorando chamados!", 200


# ------------------------------------------------------------------
# VALIDAÇÃO DE HORÁRIO E EXPEDIENTE
# ------------------------------------------------------------------
def dentro_do_expediente():
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br)
    
    # Fim de semana (5 = Sábado, 6 = Domingo)
    if agora.weekday() in [5, 6]:
        return False
        
    # Horário de atendimento (09:00 às 17:00)
    if agora.hour < 9 or agora.hour >= 17:
        return False
        
    # Feriados SP
    try:
        feriados_sp = holidays.BR(state='SP', years=agora.year)
        if agora.date() in feriados_sp:
            return False
    except Exception as e:
        print(f"⚠️ Alerta ao verificar feriados: {e}", flush=True)

    return True


# ------------------------------------------------------------------
# NOTIFICAÇÕES (TELEGRAM & WHATSAPP)
# ------------------------------------------------------------------
def enviar_telegram(mensagem):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("⚠️ Telegram não configurado nas variáveis de ambiente.", flush=True)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}
    
    try:
        res = requests.post(url, json=payload, timeout=8)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Falha Telegram: {e}", flush=True)
    return False


def enviar_whatsapp(mensagem):
    instance_id = os.getenv("ULTRAMSG_INSTANCE_ID")
    token = os.getenv("ULTRAMSG_TOKEN")
    destino = os.getenv("ULTRAMSG_DESTINO")

    if not instance_id or not token or not destino:
        print("⚠️ UltraMsg não configurado nas variáveis de ambiente.", flush=True)
        return False

    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    payload = {"token": token, "to": destino, "body": mensagem}
    headers = {'content-type': 'application/x-www-form-urlencoded'}

    try:
        res = requests.post(url, data=payload, headers=headers, timeout=8)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Falha UltraMsg: {e}", flush=True)
    return False


def notificar_todos(msg_html, msg_texto):
    enviar_telegram(msg_html)
    enviar_whatsapp(msg_texto)


# ------------------------------------------------------------------
# CONFIGURAÇÃO DO CHROME / CHROMIUM
# ------------------------------------------------------------------
def iniciar_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")

    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    return webdriver.Chrome(options=options)


# ------------------------------------------------------------------
# EXTRAÇÃO DE CHAMADOS ALINHADA AO PAINEL SMAX
# ------------------------------------------------------------------
def extrair_e_notificar_chamados(driver, wait, e_primeira_execucao=False):
    global chamados_notificados
    
    try:
        xpath_linhas = (
            "//div[@role='row' and not(ancestor::header)] | "
            "//table//tbody/tr[not(ancestor::header)]"
        )
        
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, xpath_linhas)))
            time.sleep(3)
        except Exception:
            print("⚠️ Tabela demorou para carregar ou está vazia.", flush=True)
            return

        linhas = driver.find_elements(By.XPATH, xpath_linhas)

        for linha in linhas:
            try:
                texto_linha = linha.text.strip()
                if not texto_linha or "Solicitado por" in texto_linha or "Tipo de Atendin" in texto_linha:
                    continue

                # Busca as células de dentro da linha atual
                colunas = linha.find_elements(By.XPATH, ".//div[@role='gridcell'] | .//td")
                
                # Extrai os textos limpos de cada coluna
                textos_colunas = [' '.join(col.text.strip().split()) for col in colunas if col.text.strip()]

                chamado_id = ""
                ems = ""
                titulo = ""
                solicitado_por = ""
                designado = ""  # Sempre mantido em branco conforme instruído
                tipo_atendimento = ""
                local_divulgacao = ""

                # Tenta extrair o ID numérico da primeira coluna/texto
                if textos_colunas:
                    match_id = re.search(r'\b\d{7,9}\b', textos_colunas[0])
                    if match_id:
                        chamado_id = match_id.group(0)

                if not chamado_id:
                    match_fallback = re.search(r'\b\d{7,9}\b', texto_linha)
                    if match_fallback:
                        chamado_id = match_fallback.group(0)

                if not chamado_id or chamado_id in chamados_notificados:
                    continue

                # Mapeamento seguro baseado na ordem das colunas no SMAX
                if len(textos_colunas) >= 6:
                    # Se houver checkbox, ajusta os deslocamentos
                    offset = 1 if not re.search(r'\d{7,9}', textos_colunas[0]) else 0
                    
                    chamado_id = re.search(r'\d{7,9}', textos_colunas[offset]).group(0) if re.search(r'\d{7,9}', textos_colunas[offset]) else chamado_id
                    ems = textos_colunas[offset + 1] if len(textos_colunas) > (offset + 1) else ""
                    titulo = textos_colunas[offset + 2] if len(textos_colunas) > (offset + 3) else ""
                    solicitado_por = textos_colunas[offset + 3] if len(textos_colunas) > (offset + 3) else ""
                    # Designado fica em branco intencionalmente
                    designado = ""
                    
                    # Tipo Atendimento e Local de divulgação
                    if len(textos_colunas) > (offset + 5):
                        tipo_atendimento = textos_colunas[offset + 5]
                    if len(textos_colunas) > (offset + 6):
                        local_divulgacao = textos_colunas[offset + 6]

                # Registra o ID para evitar notificações duplicadas
                chamados_notificados.add(chamado_id)

                # Se for a varredura inicial ao abrir o sistema, grava os chamados sem enviar notificação
                if e_primeira_execucao:
                    continue

                # NOTIFICAÇÃO DE NOVO CHAMADO ENCONTRADO
                link_chamado = f"https://suporte.tjsp.jus.br/saw/Requests/{chamado_id}"

                msg_tg = (
                    f"🚨 <b>NOVO CHAMADO DETECTADO!</b>\n\n"
                    f"📌 <b>ID:</b> {html.escape(chamado_id)}\n"
                    f"⏰ <b>Ems:</b> {html.escape(ems)}\n"
                    f"📝 <b>Título:</b> {html.escape(titulo)}\n"
                    f"👤 <b>Solicitado por:</b> {html.escape(solicitado_por)}\n"
                    f"👤 <b>Designado:</b> {html.escape(designado)}\n"
                    f"💻 <b>Tipo de Atendimento:</b> {html.escape(tipo_atendimento)}\n"
                    f"🏢 <b>Local de divulgação:</b> {html.escape(local_divulgacao)}\n\n"
                    f"🔗 {link_chamado}"
                )

                msg_wa = (
                    f"🚨 *NOVO CHAMADO DETECTADO!*\n\n"
                    f"📌 *ID:* {chamado_id}\n"
                    f"⏰ *Ems:* {ems}\n"
                    f"📝 *Título:* {titulo}\n"
                    f"👤 *Solicitado por:* {solicitado_por}\n"
                    f"👤 *Designado:* {designado}\n"
                    f"💻 *Tipo de Atendimento:* {tipo_atendimento}\n"
                    f"🏢 *Local de divulgação:* {local_divulgacao}\n\n"
                    f"🔗 {link_chamado}"
                )

                print(f"⚡ [NOVO CHAMADO] Disparando alerta do chamado #{chamado_id}...", flush=True)
                notificar_todos(msg_tg, msg_wa)
                time.sleep(1)

            except Exception as e_linha:
                print(f"⚠️ Erro ao processar linha da tabela: {e_linha}", flush=True)

        if e_primeira_execucao:
            print(f"📦 Mapeamento inicial concluído: {len(chamados_notificados)} chamados já existentes salvos.", flush=True)

    except Exception as e:
        print(f"⚠️ Erro ao tentar extrair chamados da tela: {e}", flush=True)


# ------------------------------------------------------------------
# LOOP PRINCIPAL DO ROBÔ
# ------------------------------------------------------------------
def executar_bot():
    global primeira_varredura_global, mensagem_boas_vindas_enviada
    
    usuario = os.getenv("USUARIO_TJSP")
    senha = os.getenv("SENHA_TJSP")

    if not usuario or not senha:
        print("❌ ERRO: Variáveis USUARIO_TJSP e SENHA_TJSP não configuradas!", flush=True)
        return

    # ENVIO ÚNICO DA MENSAGEM DE ABERTURA
    if not mensagem_boas_vindas_enviada:
        msg_tg = "🤖 <b>Bot TJSP ativo e realizando varredura</b>"
        msg_wa = "🤖 *Bot TJSP ativo e realizando varredura*"
        notificar_todos(msg_tg, msg_wa)
        mensagem_boas_vindas_enviada = True

    print("==================================================", flush=True)
    print("🚀 INICIANDO MONITOR TJSP", flush=True)
    print("==================================================", flush=True)

    while True:
        if not dentro_do_expediente():
            print("🌙 Fora do expediente (09h-17h). Aguardando 15 minutos...", flush=True)
            time.sleep(900)
            continue

        driver = None
        try:
            driver = iniciar_driver()
            wait = WebDriverWait(driver, 25)

            url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
            driver.get(url_tjsp)

            # Processo de Login
            try:
                campo_usuario = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']"))
                )
                campo_usuario.clear()
                campo_usuario.send_keys(usuario)

                try:
                    btn_proximo = driver.find_element(By.XPATH, "//button[contains(.,'Próximo') or contains(.,'Proximo')]")
                    btn_proximo.click()
                except Exception:
                    campo_usuario.send_keys(Keys.RETURN)

                campo_senha = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Senha' or @type='password']"))
                )
                time.sleep(0.5)
                campo_senha.clear()
                campo_senha.send_keys(senha)

                try:
                    btn_entrar = driver.find_element(By.XPATH, "//button[contains(.,'Entrar')]")
                    btn_entrar.click()
                except Exception:
                    campo_senha.send_keys(Keys.RETURN)

            except Exception:
                pass

            time.sleep(6)
            print("🎉 Sessão carregada no SMAX.", flush=True)

            # Mapeia todos os chamados existentes ao abrir o sistema (sem disparar mensagens)
            extrair_e_notificar_chamados(driver, wait, e_primeira_execucao=primeira_varredura_global)
            primeira_varredura_global = False

            INTERVALO_CHECAGEM = 15
            iteraçoes = 0

            while iteraçoes < 120:
                time.sleep(INTERVALO_CHECAGEM)
                
                if not dentro_do_expediente():
                    print("🌙 Expediente encerrado.", flush=True)
                    break

                driver.refresh()

                elementos_login = driver.find_elements(By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']")
                if "login" in driver.current_url.lower() or len(elementos_login) > 0:
                    print("⚠️ Sessão expirada! Recarregando login...", flush=True)
                    break

                # Notifica apenas se surgir um novo chamado
                extrair_e_notificar_chamados(driver, wait, e_primeira_execucao=False)
                iteraçoes += 1

        except Exception as e:
            print(f"❌ Erro na varredura: {e}. Reiniciando sessão em 10s...", flush=True)
            time.sleep(10)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


# ------------------------------------------------------------------
# INICIALIZAÇÃO DA APLICAÇÃO
# ------------------------------------------------------------------
if __name__ == "__main__":
    bot_thread = threading.Thread(target=executar_bot, daemon=True)
    bot_thread.start()
    print("🤖 Thread do bot iniciada com sucesso!", flush=True)

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)