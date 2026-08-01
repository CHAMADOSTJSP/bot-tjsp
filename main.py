import os
import time
import requests
from threading import Thread
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot TJSP ativo e rodando!", 200

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")

chamados_notificados = set()
primeira_execucao = True

def enviar_notificacao_telegram(mensagem):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[ERRO TELEGRAM] Falha ao enviar mensagem: {e}")

def enviar_notificacao_whatsapp(mensagem):
    if not WHATSAPP_API_URL:
        return
    try:
        payload = {"message": mensagem}
        requests.post(WHATSAPP_API_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"[ERRO WHATSAPP] Falha ao enviar mensagem: {e}")

def formatar_mensagem_chamado(chamado):
    if chamado['is_vip']:
        header = "👑 *[ALERTA VIP] NOVO CHAMADO PRIORITÁRIO!*"
        tag_vip = "\n🏷️ *Prioridade:* VIP ⭐"
    else:
        header = "🚨 *NOVO CHAMADO ENCONTRADO!*"
        tag_vip = ""

    msg = (
        f"{header}\n\n"
        f"📌 *ID:* #{chamado['id']}{tag_vip}\n"
        f"📝 *Título:* {chamado['titulo']}\n"
        f"👤 *Solicitante:* {chamado['solicitante']}\n"
        f"⏰ *Data/Hora:* {chamado['data']}\n"
        f"🏢 *Local:* {chamado['local']}\n"
        f"🔄 *Status:* {chamado['status']}\n\n"
        f"🔗 https://suporte.tjsp.jus.br/saw/Requests/{chamado['id']}"
    )
    return msg

def monitorar_chamados_tjsp():
    global primeira_execucao, chamados_notificados
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Adiciona User-Agent de navegador real para evitar bloqueios/demora de renderização
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print("[INFO] Iniciando sessão Selenium no Portal TJSP...")
        driver.get("https://suporte.tjsp.jus.br/saw/Requests")
        time.sleep(15)  # Tempo para carregamento completo da interface

        while True:
            try:
                # Aguarda carregar qualquer linha ou elemento de tabela disponível
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, "//tr | //div[@role='row']"))
                )
                
                # Busca genérica por linhas para manter compatibilidade total
                linhas = driver.find_elements(By.XPATH, "//table/tbody/tr | //div[@role='row']")
                novos_chamados_count = 0

                for linha in linhas:
                    colunas = linha.find_elements(By.XPATH, ".//td | .//div[@role='gridcell']")
                    if len(colunas) < 4:
                        continue
                    
                    chamado_id = colunas[0].text.strip()
                    data_hora = colunas[1].text.strip()
                    titulo = colunas[2].text.strip()
                    
                    solicitante_celula = colunas[3]
                    solicitante_nome = solicitante_celula.text.strip()
                    
                    # Verificação de Tag VIP super tolerante a falhas
                    is_vip = False
                    try:
                        html_celula = solicitante_celula.get_attribute("innerHTML") or ""
                        elementos_vip = solicitante_celula.find_elements(By.XPATH, ".//*[contains(@class, 'badge') or contains(@class, 'vip') or contains(@style, 'yellow')]")
                        if elementos_vip or "vip" in html_celula.lower():
                            is_vip = True
                    except Exception:
                        pass

                    local_divulgacao = colunas[6].text.strip() if len(colunas) > 6 else "N/A"
                    status_op = colunas[7].text.strip() if len(colunas) > 7 else "N/A"

                    # Validação: só processa se o ID for um número/texto válido
                    if chamado_id and len(chamado_id) >= 5 and chamado_id not in chamados_notificados:
                        chamados_notificados.add(chamado_id)
                        
                        if not primeira_execucao:
                            dados_chamado = {
                                "id": chamado_id,
                                "data": data_hora,
                                "titulo": titulo,
                                "solicitante": solicitante_nome,
                                "is_vip": is_vip,
                                "local": local_divulgacao,
                                "status": status_op
                            }
                            
                            mensagem = formatar_mensagem_chamado(dados_chamado)
                            enviar_notificacao_telegram(mensagem)
                            enviar_notificacao_whatsapp(mensagem)
                            novos_chamados_count += 1
                            print(f"[ALERTA] Novo chamado identificado: #{chamado_id} (VIP: {is_vip})")

                if primeira_execucao:
                    print(f"[INFO] Carga inicial concluída. {len(chamados_notificados)} chamados mapeados.")
                    enviar_notificacao_telegram("🤖 *Bot TJSP Conectado!* O monitoramento de chamados normais e VIPs está ativo.")
                    primeira_execucao = False
                elif novos_chamados_count > 0:
                    print(f"[INFO] {novos_chamados_count} novos chamados notificados com sucesso.")

                time.sleep(300)
                driver.refresh()

            except Exception as e_loop:
                print(f"[ERRO LOOP] Falha na varredura: {e_loop}")
                time.sleep(60)
                try:
                    driver.refresh()
                except Exception:
                    pass

    except Exception as e_main:
        print(f"[ERRO CRÍTICO] Falha geral no Selenium: {e_main}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def rodar_bot_thread():
    while True:
        try:
            monitorar_chamados_tjsp()
        except Exception as e:
            print(f"[RESTART] Reiniciando instância em 30 segundos após erro: {e}")
            time.sleep(30)

if __name__ == "__main__":
    thread_bot = Thread(target=rodar_bot_thread)
    thread_bot.daemon = True
    thread_bot.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)