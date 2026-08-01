import os
import time
import threading
import requests
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
# CANAIS DE NOTIFICAÇÃO
# ------------------------------------------------------------------
def enviar_telegram(mensagem):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8577087976:AAExdFwn6uNuo6_-9GH4erNgAK0gDFIb9m8")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "8422993986")

    if not token or not chat_id:
        print("⚠️ TELEGRAM: Token ou Chat ID ausente.", flush=True)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("📱 Telegram: Enviado!", flush=True)
            return True
        print(f"❌ Telegram Erro {res.status_code}: {res.text}", flush=True)
    except Exception as e:
        print(f"❌ Falha Telegram: {e}", flush=True)
    return False


def enviar_whatsapp(mensagem):
    instance_id = os.getenv("ULTRAMSG_INSTANCE_ID", "instance186848")
    token = os.getenv("ULTRAMSG_TOKEN", "zwrh8r6js03a4yef")
    destino = os.getenv("ULTRAMSG_DESTINO", "120363410690262545@g.us")

    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    payload = {"token": token, "to": destino, "body": mensagem}
    headers = {'content-type': 'application/x-www-form-urlencoded'}

    try:
        res = requests.post(url, data=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            print("🟢 WhatsApp: Enviado!", flush=True)
            return True
        print(f"❌ WhatsApp Erro {res.status_code}: {res.text}", flush=True)
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
    
    driver = None
    try:
        driver = iniciar_driver()
        wait = WebDriverWait(driver, 35)

        url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
        driver.get(url_tjsp)

        print(f"⏳ Acessando URL inicial...", flush=True)

        # ETAPA 1: USUÁRIO
        try:
            campo_usuario = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']"))
            )
            print("👤 Preenchendo nome de usuário...", flush=True)
            campo_usuario.clear()
            campo_usuario.send_keys(usuario)

            try:
                btn_proximo = driver.find_element(By.XPATH, "//button[contains(.,'Próximo') or contains(.,'Proximo')]")
                btn_proximo.click()
            except:
                campo_usuario.send_keys(Keys.RETURN)

            # ETAPA 2: SENHA
            print("🔑 Aguardando campo de senha...", flush=True)
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

        # ETAPA 3: CONFIRMAÇÃO
        print("⏳ Aguardando carregamento do painel de chamados...", flush=True)
        time.sleep(8)
        
        url_atual = driver.current_url
        print("🎉 LOGIN EFETUADO COM SUCESSO!", flush=True)
        print(f"📌 URL Atual: {url_atual}", flush=True)

        msg_tg = f"🤖 <b>Bot TJSP:</b> Login efetuado com sucesso!\n<b>Página:</b> {url_atual}"
        msg_wa = f"🤖 Bot TJSP: Login efetuado com sucesso!\nPágina: {url_atual}"
        notificar_todos(msg_tg, msg_wa)

    except Exception as e:
        erro_msg = f"❌ Erro na execução: {e}"
        print(erro_msg, flush=True)
        notificar_todos(
            f"⚠️ <b>Alerta Bot TJSP:</b> Ocorreu uma falha.\n<code>{e}</code>",
            f"⚠️ Alerta Bot TJSP: Ocorreu uma falha no monitoramento: {e}"
        )
    finally:
        if driver:
            driver.quit()


# ------------------------------------------------------------------
# INICIALIZAÇÃO DA APLICAÇÃO
# ------------------------------------------------------------------
if __name__ == "__main__":
    try:
        # Inicia a thread do robô em background
        bot_thread = threading.Thread(target=executar_bot, daemon=True)
        bot_thread.start()

        # Inicia o servidor Web Flask na porta do Render
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)
    except Exception as err:
        print(f"❌ Falha crítica no arranque da aplicação: {err}", flush=True)