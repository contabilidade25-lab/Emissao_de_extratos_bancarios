"""
Gravador de cliques — seção Investimentos Bradesco.

Fluxo:
  1. Seleciona empresa e faz login automático
  2. Baixa extratos CC automaticamente
  3. Navega até a página de Extrato de Investimentos
  4. Para — você interage manualmente no browser
  5. A cada clique, captura e exibe o HTML do elemento em tempo real
  6. Pressione Enter no terminal para encerrar e salvar o relatório
"""

import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from bradesco_login   import criar_driver, BradescoSession
from bradesco_extrato import BradescoExtrato, _dispensar_banner
from sheets_reader    import ler_empresas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DOWNLOADS = Path(__file__).parent.parent / "Downloads" / "BRADESCO"

# ── JavaScript injetado em TODOS os frames ────────────────────────────────────
_JS_LISTENER = """
if (!window._recorder_ativo) {
    window._recorder_ativo = true;
    window._cliques = [];
    document.addEventListener('click', function(e) {
        var el = e.target;
        function getXPath(node) {
            if (!node || node.nodeType !== 1) return '';
            if (node.id) return '//*[@id="' + node.id + '"]';
            var idx = 1, sib = node.previousSibling;
            while (sib) { if (sib.nodeType === 1 && sib.tagName === node.tagName) idx++; sib = sib.previousSibling; }
            return getXPath(node.parentNode) + '/' + node.tagName.toLowerCase() + '[' + idx + ']';
        }
        window._cliques.push({
            ts:         new Date().toLocaleTimeString('pt-BR'),
            tag:        el.tagName || '',
            id:         el.id || '',
            name:       el.getAttribute('name') || '',
            cls:        (el.className || '').substring(0, 120),
            title:      el.getAttribute('title') || '',
            href:       el.getAttribute('href') || '',
            onclick:    el.getAttribute('onclick') || '',
            value:      el.value || '',
            text:       (el.innerText || '').replace(/\\s+/g,' ').substring(0, 150),
            xpath:      getXPath(el),
            html:       el.outerHTML.substring(0, 1000),
            pai_html:   el.parentElement ? el.parentElement.outerHTML.substring(0, 600) : ''
        });
    }, true);
}
"""


def _injetar_em_todos_frames(driver):
    """Injeta o listener no frame atual e em todos os sub-frames recursivamente."""
    try:
        driver.execute_script(_JS_LISTENER)
    except Exception:
        pass
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
        for fr in frames:
            try:
                driver.switch_to.frame(fr)
                _injetar_em_todos_frames(driver)
                driver.switch_to.parent_frame()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        driver.switch_to.default_content()
    except Exception:
        pass


def _coletar_cliques(driver) -> list[dict]:
    """Coleta cliques registrados em todos os frames."""
    todos = []
    try:
        cliques = driver.execute_script("return window._cliques || [];")
        for c in cliques:
            c['_frame'] = 'main'
            todos.append(c)
    except Exception:
        pass
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
        for i, fr in enumerate(frames):
            try:
                driver.switch_to.frame(fr)
                cliques = driver.execute_script("return window._cliques || [];")
                for c in cliques:
                    c['_frame'] = f'frame[{i}]'
                    todos.append(c)
                driver.switch_to.parent_frame()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    return todos


def _limpar_cliques(driver):
    """Zera a fila de cliques em todos os frames."""
    try:
        driver.execute_script("window._cliques = [];")
    except Exception:
        pass
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
        for fr in frames:
            try:
                driver.switch_to.frame(fr)
                driver.execute_script("window._cliques = [];")
                driver.switch_to.parent_frame()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        driver.switch_to.default_content()
    except Exception:
        pass


def _formatar_clique(n: int, c: dict) -> str:
    linhas = [
        f"\n{'─'*60}",
        f"CLIQUE {n}  [{c.get('ts','')}]  frame: {c.get('_frame','')}",
        f"  tag      : {c.get('tag','')}",
        f"  id       : {c.get('id','')}",
        f"  name     : {c.get('name','')}",
        f"  class    : {c.get('cls','')}",
        f"  title    : {c.get('title','')}",
        f"  href     : {c.get('href','')}",
        f"  onclick  : {c.get('onclick','')}",
        f"  value    : {c.get('value','')}",
        f"  texto    : {c.get('text','')}",
        f"  xpath    : {c.get('xpath','')}",
        f"  HTML:\n    {c.get('html','')}",
        f"  HTML pai:\n    {c.get('pai_html','')}",
    ]
    return "\n".join(linhas)


