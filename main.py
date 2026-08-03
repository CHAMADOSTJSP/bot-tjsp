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

@app.route('/')
def health_check():
    return "Bot TJSP ativo e rodando sem falhas!", 200


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
# CONFIGURAÇÃO DO CHROME / CHROMIUM PARA RENDER (DOCKER)
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
# EXTRAÇÃO DE CHAMADOS
# ------------------------------------------------------------------
def extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=False):
    try:
        # Aguarda dynamicamente os elementos aparecerem (máx. 5 segs)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='row'] | //table//tbody/tr[not(ancestor::header)]")))
        except Exception:
            time.sleep(2)

        linhas = driver.find_elements(By.XPATH, "//div[@role='row'] | //table//tbody/tr[not(ancestor::header)]")
        chamados_encontrados = 0

        for linha in linhas:
            texto_linha = linha.text.strip()
            if not texto_linha or "Solicitado por" in texto_linha or "Tipo de Atendin" in texto_linha:
                continue

            colunas = linha.find_elements(By.XPATH, ".//div[@role='gridcell'] | .//td")

            chamado_id = None
            data_hora = "N/A"
            titulo = "Sem título"
            solicitante = "N/A"
            categoria = "Geral"

            if len(colunas) >= 4:
                raw_id = colunas[0].text.strip().replace("#", "")
                match = re.search(r'\d{6,10}', raw_id)
                if match:
                    chamado_id = match.group(0)
                else:
                    match_linha = re.search(r'\b\d{7,9}\b', texto_linha)
                    if match_linha:
                        chamado_id = match_linha.group(0)

                data_hora = colunas[1].text.strip() if len(colunas) > 1 else "N/A"
                titulo = colunas[2].text.strip() if len(colunas) > 2 else "Sem título"
                solicitante = colunas[3].text.strip() if len(colunas) > 3 else "N/A"
                
                if len(colunas) > 5:
                    categoria = colunas[5].text.strip()
            else:
                match_id = re.search(r'\b\d{7,9}\b', texto_linha)
                if match_id:
                    chamado_id = match_id.group(0)
                    partes = texto_linha.split("\n")
                    if len(partes) > 2:
                        titulo = partes[2]
                    else:
                        titulo = texto_linha[:100]

            if not chamado_id or chamado_id in chamados_notificados:
                continue

            chamados_notificados.add(chamado_id)
            chamados_encontrados += 1

            if primeira_execucao:
                continue

            # Detecta VIP
            is_vip = False
            try:
                html_linha = linha.get_attribute("innerHTML") or ""
                if "vip" in html_linha.lower() or "juiz" in solicitante.lower() or "desembargador" in solicitante.lower():
                    is_vip = True
            except Exception:
                pass

            link_chamado = f"https://suporte.tjsp.jus.br/saw/Requests/{chamado_id}"
            
            if is_vip:
                cabecalho_tg = "👑 <b>ALERTA VIP — CHAMADO PRIORITÁRIO!</b>"
                cabecalho_wa = "👑 *ALERTA VIP — CHAMADO PRIORITÁRIO!*"
                tag = "VIP ⚠️"
            else:
                cabecalho_tg = "🚨 <b>NOVO CHAMADO DETECTADO!</b>"
                cabecalho_wa = "🚨 *NOVO CHAMADO DETECTADO!*"
                tag = "Normal"

            msg_tg = (
                f"{cabecalho_tg}\n\n"
                f"📌 <b>ID:</b> #{html.escape(chamado_id)}\n"
                f"🏷️ <b>Tag:</b> {tag}\n"
                f"📂 <b>Categoria:</b> {html.escape(categoria)}\n"
                f"📝 <b>Resumo:</b> {html.escape(titulo)}\n"
                f"👤 <b>Solicitante:</b> {html.escape(solicitante)}\n"
                f"⏰ <b>Horário:</b> {html.escape(data_hora)}\n\n"
                f"🔗 {link_chamado}"
            )

            msg_wa = (
                f"{cabecalho_wa}\n\n"
                f"📌 *ID:* #{chamado_id}\n"
                f"🏷️ *Tag:* {tag}\n"
                f"📂 *Categoria:* {categoria}\n"
                f"📝 *Resumo:* {titulo}\n"
                f"👤 *Solicitante:* {solicitante}\n"
                f"⏰ *Horário:* {data_hora}\n\n"
                f"🔗 {link_chamado}"
            )

            print(f"⚡ [INSTANTÂNEO] Notificando chamado #{chamado_id} (VIP: {is_vip})...", flush=True)
            notificar_todos(msg_tg, msg_wa)
            time.sleep(1)

        if primeira_execucao:
            print(f"📦 Mapeamento inicial concluído: {len(chamados_notificados)} chamados antigos mapeados.", flush=True)

    except Exception as e:
        print(f"⚠️ Erro ao tentar extrair chamados da tela: {e}", flush=True)


# ------------------------------------------------------------------
# LOOP PRINCIPAL DO ROBÔ
# ------------------------------------------------------------------
def executar_bot():
    usuario = os.getenv("USUARIO_TJSP")
    senha = os.getenv("SENHA_TJSP")

    if not usuario or not senha:
        print("❌ ERRO: Variáveis USUARIO_TJSP e SENHA_TJSP não configuradas!", flush=True)
        return

    print("==================================================", flush=True)
    print("🚀 INICIANDO MONITOR TJSP", flush=True)
    print("==================================================", flush=True)
    
    chamados_notificados = set()
    mensagem_inicial_enviada = False

    while True:
        if not dentro_do_expediente():
            print("🌙 Fora do expediente (09h-17h). Aguardando 15 minutos...", flush=True)
            time.sleep(900)
            continue

        driver = None
        try:
            driver = iniciar_driver()
            wait = WebDriverWait(driver, 20)

            url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
            driver.get(url_tjsp)

            # Processo de Login Seguro
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

            except Exception as e_login:
                print(f"ℹ️ Etapa de login concluída ou ignorada: {e_login}", flush=True)

            time.sleep(4)
            print("🎉 LOGIN EFETUADO COM SUCESSO!", flush=True)

            if not mensagem_inicial_enviada:
                msg_tg = "🤖 <b>Bot TJSP:</b> Conectado com sucesso!\n<b>Status:</b> Monitorando chamados..."
                msg_wa = "🤖 Bot TJSP: Conectado com sucesso!\nStatus: Monitorando chamados..."
                notificar_todos(msg_tg, msg_wa)
                mensagem_inicial_enviada = True

            extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=True)

            INTERVALO_CHECAGEM = 15  # Checagem ultra-rápida (15 segundos)
            iteraçoes = 0

            # Reinicia a sessão após 120 iterações (~30 mins) para manter o container leve na Render
            while iteraçoes < 120:
                time.sleep(INTERVALO_CHECAGEM)
                
                if not dentro_do_expediente():
                    print("🌙 Expediente encerrado.", flush=True)
                    break

                driver.refresh()

                elementos_login = driver.find_elements(By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']")
                if "login" in driver.current_url.lower() or len(elementos_login) > 0:
                    print("⚠️ Sessão expirada! Reiniciando login...", flush=True)
                    break

                extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=False)
                iteraçoes += 1

        except Exception as e:
            print(f"❌ Erro temporário: {e}. Reiniciando sessão em 10 segundos...", flush=True)
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
    app.run(host="0.0.0.0", port=port)