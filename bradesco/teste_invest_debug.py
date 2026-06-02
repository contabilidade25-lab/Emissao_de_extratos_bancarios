"""
Debug de investimentos — captura o HTML dos elementos clicados após Avançar.

Faz o mesmo fluxo do teste_extrato.py (login + CC completo), chega em
[INVEST] Acessando Investimentos e ativa um listener de cliques para você
gravar os 4 elementos que devem ser acionados antes de salvar.
"""

import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from bradesco_login   import criar_driver, BradescoSession
from bradesco_extrato import BradescoExtrato, _dispensar_banner
from sheets_reader    import ler_empresas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DOWNLOADS = Path.home() / "Downloads"
BANCO_DIR = DOWNLOADS / "BRADESCO"


def main():
    print("Lendo empresas da planilha...")
    empresas = ler_empresas()
    if not empresas:
        sys.exit(1)

    print(f"\n{len(empresas)} empresa(s):\n")
    for i, e in enumerate(empresas):
        print(f"  [{i}] {e.nome}")

    idx = 0
    if len(empresas) > 1:
        escolha = input(f"\nQual testar? [0-{len(empresas)-1}] (Enter = 0): ").strip()
        if escolha.isdigit():
            idx = int(escolha)

    empresa = empresas[idx]
    print(f"\nTestando extrato: {empresa.nome}")
    print("=" * 60)

    BANCO_DIR.mkdir(parents=True, exist_ok=True)
    empresa_dir = BANCO_DIR / empresa.nome
    empresa_dir.mkdir(parents=True, exist_ok=True)

    driver = criar_driver(headless=False, download_dir=str(BANCO_DIR))
    try:
        # ── Login (idêntico ao teste_extrato) ─────────────────────────
        sessao = BradescoSession(driver)
        ok = sessao.login_completo(empresa)
        if not ok:
            print("\n✗ Login falhou.")
            input("Pressione Enter para fechar...")
            return

        print("\n✓ Login OK — iniciando extratos\n")

        extrato = BradescoExtrato(driver, BANCO_DIR)

        # ── Extrato CC (idêntico ao teste_extrato) ─────────────────────
        extrato.extratos_cc(empresa, empresa_dir)

        # ── Chega em [INVEST] e ativa listener ────────────────────────
        print("\n  [INVEST] Acessando Investimentos...")
        _dispensar_banner(driver)

        driver.switch_to.default_content()
        WebDriverWait(driver, 25).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.topmenu_I"))
        ).click()
        time.sleep(2)
        extrato._entrar_pagina_central()

        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a[href*='extratoinvestimentos']")
            )
        ).click()
        time.sleep(2)
        extrato._entrar_pagina_central()

        # ── Configura mês, tipo, produto e clica Avançar ──────────────
        extrato._escolher_sexy_combo(0)
        time.sleep(1)
        extrato._configurar_mes_invest()

        tipos = extrato._opcoes_select(
            "select[id*='comboTipoInvestimento']",
            skip_vazio=True, skip_texto=["selecione"],
        )
        if not tipos:
            print("  ✗ Nenhum tipo de investimento encontrado")
            input("Enter para fechar...")
            return

        tipo_val, tipo_texto = tipos[0]
        print(f"  → Tipo: {tipo_texto}")
        from selenium.webdriver.support.ui import Select
        Select(driver.find_element(
            By.CSS_SELECTOR, "select[id*='comboTipoInvestimento']"
        )).select_by_value(tipo_val)
        time.sleep(1.5)

        produtos = extrato._opcoes_select(
            "select[id*='comboProduto']",
            skip_vazio=True, skip_texto=["selecione", "todos"],
        )
        if not produtos:
            print("  ✗ Nenhum produto encontrado")
            input("Enter para fechar...")
            return

        prod_val, prod_texto = produtos[0]
        print(f"  → Produto: {prod_texto}")
        Select(driver.find_element(
            By.CSS_SELECTOR, "select[id*='comboTipoInvestimento']"
        )).select_by_value(tipo_val)
        time.sleep(1)
        Select(WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "select[id*='comboProduto']")
            )
        )).select_by_value(prod_val)
        time.sleep(0.5)

        # Avançar
        WebDriverWait(driver, 25).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "input.consultarExtrato[title='Avançar'], "
                 "input[title='Avançar'].bt_avancar")
            )
        ).click()
        time.sleep(3)
        extrato._entrar_pagina_central()

        print("  ✓ Avançar clicado — tela de resultado carregada")

        # ── Injeta listener de cliques ────────────────────────────────
        driver.execute_script("""
window._capturedClicks = [];
document.addEventListener('click', function(e) {
    var el = e.target;
    window._capturedClicks.push({
        tag:      el.tagName,
        id:       el.id || '',
        cls:      el.className || '',
        title:    el.getAttribute('title') || '',
        tabindex: el.getAttribute('tabindex') || '',
        html:     el.outerHTML.substring(0, 600)
    });
}, true);
""")

        print("\n" + "=" * 60)
        print("LISTENER ATIVO — clique os 4 elementos na tela do browser.")
        print("Quando terminar, pressione Enter aqui.")
        print("=" * 60)
        input()

        # ── Coleta e imprime os cliques ───────────────────────────────
        cliques = driver.execute_script("return window._capturedClicks;")
        print(f"\n{len(cliques)} clique(s) capturado(s):\n")
        for i, c in enumerate(cliques, 1):
            print(f"{'─'*60}")
            print(f"Clique {i}:")
            print(f"  tag      : {c['tag']}")
            print(f"  id       : {c['id']}")
            print(f"  class    : {c['cls']}")
            print(f"  title    : {c['title']}")
            print(f"  tabindex : {c['tabindex']}")
            print(f"  html:\n    {c['html']}")

        input("\nPressione Enter para fechar o browser...")

    except Exception as e:
        print(f"\n✗ Erro: {e}")
        input("Browser aberto. Pressione Enter para fechar...")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
