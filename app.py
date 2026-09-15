import sys
import os
import traceback
import time
import datetime
import requests
from requests.exceptions import Timeout, RequestException
import urllib3
import json
import tempfile
import threading
from zoneinfo import ZoneInfo

# Garante suporte a UTF-8 no ambiente Linux do Render
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

try:
    import holidays
    from dotenv import load_dotenv
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception as e:
    print(f"\n❌ ERRO AO IMPORTAR BIBLIOTECAS: {e}")
    sys.exit(1)

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main():
    print("\n" + "="*50, flush=True)
    print("🔐 INICIALIZANDO MONITOR TJSP (RENDER.COM - BLINDADO & OTIMIZADO RAM)", flush=True)
    print("="*50, flush=True)

    USUARIO_TJSP = os.getenv("USUARIO_TJSP", "")
    SENHA_TJSP = os.getenv("SENHA_TJSP", "")

    if not USUARIO_TJSP or not SENHA_TJSP:
        print("⚠️ Credenciais não encontradas nas variáveis de ambiente do Render!", flush=True)
        sys.exit(1)

    print(f"👤 Usuário carregado com sucesso.", flush=True)
    print("="*50 + "\n", flush=True)

    # --- CONFIGURAÇÕES DE ENVIO ---
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "") 
    WHATSAPP_CHAT_ID = os.getenv("WHATSAPP_CHAT_ID", "120363410690262545@g.us")

    HORA_INICIO = datetime.datetime.strptime("09:00:00", "%H:%M:%S").time()
    HORA_FIM = datetime.datetime.strptime("17:05:00", "%H:%M:%S").time()
    FERIADOS_SP = holidays.BR(subdiv='SP')
    FUSO_BR = ZoneInfo("America/Sao_Paulo")

    ARQUIVO_HISTORICO = os.path.join(tempfile.gettempdir(), "tjsp_historico_chamados.json")

    def carregar_historico():
        if os.path.exists(ARQUIVO_HISTORICO):
            try:
                with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

    def salvar_historico(ids_set):
        try:
            with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
                json.dump(list(ids_set), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Erro ao salvar histórico: {e}", flush=True)

    def disparar_telegram(mensagem, max_retries=3):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("⚠️ Telegram não configurado nas variáveis de ambiente.", flush=True)
            return False
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
        
        for tentativa in range(max_retries):
            try:
                res = requests.post(url, json=payload, timeout=35, verify=False)
                if res.status_code == 200:
                    print("✈️ Alerta enviado com sucesso para o Telegram!", flush=True)
                    return True
                else:
                    print(f"⚠️ Falha Telegram: HTTP {res.status_code} (Tentativa {tentativa+1}/{max_retries})", flush=True)
            except Exception as e:
                print(f"❌ Erro de rede no Telegram: {e}", flush=True)
            time.sleep(3)
        return False

    def disparar_whatsapp_gratuito(mensagem):
        if not WHATSAPP_API_URL:
            return False
        
        payload = {
            "session": "default",
            "chatId": WHATSAPP_CHAT_ID,
            "text": mensagem
        }
        try:
            res = requests.post(WHATSAPP_API_URL, json=payload, timeout=30)
            if res.status_code == 200:
                print("📱 Alerta enviado para o WhatsApp com sucesso!", flush=True)
                return True
            else:
                print(f"⚠️ Falha ao enviar WhatsApp gratuito: HTTP {res.status_code}", flush=True)
        except Exception as e:
            print(f"❌ Erro na API de WhatsApp gratuita: {e}", flush=True)
        return False

    def enviar_alertas(mensagem):
        threading.Thread(target=disparar_telegram, args=(mensagem,), daemon=True).start()
        threading.Thread(target=disparar_whatsapp_gratuito, args=(mensagem,), daemon=True).start()

    def dentro_do_expediente():
        agora = datetime.datetime.now(FUSO_BR)
        if agora.weekday() >= 5:
            return False, "Fim de semana"
        if agora.date() in FERIADOS_SP:
            return False, f"Feriado ({FERIADOS_SP.get(agora.date())})"
        if not (HORA_INICIO <= agora.time() <= HORA_FIM):
            return False, f"Fora do expediente ({agora.strftime('%H:%M:%S')})"
        return True, "Em expediente"

    # --- CONFIGURAÇÃO OTIMIZADA PARA ECONOMIA DE RAM (PLANO FREE 512MB) ---
    print("🌐 Configurando Chrome Headless com baixo consumo de RAM...", flush=True)
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--no-zygote")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        print("⏳ Acessando a página de autenticação...", flush=True)
        driver.get("https://suporte.tjsp.jus.br/saw/Requests")

        try:
            user_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@name='username' or @id='username' or @type='text']")))
            user_input.clear()
            user_input.send_keys(USUARIO_TJSP)
            time.sleep(1)

            try:
                btn_proximo = driver.find_element(By.XPATH, "//button[contains(., 'Próximo') or contains(., 'Next')] | //input[@type='submit']")
                btn_proximo.click()
            except Exception:
                user_input.send_keys(Keys.RETURN)

            print("🔑 Usuário enviado. Aguardando campo da senha...", flush=True)
            time.sleep(2)

            pass_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password' or @name='password']")))
            pass_input.clear()
            pass_input.send_keys(SENHA_TJSP)
            time.sleep(1)

            try:
                btn_login = driver.find_element(By.XPATH, "//button[contains(., 'Entrar') or contains(., 'Login')] | //input[@type='submit']")
                btn_login.click()
            except Exception:
                pass_input.send_keys(Keys.RETURN)

            print("🚀 Login enviado! Aguardando montagem da sessão...", flush=True)
            time.sleep(6)
        except Exception:
            print("ℹ️ Tela de login não exibida ou sessão ativa.", flush=True)

        try:
            btn_enter = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'ENTER')] | //button[contains(text(), 'ENTER')]")))
            btn_enter.click()
            time.sleep(5)
        except Exception:
            pass

        driver.get("https://suporte.tjsp.jus.br/saw/Requests")
        print("⏳ Aguardando renderização da tabela...", flush=True)
        time.sleep(10)

        def forcar_refresh_tabela():
            try:
                js_click = """
                var btn = document.querySelector("button[title*='Atualizar'], button[aria-label*='Atualizar'], .grid-toolbar-refresh-button, div[title*='Atualizar']");
                if (btn) { btn.click(); return true; }
                return false;
                """
                if not driver.execute_script(js_click):
                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, 'r')
                time.sleep(2)
            except Exception:
                pass

        def extrair_chamados_da_tabela():
            mapa_chamados = {}
            forcar_refresh_tabela()

            js_script = """
            var items = [];
            var rows = document.querySelectorAll("tr, div[role='row'], .grid-row");
            rows.forEach(function(row) {
                var text = row.innerText || "";
                var html = row.innerHTML || "";
                var match = text.match(/(\\b\\d{7,8}\\b)/);
                if (match) {
                    var numId = match[1];
                    var cells = row.querySelectorAll("td, div[role='gridcell']");
                    var cellValues = [];
                    cells.forEach(function(c) {
                        cellValues.push(c.innerText ? c.innerText.trim() : "");
                    });
                    var titulo = "";
                    var solicitante = "";
                    var tipoAtendimento = "";
                    var local = "";
                    if (cellValues.length >= 8) {
                        titulo = cellValues[3];
                        solicitante = cellValues[4];
                        tipoAtendimento = cellValues[6];
                        local = cellValues[7];
                    } else {
                        var linhas = text.split("\\n").map(s => s.trim()).filter(s => s.length > 0);
                        titulo = linhas[2] || "Sem descrição";
                        solicitante = linhas[3] || "Não informado";
                        tipoAtendimento = "Não informado";
                        local = linhas[linhas.length - 2] || "Não informado";
                    }
                    items.push({
                        id: numId,
                        solicitante: solicitante || "Não informado",
                        titulo: titulo || "Sem descrição",
                        tipoAtendimento: tipoAtendimento || "Não informado",
                        local: local || "Não informado",
                        rawText: text,
                        fullHtml: html
                    });
                }
            });
            return items;
            """

            try:
                resultados = driver.execute_script(js_script)
                if resultados:
                    for item in resultados:
                        num_id = item["id"]
                        texto = item["rawText"]
                        html = item["fullHtml"]

                        if num_id not in mapa_chamados:
                            texto_lower = texto.lower()
                            html_lower = html.lower()
                            eh_vip = (
                                "vip" in texto_lower or "vip" in html_lower or
                                "urgente" in texto_lower or "urgente" in html_lower or
                                "alta" in texto_lower or "alta" in html_lower or
                                "critical" in texto_lower or "critical" in html_lower
                            )
                            vip_txt = "🚨 SIM (CHAMADO VIP / ALTA PRIORIDADE)" if eh_vip else "NÃO (Normal)"

                            msg_formatada = (
                                f"📌 *Número do chamado:* {num_id}\n"
                                f"👤 *Aberto por:* {item['solicitante']}\n"
                                f"📝 *Descrição:* {item['titulo'][:150]}\n"
                                f"💻 *Tipo de Atendimento:* {item['tipoAtendimento']}\n"
                                f"📍 *Local / Origem:* {item['local']}\n"
                                f"⭐ *Classificação VIP:* {vip_txt}"
                            )
                            mapa_chamados[num_id] = {"mensagem": msg_formatada, "is_vip": eh_vip}
            except Exception as err:
                print(f"⚠️ Erro ao varrer tabela: {err}", flush=True)

            return mapa_chamados

        historico_enviados = carregar_historico()
        print(f"📋 Histórico carregado: {len(historico_enviados)} chamado(s).", flush=True)

        mapa_inicial = extrair_chamados_da_tabela()
        for cid in mapa_inicial.keys():
            historico_enviados.add(cid)
        salvar_historico(historico_enviados)

        print(f"✅ Baseline pronta. Robô ativo na nuvem do Render!\n", flush=True)
        enviar_alertas("🟢 *Monitor TJSP Ativado na Nuvem (Render)*\n\nMonitoramento de chamados iniciado com sucesso!")

        while True:
            try:
                em_exp, motivo = dentro_do_expediente()
                agora = datetime.datetime.now(FUSO_BR)
                horario = agora.strftime('%H:%M:%S')

                if not em_exp:
                    print(f"[{horario}] 💤 Pausado: {motivo}. Aguardando 1 minuto...", flush=True)
                    time.sleep(60)
                    continue

                mapa_atual = extrair_chamados_da_tabela()
                ids_atuais = set(mapa_atual.keys())
                novos_ids = ids_atuais - historico_enviados

                if novos_ids:
                    print(f"\n[{horario}] 🚨 NOVO CHAMADO DETECTADO: {list(novos_ids)}", flush=True)
                    for nid in novos_ids:
                        dados = mapa_atual[nid]
                        detalhe_msg = dados["mensagem"]
                        alert_text = f"🚨 *NOVO CHAMADO DETECTADO NO TJSP!*\n🕒 *Horário:* {horario}\n\n{detalhe_msg}"
                        
                        enviar_alertas(alert_text)
                        historico_enviados.add(nid)
                        time.sleep(1)

                    salvar_historico(historico_enviados)
                else:
                    print(f"[{horario}] 🔄 Fila atualizada — {len(ids_atuais)} chamado(s) (0 novos).", flush=True)

                time.sleep(10)

            except Exception as e:
                print(f"⚠️ Erro no ciclo: {e}", flush=True)
                time.sleep(5)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()