def main():
    print("=" * 60)
    print("GRAVADOR DE INVESTIMENTOS — BRADESCO")
    print("=" * 60)

    print("\nLendo empresas da planilha...")
    empresas = ler_empresas()
    if not empresas:
        print("Nenhuma empresa encontrada.")
        sys.exit(1)

    print(f"\n{len(empresas)} empresa(s):\n")
    for i, e in enumerate(empresas):
        print(f"  [{i:>2}] {e.nome}")

    idx = 0
    if len(empresas) > 1:
        escolha = input(f"\nQual empresa? [0-{len(empresas)-1}] (Enter=0): ").strip()
        if escolha.isdigit():
            idx = int(escolha)

    empresa = empresas[idx]
    print(f"\nEmpresa: {empresa.nome}")

    # Pergunta se faz CC automático
    fazer_cc = input("\nBaixar CC automaticamente antes? [S/n]: ").strip().lower()
    fazer_cc = fazer_cc != "n"

    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    empresa_dir = DOWNLOADS / empresa.nome
    empresa_dir.mkdir(parents=True, exist_ok=True)

    driver = criar_driver(headless=False, download_dir=str(DOWNLOADS))

    # Arquivo de saída
    ts_arquivo = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_saida = Path(__file__).parent / f"recorder_{empresa.nome[:30]}_{ts_arquivo}.txt"

    todos_cliques: list[dict] = []
    parar = threading.Event()

    def _monitorar():
        """Thread que injeta listener e coleta cliques em tempo real."""
        ultimo = 0
        while not parar.is_set():
            try:
                _injetar_em_todos_frames(driver)
                cliques = _coletar_cliques(driver)
                novos = cliques[ultimo:]
                for c in novos:
                    n = ultimo + 1 + novos.index(c)
                    txt = _formatar_clique(n, c)
                    print(txt)
                    todos_cliques.append(c)
                ultimo = len(cliques)
            except Exception:
                pass
            time.sleep(0.4)

    try:
        # ── Login ────────────────────────────────────────────────────
        sessao = BradescoSession(driver)
        ok = sessao.login_completo(empresa)
        if not ok:
            print("\n✗ Login falhou.")
            input("Enter para fechar...")
            return

        print(f"\n✓ Login OK")

        extrato = BradescoExtrato(driver, DOWNLOADS)

        # ── CC (opcional) ─────────────────────────────────────────────
        if fazer_cc:
            print("\n[CC] Baixando extratos bancários...")
            try:
                extrato.extratos_cc(empresa, empresa_dir)
            except Exception as e:
                print(f"  ✗ Erro CC: {e}")

        # ── Navega para Investimentos ─────────────────────────────────
        print("\n[INVEST] Navegando para Extrato de Investimentos...")
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

        # ── Injeta listener e inicia monitoramento ────────────────────
        _injetar_em_todos_frames(driver)
        monitor = threading.Thread(target=_monitorar, daemon=True)
        monitor.start()

        print("\n" + "=" * 60)
        print("GRAVADOR ATIVO")
        print("Clique normalmente no browser para gravar.")
        print("Pressione Enter aqui quando terminar.")
        print("=" * 60)
        input()
        parar.set()
        monitor.join(timeout=1)

    except Exception as e:
        print(f"\n✗ Erro: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # ── Salva relatório ───────────────────────────────────────────────
    if todos_cliques:
        with open(arquivo_saida, "w", encoding="utf-8") as f:
            f.write(f"Gravação: {empresa.nome}\n")
            f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"Total de cliques: {len(todos_cliques)}\n")
            f.write("=" * 60 + "\n")
            for i, c in enumerate(todos_cliques, 1):
                f.write(_formatar_clique(i, c) + "\n")
            f.write("\n\n--- JSON ---\n")
            f.write(json.dumps(todos_cliques, ensure_ascii=False, indent=2))

        print(f"\n✓ Relatório salvo: {arquivo_saida}")
        print(f"  {len(todos_cliques)} clique(s) gravado(s)")
    else:
        print("\nNenhum clique gravado.")


if __name__ == "__main__":
    main()
