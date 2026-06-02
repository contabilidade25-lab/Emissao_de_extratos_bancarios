"""
Extrato CC Sicredi — gerado a partir dos HTMLs inspecionados.

Fluxo (empresa já logada):
  1. Clica "Extrato" no menu
  2. Preenche data inicial e final do mês anterior
  3. Clica Pesquisar
  4. Clica "Gerar PDF"  → aguarda download → renomeia
  5. Clica "Gerar OFX"  → aguarda download → renomeia
"""

import time
import shutil
import calendar
from datetime import date
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


_MESES_PT = {
    1: "Janeiro",  2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",     6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",
}


def _mes_anterior():
    hoje = date.today()
    ano, mes = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    ultimo = calendar.monthrange(ano, mes)[1]
    mm = f"{mes:02d}"
    return f"01/{mm}/{ano}", f"{ultimo}/{mm}/{ano}", mm, mes, ano


def _preencher(driver, el, valor: str):
    driver.execute_script(
        """
        var el=arguments[0]; var val=arguments[1];
        var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;
        s.call(el,val);
        el.dispatchEvent(new Event("input",{bubbles:true}));
        el.dispatchEvent(new Event("change",{bubbles:true}));
        el.dispatchEvent(new Event("blur",{bubbles:true}));
        """,
        el, valor,
    )
    time.sleep(0.3)


def _renomear(download_dir: Path, output_dir: Path, nome: str, ext: str, timeout: int = 60):
    pastas = [download_dir, Path.home() / "Downloads"]
    prazo  = time.time() + timeout
    while time.time() < prazo:
        for pasta in pastas:
            try:
                candidatos = [
                    f for f in pasta.iterdir()
                    if f.suffix.lower() == ext.lower()
                    and not f.name.endswith(".crdownload")
                    and not f.name.endswith(".tmp")
                    and (time.time() - f.stat().st_mtime) < 300
                ]
            except Exception:
                continue
            if candidatos:
                arq = max(candidatos, key=lambda f: f.stat().st_mtime)
                destino = output_dir / f"{nome}{ext}"
                if destino.exists():
                    destino.unlink()
                output_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(arq), str(destino))
                print(f"  ✓ Salvo: {destino.name}")
                return
        time.sleep(0.8)
    print(f"  ✗ Arquivo {ext} não chegou em {timeout}s")


def extrato_sicredi(
    driver:       webdriver.Chrome,
    empresa_nome: str,
    mm:           str,
    output_dir:   Path,
    download_dir: Path,
):
    """Executa extrato CC (PDF + OFX) para empresa já logada."""
    wait = WebDriverWait(driver, 25)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_ini, data_fim, mm, mes_ant, ano_ant = _mes_anterior()
    print(f"  [CC] {empresa_nome} — {_MESES_PT[mes_ant]}/{ano_ant}  ({data_ini} a {data_fim})")

    # 1. Clica "Extrato" no menu lateral
    el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-gtm="Extrato"]')))
    driver.execute_script("arguments[0].click();", el)
    print("  → Extrato clicado")
    time.sleep(2.5)

    # 2. Preenche data inicial (01/MM/AAAA)
    el_ini = wait.until(EC.presence_of_element_located((By.ID, "dataInicialExtrato")))
    el_ini.clear()
    _preencher(driver, el_ini, data_ini)
    print(f"  → Data inicial: {data_ini}")

    # 3. Preenche data final (DD/MM/AAAA)
    el_fim = driver.find_element(By.ID, "dataFinalExtrato")
    el_fim.clear()
    _preencher(driver, el_fim, data_fim)
    print(f"  → Data final: {data_fim}")
    time.sleep(0.5)

    # 4. Pesquisar
    el = wait.until(EC.element_to_be_clickable((By.ID, "pesquisarExtratoNovo")))
    driver.execute_script("arguments[0].click();", el)
    print("  → Pesquisar clicado")
    time.sleep(4.0)

    # 5. Gerar PDF (download direto)
    el = wait.until(EC.element_to_be_clickable((By.ID, "botaoGerarPDFExtrato")))
    driver.execute_script("arguments[0].click();", el)
    print("  → Gerar PDF clicado")
    nome_pdf = f"{mm} - EXTRATOS BANCÁRIOS CC - SICREDI - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_pdf, ".pdf")

    time.sleep(1.5)

    # 6. Gerar OFX (download direto)
    el = wait.until(EC.element_to_be_clickable((By.ID, "botaoGerarDocumentoOFX")))
    driver.execute_script("arguments[0].click();", el)
    print("  → Gerar OFX clicado")
    nome_ofx = f"{mm} - EXTRATOS BANCÁRIOS CC - SICREDI - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_ofx, ".ofx")

    print(f"  ✓ CC concluído: {empresa_nome}")
