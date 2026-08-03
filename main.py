def atualizar_grade_smax(driver):
    """Clica no botão interno de atualizar a grade do SMAX sem dar F5 na página toda."""
    try:
        # Busca botões ou ícones que contenham 'Atualizar' ou 'Refresh' dentro do SMAX
        botoes_refresh = driver.find_elements(
            By.XPATH, 
            "//button[contains(@title, 'Atualizar') or contains(@title, 'Refresh') or contains(., 'Atualizar')]"
            " | //i[contains(@class, 'refresh') or contains(@class, 'update')]"
        )
        
        clicou = False
        for btn in botoes_refresh:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                clicou = True
                print("🔄 Grade atualizada internamente (via AJAX).", flush=True)
                break
        
        # Fallback: Se não encontrar o botão na tela, ele faz o refresh normal
        if not clicou:
            driver.refresh()
            
    except Exception as e:
        print(f"⚠️ Não foi possível clicar no refresh interno: {e}", flush=True)
        driver.refresh()