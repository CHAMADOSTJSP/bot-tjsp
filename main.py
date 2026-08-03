import re # Certifique-se de ter 'import re' no topo do seu código

def extrair_e_notificar_chamados(driver, wait, chamados_notificados, primeira_execucao=False):
    print("🔍 Buscando chamados na tela...", flush=True)
    
    try:
        time.sleep(5)
        
        # 1. Busca por linhas de tabelas padrão ou cartões da interface SAW
        linhas = driver.find_elements(By.XPATH, "//table//tbody/tr | //div[contains(@class, 'grid-row')] | //div[contains(@class, 'request-card')]")

        chamados_encontrados = 0

        for linha in linhas:
            texto_linha = linha.text.strip()
            if not texto_linha:
                continue

            # Tenta pegar as colunas explícitas
            colunas = linha.find_elements(By.XPATH, ".//td | .//div[contains(@class, 'grid-cell')] | .//div[@role='gridcell']")

            chamado_id = None
            titulo = "Sem título"
            data_hora = "N/A"
            solicitante = "N/A"
            categoria = "Geral"

            if len(colunas) >= 3:
                chamado_id = colunas[0].text.strip().replace("#", "")
                data_hora = colunas[1].text.strip() if len(colunas) > 1 else "N/A"
                titulo = colunas[2].text.strip() if len(colunas) > 2 else "Sem título"
                solicitante = colunas[3].text.strip() if len(colunas) > 3 else "N/A"
                categoria = colunas[4].text.strip() if len(colunas) > 4 else "Geral"
            else:
                # Se as colunas falharem, busca por Padrão de ID do Chamado no texto (ex: números de 5 a 10 dígitos)
                match_id = re.search(r'#?(\d{5,10})', texto_linha)
                if match_id:
                    chamado_id = match_id.group(1)
                    # Tenta limpar o título removendo o ID encontrado
                    titulo = texto_linha.replace(match_id.group(0), "").strip()[:120]
                else:
                    # Se não encontrar ID real de jeito nenhum, pula para não enviar lixo
                    continue

            if not chamado_id or chamado_id in chamados_notificados:
                continue

            chamados_notificados.add(chamado_id)
            chamados_encontrados += 1

            if primeira_execucao:
                continue

            # Detecta VIP
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