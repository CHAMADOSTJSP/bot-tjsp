#!/usr/bin/env python3
import sys
import os
import time
import re
import datetime
import requests
import urllib3
import holidays
import threading
from flask import Flask
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. SERVIDOR WEB MÍNIMO (Para manter o Web Service Free do Render ativo) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "🟢 Monitor TJSP está online e rodando em segundo plano!", 200

def iniciar_servidor_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Inicia o Flask em uma Thread paralela para responder ao Health Check do Render
threading.Thread(target=iniciar_servidor_web, daemon=True).start()

# --- 2. LÓGICA PRINCIPAL DO ROBÔ ---
def main():
    print("\n" + "="*50)
    print("🚀 INICIANDO MONITOR TJSP NA NUVEM (WEB SERVICE FREE)")
    print("="*50)

    # Lendo credenciais das Variáveis de Ambiente do Render
    USUARIO_TJSP = os.getenv("USUARIO_TJSP", "").strip()
    SENHA_TJSP = os.getenv("SENHA_TJSP", "").strip()

    if not USUARIO_TJSP or not SENHA_TJSP:
        print("❌ ERRO: Variáveis de ambiente USUARIO_TJSP e SENHA_TJSP não configuradas no Render!")
        sys.exit(1)

    # Configuração UltraMsg
    SEU_TELEFONE = os.getenv("TELEFONE_WHATSAPP", "120363410690262545@g.us").strip()
    ULTRAMSG_INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "instance186848").strip()
    ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN", "zwrh8r6js03a4yef").strip()

    HORA_INICIO = datetime.datetime.strptime("09:00:00", "%H:%M:%S").time()
    HORA_FIM = datetime.datetime.strptime("17:05:00", "%H:%M:%S").time()

    FERIADOS_SP = holidays.BR(subdiv='SP')

    def dentro_do_expediente():
        agora = datetime.datetime.now()
        data_atual = agora.date()
        hora_atual = agora.time()
        dia_semana = agora.weekday()
        
        if dia_semana >= 5:
            return False, "Fim de semana (Sábado/Domingo)"
            
        if data_atual in FERIADOS_SP:
            nome_feriado = FERIADOS_SP.get(data_atual)
            return False, f"Feriado ({nome_feriado})"
            
        if not (HORA_INICIO <= hora_atual <= HORA_FIM):
            return False, f"Fora do horário de expediente ({hora_atual.strftime('%H:%M:%S')})"
            
        return True, "Em expediente"

    def _disparar_requisicao_whatsapp(mensagem):
        try:
            url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
            payload = {
                "token": ULTRAMSG_TOKEN,
                "to": SEU_TELEFONE,
                "body": mensagem
            }
            headers = {"User-Agent": "Mozilla/5.0"}
            requests.post(url, data=payload, headers=headers, timeout=15, verify=False)
        except Exception as e:
            print(f"❌ Erro na conexão UltraMsg: {e}")

    def enviar_alertas(mensagem):
        try:
            t_wa = threading.Thread(target=_disparar_requisicao_whatsapp, args=(mensagem,), daemon=True)
            t_wa.start()
        except Exception as e:
            print(f"❌ Erro ao disparar thread: {e}")

    def tentar_auto_login_duas_etapas(driver_instancia, user, pwd):
        print("⏳ Aguardando a tela de autenticação do TJSP...")
        time.sleep(3)
        
        iframes = driver_instancia.find_elements(By.TAG_NAME, "iframe")
        if iframes:
            try:
                driver_instancia.switch_to.frame(iframes[0])
            except:
                pass

        campo_user = None
        tempo_limite = time.time() + 15
        
        while time.time() < tempo_limite:
            inputs = driver_instancia.find_elements(By.XPATH, "//input[@type='text' or @type='email' or @name='username' or @name='user' or @id='username' or not(@type)]")
            for inp in inputs:
                if inp.is_displayed() and inp.is_enabled():
                    campo_user = inp
                    break
            if campo_user:
                break
            time.sleep(0.5)

        if campo_user:
            campo_user.click()
            campo_user.clear()
            campo_user.send_keys(user)
            time.sleep(0.5)
            
            avancou = False
            botoes_avancar = driver_instancia.find_elements(By.XPATH, "//button[contains(text(),'Avançar') or contains(text(),'Próximo') or contains(text(),'Continuar')] | //input[@type='submit']")
            for btn in botoes_avancar:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    avancou = True
                    break
            if not avancou:
                campo_user.send_keys(Keys.RETURN)
            time.sleep(2.5)

        campo_pass = None
        tempo_limite_senha = time.time() + 15
        
        while time.time() < tempo_limite_senha:
            inputs_senha = driver_instancia.find_elements(By.XPATH, "//input[@type='password']")
            for inp in inputs_senha:
                if inp.is_displayed() and inp.is_enabled():
                    campo_pass = inp
                    break
            if campo_pass:
                break
            time.sleep(0.5)

        if campo_pass:
            campo_pass.click()
            campo_pass.clear()
            campo_pass.send_keys(pwd)
            time.sleep(0.5)

            clicou_entrar = False
            botoes_entrar = driver_instancia.find_elements(By.XPATH, 
                "//button[contains(translate(text(), 'ENTRAR', 'entrar'), 'entrar') or contains(translate(text(), 'LOG', 'log'), 'log') or contains(translate(text(), 'ACESSAR', 'acessar'), 'acessar')]"
                " | //input[@type='submit' and not(contains(@value, 'Cancel')) and not(contains(@value, 'cancelar'))]"
            )

            for btn in botoes_entrar:
                texto_btn = btn.text.lower() or btn.get_attribute("value").lower()
                if "cancel" not in texto_btn and "voltar" not in texto_btn and btn.is_displayed():
                    btn.click()
                    clicou_entrar = True
                    break

            if not clicou_entrar:
                campo_pass.send_keys(Keys.RETURN)

            time.sleep(5)

        driver_instancia.switch_to.default_content()

    def atualizar_apenas_grade_fila(driver):
        try:
            botoes_atualizar = driver.find_elements(By.XPATH, "//*[contains(text(), 'Atualizar') or contains(@title, 'Atualizar')]")
            clicou = False
            for btn in botoes_atualizar:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    clicou = True
                    break
            if not clicou:
                ActionChains(driver).key_down(Keys.CONTROL).send_keys('r').key_up(Keys.CONTROL).perform()
            time.sleep(3)
        except Exception:
            pass

    # --- INICIALIZAÇÃO DO CHROME HEADLESS OTIMIZADO PARA SERVIDORES DE NUVEM ---
    print("🌐 Inicializando Google Chrome Headless na nuvem...")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as err_chrome:
        print(f"\n❌ Erro ao iniciar o Google Chrome no servidor: {err_chrome}")
        sys.exit(1)

    URL_TELA_CHAMADOS = "https://suporte.tjsp.jus.br/saw/Requests"
    driver.get(URL_TELA_CHAMADOS)

    try:
        tentar_auto_login_duas_etapas(driver, USUARIO_TJSP, SENHA_TJSP)
    except Exception as err_login:
        print(f"⚠️ Aviso no Auto-Login: {err_login}")

    driver.get(URL_TELA_CHAMADOS)
    time.sleep(3)

    print("⏳ Aguardando carregamento dos chamados...")
    try:
        WebDriverWait(driver, 25).until(
            lambda d: re.search(r'\b[89]\d{7}\b', d.find_element(By.TAG_NAME, "body").text)
        )
        print("✅ Grade carregada com sucesso!")
    except TimeoutException:
        print("⚠️ Grade de chamados demorou a responder. Continuando mesmo assim...")

    enviar_alertas("🟢 *Monitor TJSP Ativado na Nuvem (Web Service Free)*\n\nO robô está ativo e monitorando novos chamados.")

    def mapear_chamados_com_detalhes():
        mapa_chamados = {}
        
        palavras_home_office = ["home office", "home-office", "remoto", "teletrabalho", "tele-trabalho", "em casa", "vtr"]
        palavras_presencial = ["presencial", "prédio", "predio", "andar", "sala", "fórum", "forum", "comarca", "vara", "cartório"]
        
        palavras_sistema_canais = [
            "aberto", "em andamento", "pendente", "normal", "alta", "urgente", "fechado", 
            "atribuído", "atribuido", "teams", "web", "email", "e-mail", "sistema", "chat", 
            "telefone", "portal", "vith", "request", "incidente", "serviço", "servico"
        ]

        palavras_indicadoras_problema = [
            "erro", "falha", "sistema", "problema", "impressora", "acesso", "senha", 
            "sem", "nao", "não", "lento", "lentidão", "tela", "computador", "notebook", 
            "monitor", "mouse", "teclado", "outlook", "saj", "pje", "vnc", "redirecionar"
        ]

        inicio_espera = time.time()
        while time.time() - inicio_espera < 8:
            try:
                texto_pag = driver.find_element(By.TAG_NAME, "body").text
                if re.search(r'\b[89]\d{7}\b', texto_pag):
                    break
            except:
                pass
            time.sleep(0.5)

        for tentativa in range(3):
            try:
                linhas = driver.find_elements(By.XPATH, "//tr | //div[@role='row'] | //div[contains(@class, 'grid-row')] | //div[contains(@class, 'vith-grid')]")
                
                for linha in linhas:
                    try:
                        texto_linha = linha.text
                        if not texto_linha:
                            continue

                        match_id = re.search(r'\b[89]\d{7}\b', texto_linha)
                        if not match_id:
                            continue
                            
                        id_chamado = match_id.group(0)
                        if id_chamado in mapa_chamados:
                            continue

                        partes = [p.strip() for p in texto_linha.split('\n') if p.strip()]
                        
                        partes_limpas = [
                            p for p in partes 
                            if p != id_chamado and not re.search(r'\d{2}/\d{2}/\d{2,4}|\d{2}:\d{2}:\d{2}', p)
                        ]

                        quem_abriu = "Não identificado"
                        descricao = "Sem descrição"
                        local_origem = "Unidade de Trabalho"

                        # 1. Busca por Nome
                        candidatos_nome = []
                        for p in partes_limpas:
                            p_lower = p.lower().strip()
                            if p_lower in palavras_sistema_canais:
                                continue
                            if any(palabra in p_lower for palabra in palavras_indicadoras_problema):
                                continue
                            if re.match(r'^[A-Za-zÀ-ÖØ-öø-ÿ\s]{5,}$', p) and len(p.split()) >= 2:
                                candidatos_nome.append(p)

                        if candidatos_nome:
                            quem_abriu = candidatos_nome[0]

                        # 2. Busca por Local
                        candidatos_local = [
                            p for p in partes_limpas 
                            if any(loc in p.lower() for loc in ["fórum", "forum", "comarca", "vara", "cartório", "cartorio", "gab.", "gabinete", "diretoria", "unidade", "seção", "secao"])
                        ]
                        if candidatos_local:
                            local_origem = candidatos_local[0]

                        # 3. Busca por Descrição
                        candidatos_desc = [
                            p for p in partes_limpas 
                            if p != quem_abriu 
                            and p != local_origem 
                            and p.lower().strip() not in palavras_sistema_canais
                            and len(p) > 2
                        ]

                        if candidatos_desc:
                            descricao = max(candidatos_desc, key=len)
                        elif quem_abriu != "Não identificado" and len(candidatos_nome) > 1:
                            descricao = candidatos_nome[1]

                        # 4. Checagem Precisa da Tag VIP no DOM
                        texto_completo_min = texto_linha.lower()
                        try:
                            elementos_vip = linha.find_elements(By.XPATH, ".//*[contains(translate(text(), 'VIP', 'vip'), 'vip') or contains(@class, 'vip') or contains(@title, 'VIP') or contains(@aria-label, 'VIP')]")
                        except:
                            elementos_vip = []

                        eh_vip = len(elementos_vip) > 0 or "vip" in texto_completo_min or "alta" in texto_completo_min or "urgente" in texto_completo_min
                        classificacao = "SIM (Alta Prioridade)" if eh_vip else "NÃO (Normal)"

                        if any(kw in texto_completo_min for kw in palavras_home_office):
                            modalidade = "🏠 Home Office"
                        elif any(kw in texto_completo_min for kw in palavras_presencial):
                            modalidade = "🏢 Presencial"
                        else:
                            modalidade = "❓ Não especificado"

                        if len(descricao) > 120:
                            desc_exibir = descricao[:117] + "..."
                        else:
                            desc_exibir = descricao

                        detalhe_formatado = (
                            f"📌 *Número do chamado:* {id_chamado}\n"
                            f"👤 *Aberto por:* {quem_abriu}\n"
                            f"💻 *Modalidade:* {modalidade}\n"
                            f"📝 *Descrição:* {desc_exibir}\n"
                            f"📍 *Local / Origem:* {local_origem}\n"
                            f"⭐ *Classificação VIP:* {classificacao}"
                        )

                        mapa_chamados[id_chamado] = detalhe_formatado

                    except StaleElementReferenceException:
                        continue

                if mapa_chamados:
                    break
            except Exception:
                time.sleep(0.5)

        return mapa_chamados

    # --- BASELINE INICIAL ---
    mapa_anterior = mapear_chamados_com_detalhes()
    print(f"✅ Baseline definida: {len(mapa_anterior)} chamado(s) na fila.")

    # --- LOOP DE MONITORAMENTO ---
    while True:
        em_expediente, motivo = dentro_do_expediente()
        horario = time.strftime('%H:%M:%S')
        
        if not em_expediente:
            print(f"[{horario}] 💤 Robô em pausa: {motivo}. Aguardando 1 minuto...")
            time.sleep(60)
            continue

        time.sleep(10)

        atualizar_apenas_grade_fila(driver)
        horario = time.strftime('%H:%M:%S')
        
        mapa_atual = mapear_chamados_com_detalhes()
        
        if not mapa_atual and mapa_anterior:
            print(f"[{horario}] ⏳ Tabela recarregando... Mantendo {len(mapa_anterior)} chamados ativos.")
            continue

        ids_anteriores = set(mapa_anterior.keys())
        ids_atuais = set(mapa_atual.keys())
        
        novos_ids = ids_atuais - ids_anteriores
        ids_encerrados = ids_anteriores - ids_atuais

        if novos_ids:
            detalhes_lista = [mapa_atual.get(num_id, "") for num_id in novos_ids if mapa_atual.get(num_id)]
            print(f"\n[{horario}] 🚨 NOVO CHAMADO DETECTADO! ({len(novos_ids)} novo(s)) | Total: {len(ids_atuais)}")

            for i in range(0, len(detalhes_lista), 5):
                lote = detalhes_lista[i:i + 5]
                msg_alerta = f"🚨 *NOVO CHAMADO DETECTADO NO TJSP!*\n🕒 *Horário:* {horario}\n\n" + "\n\n".join(lote)
                enviar_alertas(msg_alerta)
                time.sleep(2)

            mapa_anterior = mapa_atual

        elif ids_encerrados:
            print(f"[{horario}] ℹ️ Chamado(s) resolvido(s)/removido(s). Fila atual: {len(ids_atuais)}")
            mapa_anterior = mapa_atual

        else:
            print(f"[{horario}] Fila atualizada — {len(ids_atuais)} chamados ativos.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Erro fatal no executor: {e}")