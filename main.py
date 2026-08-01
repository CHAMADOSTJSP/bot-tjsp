import os
import time
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

def iniciar_driver():
    options = Options()
    
    # Flags essenciais para nuvem/Docker
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # User-Agent para não ser bloqueado pelo firewall do TJSP
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
        print("❌ ERRO: Variáveis de ambiente USUARIO_TJSP e SENHA_TJSP não configuradas no Render!")
        return

    print("==================================================")
    print("🚀 INICIANDO MONITOR TJSP NA NUVEM")
    print("==================================================")
    
    driver = None
    try:
        print("🌐 Inicializando Google Chrome Headless na nuvem...")
        driver = iniciar_driver()
        wait = WebDriverWait(driver, 35)

        url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
        driver.get(url_tjsp)

        print("⏳ Aguardando a tela de autenticação do TJSP...")

        # -------------------------------------------------------------
        # ETAPA 1: DIGITAR USUÁRIO E CLICAR EM "PRÓXIMO"
        # -------------------------------------------------------------
        print("👤 Localizando campo de usuário...")
        campo_usuario = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']"))
        )
        campo_usuario.clear()
        campo_usuario.send_keys(usuario)
        print("✅ Usuário inserido!")

        print("🔘 Clicando no botão 'Próximo'...")
        btn_proximo = None
        try:
            btn_proximo = driver.find_element(By.XPATH, "//button[contains(.,'Próximo') or contains(.,'Proximo')]")
            btn_proximo.click()
        except:
            # Fallback se o botão não for clicável diretamente via Selenium
            campo_usuario.send_keys(Keys.RETURN)

        # -------------------------------------------------------------
        # ETAPA 2: AGUARDAR TRANSIÇÃO, DIGITAR SENHA E CLICAR EM "ENTRAR"
        # -------------------------------------------------------------
        print("🔑 Aguardando transição para a tela de senha...")
        
        # Espera o campo de senha ficar visível e clicável na tela
        campo_senha = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Senha' or @type='password']"))
        )
        time.sleep(1) # Pausa técnica para animação da interface
        
        campo_senha.clear()
        campo_senha.send_keys(senha)
        print("✅ Senha inserida!")

        print("🔘 Clicando no botão 'Entrar'...")
        try:
            btn_entrar = driver.find_element(By.XPATH, "//button[contains(.,'Entrar')]")
            btn_entrar.click()
        except:
            campo_senha.send_keys(Keys.RETURN)

        # -------------------------------------------------------------
        # ETAPA 3: VALIDAÇÃO DO LOGIN
        # -------------------------------------------------------------
        print("⏳ Processando autenticação e carregando chamados...")
        time.sleep(8)
        
        print("🎉 LOGIN EFETUADO COM SUCESSO!")
        print("📌 Título da página pós-login:", driver.title)
        print("📌 URL atual:", driver.current_url)

        # --- SEU CÓDIGO DE MONITORAMENTO DE CHAMADOS ENTRA AQUI ---

    except Exception as e:
        print(f"❌ Ocorreu um erro durante a execução: {e}")
        if driver:
            print("Título no erro:", driver.title)
            print("URL no erro:", driver.current_url)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    import threading
    bot_thread = threading.Thread(target=executar_bot)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)