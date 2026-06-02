"""
invest_manual.py

1. Login automático
2. Extrato CC automático
3. Navega até Extrato de Investimentos e para
4. Interação manual — a cada clique:
     • exibe no terminal
     • salva clique_NNN.html  (na pasta de log)
     • copia o HTML do elemento para o clipboard
5. Enter no terminal para encerrar e salvar log completo
"""

import sys
import json
import time
import threading
import subprocess
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

DOWNLOADS = Path.home() / "Downloads" / "BRADESCO"

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
            while (sib) {
                if (sib.nodeType === 1 && sib.tagName === node.tagName) idx++;
                sib = sib.previousSibling;
            }
            return getXPath(node.parentNode) + '/' + node.tagName.toLowerCase() + '[' + idx + ']';
        }
        window._cliques.push({
            ts:       new Date().toLocaleTimeString('pt-BR'),
            tag:      el.tagName || '',
            id:       el.id || '',
            name:     el.getAttribute('name') || '',
            cls:      (el.className || '').substring(0, 120),
            title:    el.getAttribute('title') || '',
            href:     el.getAttribute('href') || '',
            onclick:  el.getAttribute('onclick') || '',
            value:    el.value || '',
            text:     (el.innerText || '').replace(/\\s+/g,' ').substring(0, 150),
            xpath:    getXPath(el),
            html:     el.outerHTML.substring(0, 3000),
            pai_html: el.parentElement ? el.parentElement.outerHTML.substring(0, 1500) : ''
        });
    }, true);
}
"""


def _copiar_clipboard(texto: str):
    """Copia texto para o clipboard do Windows via clip.exe (sem dependências extras)."""
    try:
        subprocess.run(
            "clip",
            input=texto.encode("utf-16-le"),
            check=False,
            timeout=3,
            capture_output=True,
        )
    except Exception:
        pass


def _injetar_em_todos_frames(driver):
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
    todos = []
    try:
        for c in driver.execute_script("return window._cliques || [];"):
            c["_frame"] = "main"
            todos.append(c)
    except Exception:
        pass
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
        for i, fr in enumerate(frames):
            try:
                driver.switch_to.frame(fr)
                for c in driver.execute_script("return window._cliques || [];"):
                    c["_frame"] = f"frame[{i}]"
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


def _formatar_clique(n: int, c: dict) -> str:
    return "\n".join([
        f"\n{'─'*60}",
        f"CLIQUE {n}  [{c.get('ts','')}]  frame: {c.get('_frame','')}",
        f"  tag     : {c.get('tag','')}",
        f"  id      : {c.get('id','')}",
        f"  name    : {c.get('name','')}",
        f"  class   : {c.get('cls','')}",
        f"  title   : {c.get('title','')}",
        f"  href    : {c.get('href','')}",
        f"  onclick : {c.get('onclick','')}",
        f"  value   : {c.get('value','')}",
        f"  texto   : {c.get('text','')}",
        f"  xpath   : {c.get('xpath','')}",
        f"  HTML:",
        f"    {c.get('html','')}",
        f"  HTML pai:",
        f"    {c.get('pai_html','')}",
    ])


def main():
    print("=" * 60)
    print("INVESTIMENTOS MANUAL — BRADESCO")
    print("=" * 60)

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

    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    empresa_dir = DOWNLOADS / empresa.nome
    empresa_dir.mkdir(parents=True, exist_ok=True)

    # Pasta de logs desta sessão
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path(__file__).parent / f"log_invest_{empresa.nome[:30]}_{ts}"
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Logs em: {log_dir}\n")

    driver = criar_driver(headless=False, download_dir=str(DOWNLOADS))
    todos_cliques: list[dict] = []
    parar = threading.Event()

    def _monitorar():
        ultimo = 0
        while not parar.is_set():
            try:
                _injetar_em_todos_frames(driver)
                cliques = _coletar_cliques(driver)
                novos = cliques[ultimo:]
                for j, c in enumerate(novos):
                    n = ultimo + j + 1
                    print(_formatar_clique(n, c))
                    todos_cliques.append(c)

                    html = c.get("html", "")

                    # Salva arquivo individual
                    (log_dir / f"clique_{n:03d}.html").write_text(html, encoding="utf-8")

                    # Copia para clipboard
                    _copiar_clipboard(html)
                    print(f"  ► clipboard atualizado  ({len(html)} chars)  →  clique_{n:03d}.html")

                ultimo = len(cliques)
            except Exception:
                pass
            time.sleep(0.4)

    try:
        # Login
        sessao = BradescoSession(driver)
        if not sessao.login_completo(empresa):
            print("\n✗ Login falhou.")
            input("Enter para fechar...")
            return
        print("\n✓ Login OK")

        extrato = BradescoExtrato(driver, DOWNLOADS)

        # CC automático
        print("\n[CC] Baixando extratos bancários...")
        try:
            extrato.extratos_cc(empresa, empresa_dir)
        except Exception as e:
            print(f"  ✗ Erro CC: {e}")

        # Navega para Investimentos
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

        # Inicia gravador
        _injetar_em_todos_frames(driver)
        threading.Thread(target=_monitorar, daemon=True).start()

        print("\n" + "=" * 60)
        print("MODO MANUAL ATIVO")
        print("Clique normalmente no browser.")
        print("A cada clique o HTML é copiado para o clipboard.")
        print("Pressione Enter aqui para encerrar.")
        print("=" * 60)
        input()
        parar.set()
        time.sleep(0.5)

    except Exception as e:
        print(f"\n✗ Erro: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # Salva log completo
    if todos_cliques:
        log_txt = log_dir / "cliques.txt"
        log_json = log_dir / "cliques.json"
        with open(log_txt, "w", encoding="utf-8") as f:
            f.write(f"Empresa : {empresa.nome}\n")
            f.write(f"Data    : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"Total   : {len(todos_cliques)} clique(s)\n")
            f.write("=" * 60 + "\n")
            for i, c in enumerate(todos_cliques, 1):
                f.write(_formatar_clique(i, c) + "\n")
        with open(log_json, "w", encoding="utf-8") as f:
            json.dump(todos_cliques, f, ensure_ascii=False, indent=2)
        print(f"\n✓ {len(todos_cliques)} clique(s) salvos em: {log_dir}")
    else:
        print("\nNenhum clique gravado.")


if __name__ == "__main__":
    main()
