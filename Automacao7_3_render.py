import sys
import os
import platform
import traceback
import time
import re
import datetime
import requests
import urllib3
import json
import tempfile
import threading

# Garante suporte a acentuação e caracteres UTF-8 no terminal/log
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

IS_WINDOWS = platform.system() == "Windows"

# --- IMPORTAÇÃO E TRATAMENTO DE DEPENDÊNCIAS ---
try:
    import holidays
    from dotenv import load_dotenv
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception as e:
    print(f"\n❌ ERRO AO IMPORTAR BIBLIOTECAS: {e}", flush=True)
    print("Instale as dependências: pip install -r requirements.txt", flush=True)
    sys.exit(1)

# winsound só existe no Windows — importado condicionalmente
if IS_WINDOWS:
    import winsound
    import ctypes

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main():
    print("\n" + "=" * 50, flush=True)
    print("🔐 INICIALIZANDO MONITOR TJSP (COM TIPO DE ATENDIMENTO)", flush=True)
    print(f"🖥️  Ambiente detectado: {platform.system()}", flush=True)
    print("=" * 50, flush=True)

    USUARIO_TJSP = os.getenv("USUARIO_TJSP", "")
    SENHA_TJSP = os.getenv("SENHA_TJSP", "")

    # Em produção (Render) NÃO existe terminal interativo: se faltar credencial,
    # é preciso falhar rápido e com uma mensagem clara nos logs, em vez de travar
    # esperando um input() que nunca vai chegar.
    if not USUARIO_TJSP or not SENHA_TJSP:
        if not IS_WINDOWS:
            print("❌ Credenciais não encontradas nas variáveis de ambiente "
                  "USUARIO_TJSP / SENHA_TJSP. Configure-as em Render > Environment.", flush=True)
            sys.exit(1)
        else:
            print("⚠️ Credenciais não encontradas no arquivo .env!", flush=True)
            USUARIO_TJSP = input("👤 Digite seu Usuário/CPF: ").strip()
            SENHA_TJSP = input("🔑 Digite sua Senha: ").strip()

    print(f"👤 Usuário carregado: {USUARIO_TJSP}", flush=True)
    print("=" * 50 + "\n", flush=True)

    # --- CONFIGURAÇÕES DE ENVIO (agora via variáveis de ambiente, com fallback) ---
    SEU_TELEFONE = os.getenv("SEU_TELEFONE", "120363410690262545@g.us")
    ULTRAMSG_INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "instance186848")
    ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN", "zwrh8r6js03a4yef")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    HORA_INICIO = datetime.datetime.strptime("09:00:00", "%H:%M:%S").time()
    HORA_FIM = datetime.datetime.strptime("17:05:00", "%H:%M:%S").time()
    # No Render não faz sentido "bloquear a estação" (não há área de trabalho);
    # deixamos configurável e, por padrão, desligado fora do Windows.
    BLOQUEAR_APOS_EXPEDIENTE = IS_WINDOWS and os.getenv("BLOQUEAR_APOS_EXPEDIENTE", "true").lower() == "true"
    FERIADOS_SP = holidays.BR(subdiv='SP')

    ARQUIVO_HISTORICO = os.path.join(tempfile.gettempdir(), "tjsp_historico_chamados.json")
    # Pasta para salvar HTML bruto capturado (debug/precisão dos chamados)
    PASTA_DEBUG_HTML = os.path.join(tempfile.gettempdir(), "tjsp_html_debug")
    os.makedirs(PASTA_DEBUG_HTML, exist_ok=True)
    SALVAR_HTML_DEBUG = os.getenv("SALVAR_HTML_DEBUG", "true").lower() == "true"

    # --- HISTÓRICO LOCAL ---
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

    # --- RECURSOS DO WINDOWS (viram no-op fora do Windows) ---
    def emitir_alerta_sonoro_normal():
        if not IS_WINDOWS:
            return
        for _ in range(2):
            winsound.Beep(2000, 200)
            time.sleep(0.1)

    def emitir_alerta_sonoro_vip():
        if not IS_WINDOWS:
            return
        for _ in range(5):
            winsound.Beep(3200, 150)
            time.sleep(0.08)

    def bloquear_estacao_windows():
        if IS_WINDOWS:
            print("\n⏰ Fim do expediente! Bloqueando estação...", flush=True)
            ctypes.windll.user32.LockWorkStation()
        else:
            print("\n⏰ Fim do expediente! (ambiente sem GUI — monitoramento encerrado, não há estação para bloquear)", flush=True)

    # --- DISPAROS DE NOTIFICAÇÃO ---
    def disparar_whatsapp(mensagem):
        try:
            url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
            payload = {"token": ULTRAMSG_TOKEN, "to": SEU_TELEFONE, "body": mensagem}
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.post(url, data=payload, headers=headers, timeout=15, verify=False)
            if res.status_code == 200:
                print("📱 Alerta enviado para WhatsApp!", flush=True)
            else:
                print(f"⚠️ Falha WhatsApp: HTTP {res.status_code}", flush=True)
        except Exception as e:
            print(f"❌ Erro conexão WhatsApp: {e}", flush=True)

    def disparar_telegram(mensagem):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=15, verify=False)
            print("✈️ Alerta enviado para Telegram!", flush=True)
        except Exception as e:
            print(f"❌ Erro conexão Telegram: {e}", flush=True)

    def enviar_alertas(mensagem):
        threading.Thread(target=disparar_whatsapp, args=(mensagem,), daemon=True).start()
        threading.Thread(target=disparar_telegram, args=(mensagem,), daemon=True).start()

    def dentro_do_expediente():
        agora = datetime.datetime.now()
        if agora.weekday() >= 5:
            return False, "Fim de semana"
        if agora.date() in FERIADOS_SP:
            return False, f"Feriado ({FERIADOS_SP.get(agora.date())})"
        if not (HORA_INICIO <= agora.time() <= HORA_FIM):
            return False, f"Fora do expediente ({agora.time().strftime('%H:%M:%S')})"
        return True, "Em expediente"

    # --- INICIALIZAÇÃO DO CHROME (headless, compatível com container do Render) ---
    print("🌐 Iniciando Chrome em modo headless...", flush=True)
    chrome_options = Options()
    pasta_sessao = f"tjsp_session_{int(time.time())}"
    temp_dir = os.path.join(tempfile.gettempdir(), pasta_sessao)
    chrome_options.add_argument(f"--user-data-dir={temp_dir}")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")

    # Permite apontar para binários instalados no container do Render via Dockerfile
    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    try:
        if chromedriver_path:
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        print(f"❌ Falha ao iniciar o Chrome: {e}", flush=True)
        print("Verifique se o Chrome/Chromedriver estão instalados no container "
              "(veja o Dockerfile) e se CHROME_BIN/CHROMEDRIVER_PATH estão corretos.", flush=True)
        sys.exit(1)

    wait = WebDriverWait(driver, 20)

    def salvar_html_debug(motivo):
        if not SALVAR_HTML_DEBUG:
            return
        try:
            nome = f"pagina_{motivo}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            caminho = os.path.join(PASTA_DEBUG_HTML, nome)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"💾 HTML da página salvo para diagnóstico: {caminho}", flush=True)
        except Exception as e:
            print(f"⚠️ Não foi possível salvar HTML de debug: {e}", flush=True)

    try:
        # --- FLUXO DE LOGIN ---
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
            print("ℹ️ Tela de login não exibida (sessão já ativa ou carregamento direto).", flush=True)
            salvar_html_debug("tela_login_nao_encontrada")

        try:
            btn_enter = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'ENTER')] | //button[contains(text(), 'ENTER')]")))
            btn_enter.click()
            time.sleep(5)
        except Exception:
            pass

        driver.get("https://suporte.tjsp.jus.br/saw/Requests")
        print("⏳ Aguardando renderização das linhas da tabela...", flush=True)
        time.sleep(10)

        # --- REFRESH NATIVO DO SMAX ---
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

        # --- EXTRAÇÃO COM MAPEAMENTO BASEADO NA SUA TELA DO SMAX ---
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

                    // De acordo com o layout da foto enviada:
                    // Coluna 0: Checkbox
                    // Coluna 1: ID
                    // Coluna 2: Ems (Data/Hora)
                    // Coluna 3: Título
                    // Coluna 4: Solicitado por
                    // Coluna 5: Designado
                    // Coluna 6: Tipo de Atendimento (Home Office / Unidade de Trabalho)
                    // Coluna 7: Local de divulgação

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
                        // Trava de segurança caso falte alguma célula visual
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

                # Se nada foi encontrado, salva o HTML completo da página para
                # diagnosticar se os seletores (tr, div[role='row'], .grid-row)
                # ainda batem com o layout atual do SMAX.
                if not resultados:
                    salvar_html_debug("nenhum_chamado_encontrado")

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

                        mapa_chamados[num_id] = {
                            "mensagem": msg_formatada,
                            "is_vip": eh_vip,
                            "html": html,
                        }
            except Exception as err:
                print(f"⚠️ Erro ao varrer tabela visível: {err}", flush=True)
                salvar_html_debug("erro_varredura")

            return mapa_chamados

        # --- MONITORAÇÃO ---
        historico_enviados = carregar_historico()
        print(f"📋 Histórico no disco: {len(historico_enviados)} chamado(s).", flush=True)

        print("🔍 Varrendo fila inicial na tela do Chrome...", flush=True)
        mapa_inicial = extrair_chamados_da_tabela()

        for cid in mapa_inicial.keys():
            historico_enviados.add(cid)

        salvar_historico(historico_enviados)
        print(f"✅ Baseline pronta ({len(mapa_inicial)} chamado(s) lido(s) na exibição atual).", flush=True)
        print("🚀 Robô iniciado com sucesso! Monitoramento ativo.\n", flush=True)

        enviar_alertas("🟢 *Monitor TJSP Ativado*\n\nMonitorando fila e identificando chamados VIP em tempo real!")

        while True:
            try:
                em_exp, motivo = dentro_do_expediente()
                agora = datetime.datetime.now()
                horario = agora.strftime('%H:%M:%S')

                if BLOQUEAR_APOS_EXPEDIENTE and agora.weekday() < 5 and agora.time() >= HORA_FIM:
                    bloquear_estacao_windows()
                    break

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
                        eh_vip = dados["is_vip"]

                        if eh_vip:
                            print(f"🔥 [ALERTA VIP] Chamado {nid} possui TAG VIP ou ALTA PRIORIDADE!", flush=True)
                            threading.Thread(target=emitir_alerta_sonoro_vip, daemon=True).start()
                        else:
                            threading.Thread(target=emitir_alerta_sonoro_normal, daemon=True).start()

                        alert_text = f"🚨 *NOVO CHAMADO DETECTADO NO TJSP!*\n🕒 *Horário:* {horario}\n\n{detalhe_msg}"
                        enviar_alertas(alert_text)
                        historico_enviados.add(nid)
                        time.sleep(1)

                    salvar_historico(historico_enviados)
                else:
                    print(f"[{horario}] 🔄 Fila atualizada — {len(ids_atuais)} chamado(s) na tela (0 novos).", flush=True)

                time.sleep(10)

            except KeyboardInterrupt:
                print("\nEncerrado pelo usuário.", flush=True)
                break
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
        print("\n" + "❌" * 30, flush=True)
        print("OCORREU UM ERRO E O SCRIPT PRECISOU PARAR:", flush=True)
        print("❌" * 30, flush=True)
        traceback.print_exc()
        print("❌" * 30, flush=True)
        # input() bloquearia para sempre no Render — apenas encerra com erro.
        sys.exit(1)