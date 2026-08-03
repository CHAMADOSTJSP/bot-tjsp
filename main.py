import re
import html
import time
from selenium.webdriver.common.by import By

def extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=False):
    print("🔍 Buscando chamados na tela...", flush=True)
    
    try:
        time.sleep(5)
        
        # Busca linhas específicas da tabela
        linhas = driver.find_elements(By.XPATH, "//div[@role='row'] | //table//tbody/tr[not(ancestor::header)]")

        chamados_encontrados = 0

        for linha in linhas:
            texto_linha = linha.text.strip()
            
            # Descarta linhas vazias ou cabeçalhos
            if not texto_linha or "Solicitado por" in texto_linha or "Tipo de Atendin" in texto_linha:
                continue

            colunas = linha.find_elements(By.XPATH, ".//div[@role='gridcell'] | .//td")

            chamado_id = None
            data_hora = "N/A"
            titulo = "Sem título"
            solicitante = "N/A"
            categoria = "Geral"

            if len(colunas) >= 4:
                raw_id = colunas[0].text.strip().replace("#", "")
                
                match = re.search(r'\d{6,10}', raw_id)
                if match:
                    chamado_id = match.group(0)
                else:
                    match_linha = re.search(r'\b\d{7,9}\b', texto_linha)
                    if match_linha:
                        chamado_id = match_linha.group(0)

                data_hora = colunas[1].text.strip() if len(colunas) > 1 else "N/A"
                titulo = colunas[2].text.strip() if len(colunas) > 2 else "Sem título"
                solicitante = colunas[3].text.strip() if len(colunas) > 3 else "N/A"
                
                if len(colunas) > 5:
                    categoria = colunas[5].text.strip()
            else:
                match_id = re.search(r'\b\d{7,9}\b', texto_linha)
                if match_id:
                    chamado_id = match_id.group(0)
                    partes = texto_linha.split("\n")
                    if len(partes) > 2:
                        titulo = partes[2]
                    else:
                        titulo = texto_linha[:100]

            if not chamado_id or chamado_id in chamados_notificados:
                continue

            chamados_notificados.add(chamado_id)
            chamados_encontrados += 1

            if primeira_execucao:
                continue

            # Detecta se é VIP
            is_vip = False
            try:
                html_linha = linha.get_attribute("innerHTML") or ""
                if "vip" in html_linha.lower() or "juiz" in solicitante.lower() or "desembargador" in solicitante.lower():
                    is_vip = True
            except Exception:
                pass

            link_chamado = f"https://suporte.tjsp.jus.br/saw/Requests/{chamado_id}"
            
            if is_vip:
                cabecalho_tg = "👑 <b>ALERTA VIP — CHAMADO PRIORITÁRIO!</b>"
                cabecalho_wa = "👑 *ALERTA VIP — CHAMADO PRIORITÁRIO!*"
                tag = "VIP ⚠️"
            else:
                cabecalho_tg = "🚨 <b>NOVO CHAMADO DETECTADO!</b>"
                cabecalho_wa = "🚨 *NOVO CHAMADO DETECTADO!*"
                tag = "Normal"

            msg_tg = (
                f"{cabecalho_tg}\n\n"
                f"📌 <b>ID:</b> #{html.escape(chamado_id)}\n"
                f"🏷️ <b>Tag:</b> {tag}\n"
                f"📂 <b>Categoria:</b> {html.escape(categoria)}\n"
                f"📝 <b>Resumo:</b> {html.escape(titulo)}\n"
                f"👤 <b>Solicitante:</b> {html.escape(solicitante)}\n"
                f"⏰ <b>Horário:</b> {html.escape(data_hora)}\n\n"
                f"🔗 {link_chamado}"
            )

            msg_wa = (
                f"{cabecalho_wa}\n\n"
                f"📌 *ID:* #{chamado_id}\n"
                f"🏷️ *Tag:* {tag}\n"
                f"📂 *Categoria:* {categoria}\n"
                f"📝 *Resumo:* {titulo}\n"
                f"👤 *Solicitante:* {solicitante}\n"
                f"⏰ *Horário:* {data_hora}\n\n"
                f"🔗 {link_chamado}"
            )

            print(f"📌 Notificando novo chamado #{chamado_id} (VIP: {is_vip})...", flush=True)
            notificar_todos(msg_tg, msg_wa)

        if primeira_execucao:
            print(f"📦 Mapeamento inicial concluído: {len(chamados_notificados)} chamados antigos ignorados.", flush=True)
        elif chamados_encontrados == 0:
            print("ℹ️ Nenhum chamado novo detectado nesta verificação.", flush=True)
        else:
            print(f"✅ Total de {chamados_encontrados} novos chamados notificados!", flush=True)

    except Exception as e:
        print(f"⚠️ Erro ao tentar extrair chamados da tela: {e}", flush=True)