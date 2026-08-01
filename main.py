def executar_bot():
    usuario = os.getenv("USUARIO_TJSP")
    senha = os.getenv("SENHA_TJSP")

    if not usuario or not senha:
        print("❌ ERRO: Variáveis USUARIO_TJSP e SENHA_TJSP não configuradas no Render!", flush=True)
        return

    print("==================================================", flush=True)
    print("🚀 INICIANDO MONITOR TJSP NA NUVEM", flush=True)
    print("==================================================", flush=True)
    
    driver = None
    try:
        driver = iniciar_driver()
        wait = WebDriverWait(driver, 35)

        url_tjsp = "https://suporte.tjsp.jus.br/saw/Requests" 
        driver.get(url_tjsp)

        print(f"⏳ Acessando URL inicial: {driver.current_url}", flush=True)

        # ETAPA 1: TENTA LOCALIZAR USUÁRIO (se a sessão já não estiver logada)
        try:
            campo_usuario = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nome de usuário' or @type='text']"))
            )
            print("👤 Tela de login detectada. Inserindo usuário...", flush=True)
            campo_usuario.clear()
            campo_usuario.send_keys(usuario)

            try:
                btn_proximo = driver.find_element(By.XPATH, "//button[contains(.,'Próximo') or contains(.,'Proximo')]")
                btn_proximo.click()
            except:
                campo_usuario.send_keys(Keys.RETURN)

            # ETAPA 2: SENHA
            print("🔑 Aguardando campo de senha...", flush=True)
            campo_senha = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Senha' or @type='password']"))
            )
            time.sleep(1)
            campo_senha.clear()
            campo_senha.send_keys(senha)

            try:
                btn_entrar = driver.find_element(By.XPATH, "//button[contains(.,'Entrar')]")
                btn_entrar.click()
            except:
                campo_senha.send_keys(Keys.RETURN)

        except Exception as e_login:
            print(f"ℹ️ Tela de login não exibida ou sessão ativa: {e_login}", flush=True)

        # ETAPA 3: PÓS-LOGIN E CONFIRMAÇÃO DE TELA
        print("⏳ Processando autenticação e carregando tela de chamados...", flush=True)
        time.sleep(10)
        
        url_atual = driver.current_url
        titulo_atual = driver.title

        print("🎉 LOGIN EFETUADO COM SUCESSO!", flush=True)
        print(f"📌 URL Final Alcançada: {url_atual}", flush=True)
        print(f"📌 Título da Página: {titulo_atual}", flush=True)
        
        # DISPARA AS NOTIFICAÇÕES COM A CONFIRMAÇÃO DA URL
        msg_tg = f"🤖 <b>Bot TJSP:</b> Login efetuado com sucesso!\n<b>Página:</b> {url_atual}"
        msg_wa = f"🤖 Bot TJSP: Login efetuado com sucesso!\nPágina: {url_atual}"
        notificar_todos(msg_tg, msg_wa)

        # --- SEU CÓDIGO DE RASPAGEM / MONITORAMENTO DE CHAMADOS ENTRA AQUI ---

    except Exception as e:
        erro_msg = f"❌ Erro durante a execução do Bot TJSP: {e}"
        print(erro_msg, flush=True)
        notificar_todos(
            f"⚠️ <b>Alerta Bot TJSP:</b> Ocorreu uma falha.\n<code>{e}</code>",
            f"⚠️ Alerta Bot TJSP: Ocorreu uma falha no monitoramento: {e}"
        )
    finally:
        if driver:
            driver.quit()