import os
import time
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)

# Rota simples para o Render entender que o serviço está vivo (Health Check)
@app.route('/')
def health_check():
    return "Bot TJSP ativo e rodando!", 200

def iniciar_driver():
    options = Options()
    
    # --- CONFIGURAÇÕES ESSENCIAIS PARA RODAR HEADLESS NA NUVEM ---
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # --- MASCARAMENTO PARA O TJSP NÃO BLOQUEAR ---
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
        
        # Aumentamos o tempo limite para 30 segundos devido à latência da nuvem
        wait = WebDriverWait(driver, 30)

        # LINK DO SEU SISTEMA DE CHAMADOS DO TJSP
        url_tjsp = "https://seu-link-de-login-do-tjsp.jus.br" 
        driver.get(url_tjsp)

        print("⏳ Aguardando a tela de autenticação do TJSP...")
        
        # ⚠️ AJUSTE OS LOCATORS (IDs ou XPaths) CONFORME A PÁGINA REAL DO TJSP
        # Exemplo: Se o campo do usuário for um <input id="username">
        campo_usuario = wait.until(
            EC.presence_of_element_located((By.NAME, "username"))  # ou By.ID
        )
        campo_senha = driver.find_element(By.NAME, "password")    # ou By.ID
        
        campo_usuario.send_keys(usuario)
        campo_senha.send_keys(senha)

        # Clica no botão de login (Ajuste o seletor se necessário)
        btn_login = driver.find_element(By.XPATH, "//button[@type='submit']")
        btn_login.click()

        print("⏳ Aguardando carregamento dos chamados...")
        
        # Espera algum elemento da tela inicial pós-login carregar para confirmar o sucesso
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print("✅ Login efetuado com sucesso!")

        # --- SEU CÓDIGO DE RASPAGEM / MONITORAMENTO AQUI ---
        
    except Exception as e:
        print(f"❌ Ocorreu um erro durante a execução: {e}")
        if driver:
            print("Page Source/Título no momento do erro:", driver.title)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    # Em threads/Background ou direto no start da API
    import threading
    bot_thread = threading.Thread(target=executar_bot)
    bot_thread.start()

    # Inicia o servidor Web na porta definida pelo Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)