import os
import time
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)

# Rota de verificação de saúde para o Render manter o serviço ativo
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
        
        # Tempo limite aumentado para latência na nuvem
        wait = WebDriverWait(driver, 30)

        # URL ATUALIZADA DO SISTEMA DE SUPORTE DO TJSP
        url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
        driver.get(url_tjsp)

        print("⏳ Aguardando a tela de autenticação do TJSP...")
        
        # ⚠️ AJUSTE OS LOCATORS (IDs ou XPaths) CONFORME O FORMULÁRIO REAL DO TJSP
        # Exemplo: busca pelos campos de entrada
        campo_usuario = wait.until(
            EC.presence_of_element_located((By.NAME, "username"))  # Ou By.ID se for id="username"
        )
        campo_senha = driver.find_element(By.NAME, "password")    # Ou By.ID se for id="password"
        
        campo_usuario.send_keys(usuario)
        campo_senha.send_keys(senha)

        # Clica no botão de login
        btn_login = driver.find_element(By.XPATH, "//button[@type='submit']")
        btn_login.click()

        print("⏳ Aguardando carregamento dos chamados...")
        
        # Espera a página carregar após o login
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print("✅ Login efetuado com sucesso!")

        # --- SEU CÓDIGO DE LÓGICA/MONITORAMENTO DOS CHAMADOS AQUI ---
        
    except Exception as e:
        print(f"❌ Ocorreu um erro durante a execução: {e}")
        if driver:
            print("Título da página no momento do erro:", driver.title)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    import threading
    bot_thread = threading.Thread(target=executar_bot)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)