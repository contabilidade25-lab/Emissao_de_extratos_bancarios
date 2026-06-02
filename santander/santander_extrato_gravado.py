"""
Extrato CC + Investimento Santander — gerado por santander_recorder.py
Empresa base: AMAZON PAINEIS LTDA - ME
Gravado: 27/05/2026

Fluxo:
  Conta Corrente → Período personalizado → datas mês anterior
  → Exportar PDF → Baixar extrato
  → Exportar OFX → Money 2000 → Baixar extrato
  → Investimentos (se existir) → mês anterior → Salvar em PDF
  → Renomeia os 3 arquivos na pasta da empresa

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
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException
)


_MESES_PT = {
    1: "Janeiro",  2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",     6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",
}


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


def _mes_anterior():
    hoje = date.today()
    ano, mes = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    ultimo = calendar.monthrange(ano, mes)[1]
    mm = f"{mes:02d}"
    return f"01/{mm}/{ano}", f"{ultimo}/{mm}/{ano}", mm


def _clicar_exportar(driver):
    _aguardar_sem_loader(driver)   # garante que nenhum spinner esteja em cima
    for xpath in [
        '//a[normalize-space(.)="Exportar"]',
        '//a[contains(normalize-space(.),"Exportar")]',
        '//button[contains(normalize-space(.),"Exportar")]',
    ]:
        try:
            el = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            driver.execute_script('arguments[0].click();', el)
            return
        except TimeoutException:
            continue
    raise NoSuchElementException("Botão Exportar não encontrado")


def _aguardar_sem_loader(driver, timeout: int = 15):
    """Espera o overlay dss-page-loader sumir antes de clicar."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.dss-page-loader")
            )
        )
        time.sleep(0.3)
    except TimeoutException:
        pass  # se não achou o loader, tudo bem — continua


def _clicar_baixar(driver, wait):
    """Clica 'Baixar extrato' com .click() nativo (dispara o download)."""
    _aguardar_sem_loader(driver)   # aguarda spinner de carregamento sumir
    for xpath in [
        '//button[contains(normalize-space(.),"Baixar extrato")]',
        '//a[contains(normalize-space(.),"Baixar extrato")]',
        '//button[contains(normalize-space(.),"Baixar")]',
    ]:
        try:
            el = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            el.click()
            return
        except TimeoutException:
            continue
    # Fallback: <p> → sobe para pai button/a e usa native click
    try:
        el = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, '//p[contains(normalize-space(.),"Baixar extrato")]')
            )
        )
        pai = driver.execute_script(
            "var e=arguments[0];"
            "while(e && e.tagName!=='BUTTON' && e.tagName!=='A') e=e.parentElement;"
            "return e;",
            el
        )
        (pai or el).click()
    except TimeoutException:
        raise NoSuchElementException("'Baixar extrato' não encontrado")


def _sel_radio(driver, wait, radio_id: str, label_texto: str):
    """Seleciona radio button hidden por ID (JS click) ou pelo label."""
    # Primeiro tenta abrir as opções (label.form-check-label)
    try:
        el = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'label.form-check-label'))
        )
        driver.execute_script('arguments[0].click();', el)
        time.sleep(0.5)
    except TimeoutException:
        pass
    # Clica no radio pelo ID (pode ser display:none — usa JS)
    try:
        el = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.ID, radio_id))
        )
        driver.execute_script('arguments[0].click();', el)
        print(f"  → radio #{radio_id} selecionado")
        return
    except TimeoutException:
        pass
    # Fallback pelo texto do label
    try:
        el = driver.find_element(
            By.XPATH,
            f'//label[contains(normalize-space(.), "{label_texto}")] | '
            f'//div[normalize-space(.)="{label_texto}"]'
        )
        driver.execute_script('arguments[0].click();', el)
        print(f"  → label '{label_texto}' selecionado")
    except NoSuchElementException:
        print(f"  ⚠ radio '{label_texto}' não encontrado")


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


