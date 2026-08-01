import os
import time
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
# ENVIAR MENSAGEM VIA TELEGRAM
# ------------------------------------------------------------------
def enviar_telegram(mensagem):
    # Usa a variável TELEGRAM_BOT_TOKEN
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8577087976:AAExdFwn6uNuo6_-9GH4erNgAK0gDFIb9m8")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "8422993986")

    if not token or not chat_id:
        print("⚠️ TELEGRAM: Token ou Chat ID não configurados.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": "HTML"
    }
    
    try:
        resposta = requests.post(url, json=payload, timeout=10)
        if resposta.status_code == 200:
            print("📱 Telegram: Notificação enviada com sucesso!")
            return True
        else:
            print(f"❌ Telegram erro {resposta.status_code}: {resposta.text}")
            return False
    except Exception as e:
        print(f"❌ Falha de conexão com Telegram: {e}")
        return False

# ------------------------------------------------------------------
# ENVIAR MENSAGEM VIA ULTRAMSG (WHATSAPP)
# ------------------------------------------------------------------
def enviar_whatsapp(mensagem):
    instance_id = os.getenv("ULTRAMSG_INSTANCE_ID", "instance186848")
    token = os.getenv("ULTRAMSG_TOKEN", "zwrh8r6js03a4yef")
    destino = os.getenv("ULTRAMSG_DESTINO", "120363410690262545@g.us")

    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    payload = {
        "token": token,
        "to": destino,
        "body": mensagem
    }
    headers = {'content-type': 'application/x-www-form-urlencoded'}

    try:
        resposta = requests.post(url, data=payload, headers=headers, timeout=10)
        if resposta.status_code == 200:
            print("🟢 WhatsApp (UltraMsg): Notificação enviada com sucesso!")
            return True
        else:
            print(f"❌ WhatsApp erro {resposta.status_code}: {resposta.text}")
            return False
    except Exception as e:
        print(f"❌ Falha de conexão com UltraMsg: {e}")
        return False

# Função auxiliar para notificar em ambos os canais
def notificar_todos(mensagem_html, mensagem_texto):
    enviar_telegram(mensagem_html)
    enviar_whatsapp(mensagem_texto)


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


def executar_bot():
    usuario = os.getenv("USUARIO_TJSP")
    senha = os.getenv("SENHA_TJSP")

    if not usuario or not senha:
        print("❌ ERRO: Variáveis USUARIO_TJSP e SENHA_TJSP não configuradas no Render!")
        return

    print("==================================================")
    print("🚀 INICIANDO MONITOR TJSP NA NUVEM")
    print("==================================================")
    
    driver = None
    try:
        driver = iniciar_driver()
        wait = WebDriverWait(driver, 35)

        url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
        driver.get(url_tjsp)

        print("⏳ Aguardando a tela de autenticação do TJSP...")

        # ETAPA 1: USUÁRIO
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

        # ETAPA 2: SENHA
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

        # ETAPA 3: PÓS-LOGIN
        print("⏳ Processando autenticação e carregando chamados...")
        time.sleep(10)
        
        print("🎉 LOGIN EFETUADO COM SUCESSO!")
        
        # DISPARA AS NOTIFICAÇÕES
        msg_tg = "🤖 <b>Bot TJSP:</b> Login efetuado com sucesso no portal de suporte!"
        msg_wa = "🤖 Bot TJSP: Login efetuado com sucesso no portal de suporte!"
        notificar_todos(msg_tg, msg_wa)

        # --- SEU CÓDIGO DE RASPAGEM E EXTRAÇÃO DE CHAMADOS ENTRA AQUI ---

    except Exception as e:
        erro_msg = f"❌ Erro durante a execução do Bot TJSP: {e}"
        print(erro_msg)
        notificar_todos(
            f"⚠️ <b>Alerta Bot TJSP:</b> Ocorreu uma falha.\n<code>{e}</code>",
            f"⚠️ Alerta Bot TJSP: Ocorreu uma falha no monitoramento: {e}"
        )
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    import threading
    bot_thread = threading.Thread(target=executar_bot)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)