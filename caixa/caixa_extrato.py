"""
Extrato CC Caixa Econômica Federal — PDF (via CDP) + OFX (download direto).

Fluxo:
  Saldo e Extratos → Extrato por Período
  → OUTRO MÊS → seleciona mês anterior → Continuar
  → Imprimir → CDP printToPDF (sem diálogo nativo) → Retornar
  → OFX radio → Continuar → download OFX
  → Renomeia os 2 arquivos em output_dir
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


def _renomear(download_dir: Path, output_dir: Path, nome: str, ext: str, timeout: int = 45):
    pastas = [download_dir]
    downloads_padrao = Path.home() / "Downloads"
    if downloads_padrao != download_dir and downloads_padrao.exists():
        pastas.append(downloads_padrao)

    prazo = time.time() + timeout
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
    """
    Tenta selecionar mês anterior nos selects que aparecem após 'OUTRO MÊS'.
    Procura selects com 'mes' ou 'ano' no id/name.
    """
    time.sleep(1.0)

    # ── Mês ──────────────────────────────────────────────────────────
    sel_mes = None
    for xpath in [
        '//select[contains(translate(@id,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"mes")]',
        '//select[contains(translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"mes")]',
        '//select',
    ]:
        try:
            sel_mes = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            break
        except TimeoutException:
            continue

    if sel_mes:
        sel = Select(sel_mes)
        opcoes = [o.get_attribute("value") for o in sel.options]
        # Tenta por número (1, 01, 4, 04...)
        for v in [str(mes_ant), f"{mes_ant:02d}"]:
            if v in opcoes:
                sel.select_by_value(v)
                print(f"  → Mês selecionado por valor: {v}")
                break
        else:
            # Tenta pelo nome em português
            nome_mes = _MESES_PT[mes_ant]
            for op in sel.options:
                if nome_mes.lower() in op.text.lower():
                    sel.select_by_visible_text(op.text)
                    print(f"  → Mês selecionado por texto: {op.text}")
                    break
            else:
                print(f"  ⚠ Mês {mes_ant} não encontrado nas opções: {[o.text for o in sel.options]}")
    else:
        print("  ⚠ Select de mês não encontrado")

    # ── Ano ───────────────────────────────────────────────────────────
    try:
        sel_ano_el = driver.find_element(
            By.XPATH,
            '//select[contains(translate(@id,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"ano")]'
            ' | //select[contains(translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"ano")]'
        )
        sel_ano = Select(sel_ano_el)
        opcoes_ano = [o.get_attribute("value") for o in sel_ano.options]
        for v in [str(ano_ant), str(ano_ant)[-2:]]:
            if v in opcoes_ano:
                sel_ano.select_by_value(v)
                print(f"  → Ano selecionado: {v}")
                break
    except NoSuchElementException:
        pass  # Sem select de ano — provavelmente usa só mês


def _salvar_pdf_cdp(driver, destino: Path):
    """Usa CDP Page.printToPDF — salva sem abrir o diálogo nativo."""
    result = driver.execute_cdp_cmd("Page.printToPDF", {
        "printBackground": True,
        "paperWidth":  8.27,    # A4
        "paperHeight": 11.69,
        "marginTop":   0.4,
        "marginBottom": 0.4,
        "marginLeft":  0.4,
        "marginRight": 0.4,
    })
    pdf_bytes = base64.b64decode(result["data"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(pdf_bytes)
    print(f"  ✓ PDF salvo: {destino.name}")


def extrato_caixa(
    driver:       webdriver.Chrome,
    empresa_nome: str,
    mm:           str,
    output_dir:   Path,
    download_dir: Path,
):
    """Executa extrato CC (PDF + OFX) para empresa já logada na Caixa."""
    wait = WebDriverWait(driver, 20)
    output_dir.mkdir(parents=True, exist_ok=True)

    _, _, mm, mes_ant, ano_ant = _mes_anterior()
    mes_anterior_str = f"{_MESES_PT[mes_ant]}/{ano_ant}"
    print(f"  [CC] {empresa_nome} — {mes_anterior_str}")

    # [01] Saldo e Extratos
    el = wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//span[normalize-space(.)="Saldo e Extratos"] | //a[normalize-space(.)="Saldo e Extratos"]')
    ))
    driver.execute_script('arguments[0].click();', el)
    print("  → [01] Saldo e Extratos")
    time.sleep(2.0)

    # [02] Extrato por Período
    el = wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//a[contains(normalize-space(.),"Extrato por Per")]')
    ))
    el.click()
    print("  → [02] Extrato por Período")
    time.sleep(3.0)

    # [03] OUTRO MÊS
    el = wait.until(EC.presence_of_element_located((By.ID, 'rdoTipoExtratoOutro')))
    driver.execute_script('arguments[0].click();', el)
    print("  → [03] OUTRO MÊS selecionado")

    # [04] Seleciona mês e ano anteriores
    _selecionar_mes(driver, wait, mes_ant, ano_ant)

    # [05] Continuar (PDF/Imprimir implícito — formato padrão)
    el = wait.until(EC.element_to_be_clickable((By.ID, 'confirma')))
    driver.execute_script('arguments[0].click();', el)
    print("  → [05] Continuar")
    time.sleep(4.0)

    # [06] Imprimir → abre nova janela com a página de impressão
    janelas_antes = set(driver.window_handles)
    el = wait.until(EC.element_to_be_clickable((By.ID, 'btnImprimir')))
    driver.execute_script('arguments[0].click();', el)
    print("  → [06] Imprimir clicado")

    # Aguarda nova janela (até 10s)
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
        driver.execute_script("window.print = function() {};")  # desativa diálogo nativo
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1.5)
        nome_pdf = f"{mm} - EXTRATOS BANCÁRIOS CC - CAIXA - {empresa_nome}.pdf"
        _salvar_pdf_cdp(driver, output_dir / nome_pdf)
        driver.close()
        driver.switch_to.window(list(janelas_antes)[0])
    else:
        # Sem nova janela — tenta CDP na janela atual
        print("  ⚠ Nova janela não detectada — tentando CDP na janela atual")
        driver.execute_script("window.print = function() {};")
        time.sleep(1.5)
        nome_pdf = f"{mm} - EXTRATOS BANCÁRIOS CC - CAIXA - {empresa_nome}.pdf"
        _salvar_pdf_cdp(driver, output_dir / nome_pdf)

    time.sleep(1.5)

    # [07] Retornar
    try:
        el = wait.until(EC.element_to_be_clickable((By.ID, 'btnRetornarcbgextratoresultado')))
        driver.execute_script('arguments[0].click();', el)
        print("  → [07] Retornar")
        time.sleep(3.0)
    except TimeoutException:
        print("  ⚠ Botão Retornar não encontrado — tentando navegação direta")
        driver.back()
        time.sleep(3.0)

    # [08] Radio OFX — "Gerar Arquivo para Gerenciadores Financeiros"
    try:
        el = wait.until(EC.presence_of_element_located((By.ID, 'rdoFormatoExtratoArquivo')))
        driver.execute_script('arguments[0].click();', el)
        print("  → [08] OFX selecionado")
        time.sleep(1.0)
    except TimeoutException:
        # Mês pode ter sido desmarcado após Retornar — re-seleciona
        print("  → [08] Re-selecionando OUTRO MÊS para OFX...")
        try:
            el = wait.until(EC.presence_of_element_located((By.ID, 'rdoTipoExtratoOutro')))
            driver.execute_script('arguments[0].click();', el)
            _selecionar_mes(driver, wait, mes_ant, ano_ant)
            el = wait.until(EC.presence_of_element_located((By.ID, 'rdoFormatoExtratoArquivo')))
            driver.execute_script('arguments[0].click();', el)
            print("  → [08] OFX selecionado (após re-seleção de mês)")
            time.sleep(1.0)
        except TimeoutException:
            print("  ✗ Radio OFX não encontrado — pulando OFX")
            return

    # [09] Continuar → download OFX
    el = wait.until(EC.element_to_be_clickable((By.ID, 'confirma')))
    driver.execute_script('arguments[0].click();', el)
    print("  → [09] Continuar (OFX)")
    time.sleep(4.0)

    # Renomeia OFX
    nome_ofx = f"{mm} - EXTRATOS BANCÁRIOS CC - CAIXA - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_ofx, ".ofx")
    print(f"  ✓ CC concluído: {empresa_nome}")
