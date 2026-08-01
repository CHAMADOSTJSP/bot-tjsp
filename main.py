import os
import time
import threading
import html
import requests
from datetime import datetime, timezone, timedelta
import holidays
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot TJSP ativo e rodando!", 200


# ------------------------------------------------------------------
# VALIDAÇÃO DE HORÁRIO E EXPEDIENTE (09:00 às 17:00 - Horário de Brasília)
# ------------------------------------------------------------------
def dentro_do_expediente():
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br)
    
    # 1. Checa Fim de Semana (5 = Sábado, 6 = Domingo)
    if agora.weekday() in [5, 6]:
        return False
        
    # 2. Checa Horário (Entre 09:00 e 17:00)
    if agora.hour < 9 or agora.hour >= 17:
        return False
        
    # 3. Checa Feriados em SP
    try:
        feriados_sp = holidays.BR(state='SP', years=agora.year)
        if agora.date() in feriados_sp:
            return False
    except Exception as e:
        print(f"⚠️ Alerta ao verificar feriados: {e}", flush=True)

    return True


# ------------------------------------------------------------------
# CANAIS DE NOTIFICAÇÃO
# ------------------------------------------------------------------
def enviar_telegram(mensagem):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("⚠️ Telegram não configurado em variáveis de ambiente.", flush=True)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Falha Telegram: {e}", flush=True)
    return False


def enviar_whatsapp(mensagem):
    instance_id = os.getenv("ULTRAMSG_INSTANCE_ID")
    token = os.getenv("ULTRAMSG_TOKEN")
    destino = os.getenv("ULTRAMSG_DESTINO")

    if not instance_id or not token or not destino:
        print("⚠️ UltraMsg não configurado em variáveis de ambiente.", flush=True)
        return False

    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    payload = {"token": token, "to": destino, "body": mensagem}
    headers = {'content-type': 'application/x-www-form-urlencoded'}

    try:
        res = requests.post(url, data=payload, headers=headers, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Falha UltraMsg: {e}", flush=True)
    return False


def notificar_todos(msg_html, msg_texto):
    enviar_telegram(msg_html)
    enviar_whatsapp(msg_texto)


# ------------------------------------------------------------------
# CONFIGURAÇÃO DO CHROME
# ------------------------------------------------------------------
def iniciar_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(options=options)


# ------------------------------------------------------------------
# LÓGICA DE EXTRAÇÃO DE CHAMADOS
# ------------------------------------------------------------------
def extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=False):
    print("🔍 Buscando chamados na tela...", flush=True)
    
    try:
        time.sleep(5)
        
        elementos_chamados = driver.find_elements(
            By.XPATH, 
            "//tr[contains(@class, 'grid-row') or contains(@class, 'row')] | //div[contains(@class, 'request-card') or contains(@class, 'item')]"
        )

        if not elementos_chamados:
            elementos_chamados = driver.find_elements(By.XPATH, "//table//tbody/tr")

        chamados_encontrados = 0

        for idx, item in enumerate(elementos_chamados):
            texto_completo = item.text.strip()
            if not texto_completo:
                continue

            id_chamado = f"chamado_{hash(texto_completo)}"

            if id_chamado not in chamados_notificados:
                chamados_notificados.add(id_chamado)
                chamados_encontrados += 1

                if primeira_execucao:
                    continue

                # Trata caracteres especiais para não quebrar a tag HTML do Telegram
                texto_escapado = html.escape(texto_completo[:300])

                msg_tg = f"🚨 <b>NOVO CHAMADO TJSP DETECTADO!</b>\n\n<code>{texto_escapado}</code>"
                msg_wa = f"🚨 *NOVO CHAMADO TJSP DETECTADO!*\n\n{texto_completo[:300]}"
                
                print(f"📌 Notificando novo chamado #{chamados_encontrados}...", flush=True)
                notificar_todos(msg_tg, msg_wa)

        if primeira_execucao:
            print(f"📦 Mapeamento inicial concluído: {len(chamados_notificados)} chamados antigos ignorados.", flush=True)
        elif chamados_encontrados == 0:
            print("ℹ️ Nenhum chamado novo detectado nesta verificação.", flush=True)
        else:
            print(f"✅ Total de {chamados_encontrados} novos chamados notificados!", flush=True)

    except Exception as e:
        print(f"⚠️ Erro ao tentar extrair chamados da tela: {e}", flush=True)


