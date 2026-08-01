def monitorar_chamados_tjsp():
    global primeira_execucao, chamados_notificados
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print("[INFO] Iniciando sessão Selenium no Portal TJSP...")
        driver.get("https://suporte.tjsp.jus.br/saw/Requests")
        time.sleep(15)  # Tempo para carregamento inicial

        # DIAGNÓSTICO DE LOGIN / NAVEGAÇÃO
        print(f"[DIAGNÓSTICO] URL atual: {driver.current_url}")
        print(f"[DIAGNÓSTICO] Título da página: {driver.title}")

        while True:
            try:
                print("[INFO] Aguardando elementos da tabela...")
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.XPATH, "//tr | //div[@role='row']"))
                )
                
                linhas = driver.find_elements(By.XPATH, "//table/tbody/tr | //div[@role='row']")
                print(f"[INFO] Linhas encontradas na página: {len(linhas)}")
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
                print(f"[DIAGNÓSTICO ERRO] URL no momento da falha: {driver.current_url}")
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