def extrato_gravado(
    driver:       webdriver.Chrome,
    empresa_nome: str,
    mm:           str,
    output_dir:   Path,
    download_dir: Path,
):
    """Executa CC + Investimento para empresa já logada."""
    wait = WebDriverWait(driver, 20)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_inicio, data_fim, mm = _mes_anterior()
    hoje = date.today()
    ano_ant, mes_ant = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    mes_atual_str    = f"{_MESES_PT[hoje.month]}/{hoje.year}"
    mes_anterior_str = f"{_MESES_PT[mes_ant]}/{ano_ant}"

    print(f"  [CC] {empresa_nome} — {data_inicio} a {data_fim}")

    # [00] fecha banner inicial (ID dinâmico — ignora se não achar)
    try:
        el = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((By.ID, 'j_id_1h'))
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [00] banner fechado")
    except TimeoutException:
        print("  → [00] sem banner")

    time.sleep(1.3)

    # [01] Conta Corrente
    el = wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//span[normalize-space(.)="Conta Corrente"]')
    ))
    driver.execute_script('arguments[0].click();', el)
    print("  → [01] Conta Corrente")
    time.sleep(4.0)

    # [01b] Em sessão nova, "Conta Corrente" abre overview — precisa navegar ao extrato.
    # Se o campo de data já estiver na tela, pula; caso contrário procura o link.
    _no_extrato = False
    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input.dss-datepicker__input--start')
            )
        )
        _no_extrato = True
        print("  → [01b] já na página de extrato")
    except TimeoutException:
        pass

    if not _no_extrato:
        print("  → [01b] buscando link de extrato...")
        _XPATH_EXT = (
            '//a[contains(normalize-space(.),"Ver extrato")] | '
            '//span[contains(normalize-space(.),"Ver extrato")] | '
            '//a[contains(normalize-space(.),"Consultar extrato")] | '
            '//span[contains(normalize-space(.),"Consultar extrato")] | '
            '//a[contains(normalize-space(.),"extrato e saldo")] | '
            '//span[contains(normalize-space(.),"extrato e saldo")] | '
            '//a[contains(normalize-space(.),"Extrato") '
            '  and not(contains(normalize-space(.),"Baixar"))] | '
            '//span[contains(normalize-space(.),"Extrato") '
            '  and not(contains(normalize-space(.),"Baixar"))]'
        )
        _clicou_ext = False
        for _tent in range(4):  # até 4 tentativas (stale element no Angular)
            try:
                el = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, _XPATH_EXT))
                )
                _txt = el.text.strip()[:40]
                el.click()  # .click() nativo — dispara onclick JSF corretamente
                print(f"  → [01b] navegou: {_txt!r}")
                time.sleep(3.0)
                _clicou_ext = True
                break
            except StaleElementReferenceException:
                print(f"  → [01b] stale (tentativa {_tent+1}) — re-tentando...")
                time.sleep(0.5)
            except TimeoutException:
                break  # elemento não existe — vai para debug

        if not _clicou_ext:
            # Debug — mostra os elementos de texto visíveis na página
            _els = driver.find_elements(
                By.XPATH,
                '//*[self::a or self::span or self::button or self::li]'
                '[string-length(normalize-space(.)) > 2 '
                ' and string-length(normalize-space(.)) < 60]'
            )
            _vis = [e for e in _els if e.is_displayed() and e.text.strip()][:20]
            print(f"  ⚠ DEBUG — {len(_vis)} elementos visíveis após 'Conta Corrente':")
            for _e in _vis:
                print(f"      <{_e.tag_name}> {_e.text.strip()[:50]!r}")
            raise NoSuchElementException(
                "Página de extrato não encontrada — veja DEBUG acima"
            )

    time.sleep(2.0)

    # [02] fecha banner/popup da página de extrato (aparece só após chegar nela)
    try:
        el = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.dss-icon-close-1px'))
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [02] banner fechado")
    except TimeoutException:
        print("  → [02] sem banner")

    time.sleep(1.5)

    # [03] Período personalizado — abre os campos de data
    try:
        el = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//label[normalize-space(.)="Período personalizado"]')
            )
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [03] Período personalizado")
        time.sleep(1.0)
    except TimeoutException:
        print("  → [03] sem 'Período personalizado' — continuando")

    # [04-06] preenche datas com CSS selector (IDs são dinâmicos na gravação)
    campo_inicio = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'input.dss-datepicker__input--start')
        )
    )
    _preencher(driver, campo_inicio, data_inicio)
    print(f"  → Data início: {data_inicio}")
    time.sleep(0.5)

    campo_fim = driver.find_element(
        By.CSS_SELECTOR, 'input.dss-datepicker__input--end'
    )
    _preencher(driver, campo_fim, data_fim)
    print(f"  → Data fim: {data_fim}")
    time.sleep(4.0)

    # ── PDF ──────────────────────────────────────────────────────────
    print("  → [07] Exportar PDF...")
    _clicar_exportar(driver)
    time.sleep(1.6)

    _sel_radio(driver, wait, 'pdf', 'PDF')
    time.sleep(1.3)

    print("  → [10] Baixar extrato (PDF)...")
    _clicar_baixar(driver, wait)
    print("  → PDF solicitado ✓")
    time.sleep(4.0)

    # ── OFX ──────────────────────────────────────────────────────────
    print("  → [11] Exportar OFX...")
    _clicar_exportar(driver)
    time.sleep(1.4)

    _sel_radio(driver, wait, 'ofx', 'OFX')
    time.sleep(0.5)

    print("  → [14] Money 2000 ou superior...")
    el = wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//label[normalize-space(.)="Money 2000 ou superior"]')
    ))
    driver.execute_script('arguments[0].click();', el)
    time.sleep(1.6)

    print("  → [17] Baixar extrato (OFX)...")
    _clicar_baixar(driver, wait)
    print("  → OFX solicitado ✓")
    time.sleep(3.0)

    # ── Renomeia CC (PDF + OFX) ───────────────────────────────────────
    nome_cc = f"{mm} - EXTRATOS BANCÁRIOS CC - SANTANDER - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_cc, ".pdf")
    _renomear(download_dir, output_dir, nome_cc, ".ofx")
    print(f"  ✓ CC concluído: {empresa_nome}")

    # ── Investimentos (opcional) ──────────────────────────────────────
    print(f"\n  [INVESTIMENTO] {empresa_nome} — {mes_anterior_str}")

    # [18] Fecha eventual modal que sobrou do OFX (ID dinâmico — ignora)
    try:
        el = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((By.ID, 'j_id_p'))
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [18] modal fechado")
        time.sleep(1.0)
    except TimeoutException:
        pass

    # [19] Clica "Investimentos" — pula empresa se não existir
    try:
        el = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH,
                '//span[normalize-space(.)="Investimentos"] | '
                '//a[normalize-space(.)="Investimentos"]'
            ))
        )
        driver.execute_script('arguments[0].click();', el)
        print("  → [19] Investimentos")
    except TimeoutException:
        print(f"  ⚠ {empresa_nome} — sem 'Investimentos', pulando")
        return

    time.sleep(4.0)

    # [19b] "Ver extrato consolidado" — link JSF (onclick não borbulha, usar .click() nativo)
    try:
        el = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//a[normalize-space(.)="Ver extrato consolidado"]')
            )
        )
        el.click()  # nativo — dispara jsf.util.chain + myfaces.oam.submitForm
        print("  → [19b] Ver extrato consolidado")
        time.sleep(4.0)
    except TimeoutException:
        print(f"  ⚠ 'Ver extrato consolidado' não encontrado — pulando investimento")
        return

    # [20] Clica o seletor de mês (div.ibe-select) para abrir o picker
    # Estrutura real: <div class="ibe-select ..."><span class="not-selectable">Maio/2026</span>...
    # normalize-space(.) no div inclui o ícone — usa o span interno para matchear o mês
    try:
        el = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH,
                f'//div[contains(@class,"ibe-select") and '
                f'.//span[normalize-space(.)="{mes_atual_str}"]]'
            ))
        )
        driver.execute_script('arguments[0].click();', el)
        print(f"  → [20] seletor aberto ({mes_atual_str})")
        time.sleep(1.2)
    except TimeoutException:
        print(f"  ⚠ seletor '{mes_atual_str}' não encontrado — continuando")

    # [21] Seleciona mês anterior — span.not-selectable dentro do picker aberto
    try:
        el = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH,
                f'//span[normalize-space(.)="{mes_anterior_str}"] | '
                f'//div[contains(@class,"ibe-select") and '
                f'  .//span[normalize-space(.)="{mes_anterior_str}"]]'
            ))
        )
        driver.execute_script('arguments[0].click();', el)
        print(f"  → [21] mês: {mes_anterior_str}")
    except TimeoutException:
        print(f"  ⚠ '{mes_anterior_str}' não encontrado — tentando assim mesmo")

    time.sleep(4.0)

    # [22] Salvar em PDF
    try:
        el = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//a[normalize-space(.)="Salvar em PDF"]')
        ))
        driver.execute_script('arguments[0].click();', el)
        print("  → [22] Salvar em PDF")
    except TimeoutException:
        print("  ✗ 'Salvar em PDF' não encontrado — pulando investimento")
        return

    time.sleep(4.0)

    # Renomeia investimento
    nome_inv = f"{mm} - EXTRATO INVESTIMENTO - SANTANDER - {empresa_nome}"
    _renomear(download_dir, output_dir, nome_inv, ".pdf")
    print(f"  ✓ Investimento concluído: {empresa_nome}")