# ------------------------------------------------------------------
# LÓGICA DO ROBÔ
# ------------------------------------------------------------------
def executar_bot():
    usuario = os.getenv("USUARIO_TJSP")
    senha = os.getenv("SENHA_TJSP")

    if not usuario or not senha:
        print("❌ ERRO: Variáveis USUARIO_TJSP e SENHA_TJSP não configuradas no Render!", flush=True)
        return

    print("==================================================", flush=True)
    print("🚀 INICIANDO MONITOR TJSP NA NUVEM", flush=True)
    print("==================================================", flush=True)
    
    chamados_notificados = set()
    mensagem_inicial_enviada = False

    while True:
        # Se estiver fora do expediente, pausa a verificação sem abrir o Selenium
        if not dentro_do_expediente():
            print("🌙 Fora do expediente (09h-17h, fim de semana ou feriado). Aguardando 15 minutos...", flush=True)
            time.sleep(900)
            continue

        driver = None
        try:
            driver = iniciar_driver()
            wait = WebDriverWait(driver, 35)

            url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
            driver.get(url_tjsp)

            print("⏳ Acessando URL inicial...", flush=True)

            # ETAPA DE LOGIN
            try:
                campo_usuario = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']"))
                )
                campo_usuario.clear()
                campo_usuario.send_keys(usuario)

                try:
                    btn_proximo = driver.find_element(By.XPATH, "//button[contains(.,'Próximo') or contains(.,'Proximo')]")
                    btn_proximo.click()
                except:
                    campo_usuario.send_keys(Keys.RETURN)

                campo_senha = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Senha' or @type='password']"))
                )
                time.sleep(1)
                campo_senha.clear()
                campo_senha.send_keys(senha)

                try:
                    btn_entrar = driver.find_element(By.XPATH, "//button[contains(.,'Entrar')]")
                    btn_entrar.click()
                except:
                    campo_senha.send_keys(Keys.RETURN)

            except Exception as e_login:
                print(f"ℹ️ Login em etapa única ou sessão reutilizada: {e_login}", flush=True)

            time.sleep(8)
            print("🎉 LOGIN EFETUADO COM SUCESSO!", flush=True)

            if not mensagem_inicial_enviada:
                msg_tg = "🤖 <b>Bot TJSP:</b> Login efetuado com sucesso!\n<b>Status:</b> Mapeando chamados existentes..."
                msg_wa = "🤖 Bot TJSP: Login efetuado com sucesso!\nStatus: Mapeando chamados existentes..."
                notificar_todos(msg_tg, msg_wa)
                mensagem_inicial_enviada = True

            # MAPEAMENTO INICIAL
            extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=True)

            # LOOP DE MONITORAMENTO INTERNO (Até 2 horas antes de recriar a sessão)
            INTERVALO_CHECAGEM = 300  # 5 minutos
            iterações = 0

            while iterações < 24:  # 24 * 5 min = 2 horas
                time.sleep(INTERVALO_CHECAGEM)
                
                if not dentro_do_expediente():
                    print("🌙 Expediente encerrado. Encerrando sessão do navegador...", flush=True)
                    break

                print("🔄 Recarregando a página de chamados...", flush=True)
                driver.refresh()
                time.sleep(3)

                # Checagem de perda de sessão
                elementos_login = driver.find_elements(By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']")
                if "login" in driver.current_url.lower() or len(elementos_login) > 0:
                    print("⚠️ Sessão expirada! Reiniciando ciclo de login...", flush=True)
                    break

                extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=False)
                iterações += 1

        except Exception as e:
            print(f"❌ Erro crítico no robô: {e}. Reiniciando em 60 segundos...", flush=True)
            time.sleep(60)
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass


# ------------------------------------------------------------------
# INICIALIZAÇÃO DA APLICAÇÃO
# ------------------------------------------------------------------
if __name__ == "__main__":
    try:
        bot_thread = threading.Thread(target=executar_bot, daemon=True)
        bot_thread.start()

        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)
    except Exception as err:
        print(f"❌ Falha crítica: {err}", flush=True)