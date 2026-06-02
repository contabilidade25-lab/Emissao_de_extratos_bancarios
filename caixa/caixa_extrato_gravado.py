"""
Extrato CC Caixa — gerado por caixa_recorder.py
Empresa : MAGNIFICA FASHION
Gravado : 28/05/2026 10:55
"""

import base64
import time
import shutil
import calendar
from datetime import date
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
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


def _salvar_pdf_cdp(driver, destino: Path):
    result = driver.execute_cdp_cmd("Page.printToPDF", {
        "printBackground": True, "paperWidth": 8.27, "paperHeight": 11.69,
        "marginTop": 0.4, "marginBottom": 0.4, "marginLeft": 0.4, "marginRight": 0.4,
    })
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(base64.b64decode(result["data"]))
    print(f"  ✓ PDF salvo: {destino.name}")


def _renomear(download_dir: Path, output_dir: Path, nome: str, ext: str, timeout: int = 45):
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


def _selecionar_mes(driver, wait, mes_ant: int, ano_ant: int):
    """Seleciona o mês anterior no dropdown sltOutroMes pelo texto visível."""
    texto_mes = f"{_MESES_PT[mes_ant]}/{ano_ant}"
    el = wait.until(EC.presence_of_element_located((By.ID, 'sltOutroMes')))
    sel = Select(el)
    try:
        sel.select_by_visible_text(texto_mes)
        print(f"  → Mês: {texto_mes}")
    except Exception:
        # Fallback: seleciona a primeira opção (mês mais recente = mês anterior)
        sel.select_by_index(1)
        print(f"  → Mês: selecionado por índice 1")


def extrato_caixa(
    driver:       webdriver.Chrome,
    empresa_nome: str,
    mm:           str,
    output_dir:   Path,
    download_dir: Path,
):
    """Executa extrato CC (PDF + OFX) para empresa já logada."""
    wait = WebDriverWait(driver, 20)
    output_dir.mkdir(parents=True, exist_ok=True)
    _, _, mm, mes_ant, ano_ant = _mes_anterior()
    print(f"  [CC] {empresa_nome} — {_MESES_PT[mes_ant]}/{ano_ant}")

    # [00] Saldo e Extratos
    el = wait.until(EC.element_to_be_clickable((By.XPATH, '//span[normalize-space(.)="Saldo e Extratos"]')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(3.2)

    # [01] Extrato por Período
    el = wait.until(EC.element_to_be_clickable((By.XPATH, '//a[normalize-space(.)="Extrato por Período"]')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(1.5)

    # [02] OUTRO MÊS
    el = wait.until(EC.element_to_be_clickable((By.ID, 'rdoTipoExtratoOutro')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(1.0)

    # [03] Seleciona mês anterior
    _selecionar_mes(driver, wait, mes_ant, ano_ant)
    time.sleep(1.0)

    # [04] Continuar
    el = wait.until(EC.element_to_be_clickable((By.ID, 'confirma')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(4.0)

    # [05] Imprimir → CDP salva PDF sem diálogo
    janelas_antes = set(driver.window_handles)
    el = wait.until(EC.element_to_be_clickable((By.ID, 'btnImprimir')))
    driver.execute_script('arguments[0].click();', el)

    nova_janela = None
    prazo = time.time() + 10
    while time.time() < prazo:
        novas = set(driver.window_handles) - janelas_antes
        if novas:
            nova_janela = novas.pop()
            break
        time.sleep(0.2)

    if nova_janela:
        driver.switch_to.window(nova_janela)
        driver.execute_script("window.print = function() {};")
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1.5)
        _salvar_pdf_cdp(driver, output_dir / f"{mm} - EXTRATOS BANCÁRIOS CC - CAIXA - {empresa_nome}.pdf")
        driver.close()
        driver.switch_to.window(list(janelas_antes)[0])
    else:
        driver.execute_script("window.print = function() {};")
        time.sleep(1.5)
        _salvar_pdf_cdp(driver, output_dir / f"{mm} - EXTRATOS BANCÁRIOS CC - CAIXA - {empresa_nome}.pdf")
    time.sleep(1.5)

    # [06] Retornar
    el = wait.until(EC.element_to_be_clickable((By.ID, 'btnRetornarcbgextratoresultado')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(3.0)

    # [07] OUTRO MÊS novamente (form reseta após Retornar)
    el = wait.until(EC.element_to_be_clickable((By.ID, 'rdoTipoExtratoOutro')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(1.0)

    # [08] Seleciona mês anterior novamente
    _selecionar_mes(driver, wait, mes_ant, ano_ant)
    time.sleep(1.0)

    # [09] Formato OFX — dois radios: primeiro abre a seção, segundo escolhe OFX
    el = wait.until(EC.element_to_be_clickable((By.ID, 'rdoFormatoExtratoArquivo')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(0.8)

    el = wait.until(EC.element_to_be_clickable((By.ID, 'rdoFormatoArquivoOfx')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(1.0)

    # [10] Continuar → download OFX
    el = wait.until(EC.element_to_be_clickable((By.ID, 'confirma')))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(4.0)

    # Renomeia OFX
    nome_ofx = f"{mm} - EXTRATOS BANCÁRIOS CC - CAIXA - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_ofx, ".ofx")
    print(f"  ✓ CC concluído: {empresa_nome}")
