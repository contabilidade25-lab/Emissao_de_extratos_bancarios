"""
Extrato INVESTIMENTO Santander — gerado por santander_recorder.py
Empresa base: AMAZON PAINEIS LTDA - ME
Gravado: 27/05/2026

Fluxo:
  Investimentos → clica mês atual (abre seletor) → seleciona mês anterior
  → Salvar em PDF → renomeia para:
    {MM} - EXTRATO INVESTIMENTO - SANTANDER - {EMPRESA}.pdf

Se 'Investimentos' não existir para a empresa → pula sem erro.
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


# Nomes dos meses em português (para montar "Abril/2026", "Maio/2026" etc.)
_MESES_PT = {
    1: "Janeiro",  2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",     6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",
}


def _periodo() -> tuple[str, str, str]:
    """
    Retorna (mes_atual_str, mes_anterior_str, mm) dinâmicos.
    Ex. em maio/2026 → ("Maio/2026", "Abril/2026", "04")
    """
    hoje = date.today()
    ano_ant, mes_ant = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    mes_atual_str    = f"{_MESES_PT[hoje.month]}/{hoje.year}"
    mes_anterior_str = f"{_MESES_PT[mes_ant]}/{ano_ant}"
    mm               = f"{mes_ant:02d}"
    return mes_atual_str, mes_anterior_str, mm


def extrato_complemento(
    driver:       webdriver.Chrome,
    empresa_nome: str,
    mm:           str,
    output_dir:   Path,
    download_dir: Path,
):
    """
    Extrato de investimentos.
    Pula silenciosamente se a empresa não tiver Investimentos.
    """
    wait = WebDriverWait(driver, 20)
    output_dir.mkdir(parents=True, exist_ok=True)

    mes_atual_str, mes_anterior_str, mm = _periodo()
    print(f"  [INVESTIMENTO] {empresa_nome} — {mes_anterior_str}")

    # ── [00] Clica "Investimentos" — pula se não existir ─────────────
    try:
        el = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//a[normalize-space(.)="Investimentos"]')
            )
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [00] Investimentos clicado")
    except TimeoutException:
        print(f"  ⚠ {empresa_nome} — sem 'Investimentos', pulando")
        return

    time.sleep(4.0)  # aguarda Angular carregar

    # ── [01] Clica mês atual para abrir o seletor ─────────────────────
    try:
        el = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable(
                (By.XPATH, f'//div[normalize-space(.)="{mes_atual_str}"]')
            )
        )
        driver.execute_script('arguments[0].click();', el)
        print(f"  → [01] seletor aberto ({mes_atual_str})")
        time.sleep(1.2)
    except TimeoutException:
        print(f"  ⚠ seletor '{mes_atual_str}' não encontrado — tentando continuar")

    # ── [02] Seleciona mês anterior ───────────────────────────────────
    try:
        el = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH,
                f'//span[normalize-space(.)="{mes_anterior_str}"] | '
                f'//div[normalize-space(.)="{mes_anterior_str}"] | '
                f'//a[normalize-space(.)="{mes_anterior_str}"]'
            ))
        )
        driver.execute_script('arguments[0].click();', el)
        print(f"  → [02] mês selecionado: {mes_anterior_str}")
    except TimeoutException:
        print(f"  ⚠ mês '{mes_anterior_str}' não encontrado — tentando baixar assim mesmo")

    time.sleep(4.0)

    # ── [03] Salvar em PDF ────────────────────────────────────────────
    try:
        el = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//a[normalize-space(.)="Salvar em PDF"]')
            )
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [03] Salvar em PDF clicado")
    except TimeoutException:
        print("  ✗ 'Salvar em PDF' não encontrado — pulando investimento")
        return

    time.sleep(4.0)  # aguarda download

    # ── Renomeia ──────────────────────────────────────────────────────
    nome_base = f"{mm} - EXTRATO INVESTIMENTO - SANTANDER - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_base, ".pdf")
    print(f"  ✓ Investimento concluído: {empresa_nome}")


def _renomear(download_dir: Path, output_dir: Path, nome: str, ext: str, timeout: int = 45):
    """Aguarda o arquivo e move com nome correto. Busca em download_dir e Downloads padrão."""
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
