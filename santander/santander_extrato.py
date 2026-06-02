"""
Extração de extrato bancário — Santander Net Empresa PJ.

Fluxo pós-login:
  1. Clica em "Conta Corrente" no menu
  2. Clica em "Consultar extrato e saldo"
  3. Fecha banner se aparecer
  4. Preenche data: mês anterior (1º ao último dia)
  5. Aguarda 3s o carregamento automático
  6. Clica em "Exportar" → seleciona PDF → "Baixar extrato"
     Salva como: {MM} - EXTRATOS BANCÁRIOS CC - SANTANDER - {NOME}
  7. Clica em "Exportar" novamente → seleciona OFX → "Money 2000 ou superior" → "Baixar"
     Salva com o mesmo padrão de nome
"""

import os
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
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

TIMEOUT = 25
DOWNLOAD_WAIT = 30  # segundos para aguardar o arquivo aparecer na pasta


# ── Helpers ───────────────────────────────────────────────────────────


def _mes_anterior() -> tuple[str, str, str]:
    """
    Retorna (primeiro_dia, ultimo_dia, mm_str) do mês anterior.
    Ex.: em maio/2026 → ("01/04/2026", "30/04/2026", "04")
    """
    hoje = date.today()
    if hoje.month == 1:
        ano, mes = hoje.year - 1, 12
    else:
        ano, mes = hoje.year, hoje.month - 1

    ultimo = calendar.monthrange(ano, mes)[1]
    mm = f"{mes:02d}"
    return (
        f"01/{mm}/{ano}",
        f"{ultimo}/{mm}/{ano}",
        mm,
    )


def _nome_arquivo(empresa_nome: str, mm: str) -> str:
    """Gera o prefixo de nome do arquivo, sem extensão."""
    return f"{mm} - EXTRATOS BANCÁRIOS CC - SANTANDER - {empresa_nome}"


def _aguardar_download(pasta: Path, prefixo: str, extensao: str, timeout: int = DOWNLOAD_WAIT) -> Path | None:
    """
    Aguarda um arquivo com `prefixo` + `extensao` aparecer em `pasta`.
    Retorna o Path do arquivo ou None se timeout.
    Ignora arquivos .crdownload (download incompleto do Chrome).
    """
    prazo = time.time() + timeout
    while time.time() < prazo:
        for arq in pasta.iterdir():
            if (
                arq.suffix.lower() == extensao.lower()
                and not arq.name.endswith(".crdownload")
                and prefixo.lower() in arq.name.lower()
            ):
                return arq
        # Verifica qualquer arquivo novo que termine com a extensão
        candidatos = [
            f for f in pasta.iterdir()
            if f.suffix.lower() == extensao.lower()
            and not f.name.endswith(".crdownload")
        ]
        if candidatos:
            # pega o mais recente
            return max(candidatos, key=lambda f: f.stat().st_mtime)
        time.sleep(0.8)
    return None


# ── Classe principal ───────────────────────────────────────────────────


class SantanderExtrato:
    """
    Realiza a extração de extrato (PDF + OFX) para uma empresa
    já autenticada na sessão Santander.
    """

    # Seletores
    SEL_MENU_CC        = "span.ui-menuitem-text"          # filtra por texto "Conta Corrente"
    SEL_BANNER_CLOSE   = ".dss-icon-close-1px"
    SEL_DATE_START     = "input.dss-datepicker__input--start"
    SEL_DATE_END       = "input.dss-datepicker__input--end"
    SEL_EXPORTAR_BTN   = "a.dss-button.dss-button--text"  # texto " Exportar "
    # Modal "Baixar extrato" — cards de formato
    # Seletores abaixo usam XPath por texto pois as classes DSS podem variar
    SEL_BAIXAR_BTN     = "button"   # botão vermelho "Baixar extrato" no modal

    def __init__(
        self,
        driver: webdriver.Chrome,
        output_dir: Path,
        download_dir: Path,
    ):
        self.driver       = driver
        self.wait         = WebDriverWait(driver, TIMEOUT)
        self.output_dir   = output_dir
        self.download_dir = download_dir

    # ── Passos individuais ─────────────────────────────────────────────

    def _clicar_menu_conta_corrente(self) -> bool:
        """Clica no item de menu 'Conta Corrente'."""
        try:
            menus = self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, self.SEL_MENU_CC)
                )
            )
            for item in menus:
                if "conta corrente" in item.text.lower():
                    print("  → Menu: Conta Corrente")
                    self.driver.execute_script("arguments[0].click();", item)
                    time.sleep(1.5)
                    return True
            print("  ✗ Menu 'Conta Corrente' não encontrado")
            return False
        except TimeoutException:
            print("  ✗ Timeout aguardando menu")
            return False

    def _clicar_consultar_extrato(self) -> bool:
        """
        Clica em 'Consultar extrato e saldo'.
        ID fixo: formGeral:j_id_5l_2e:1:j_id_5l_2j
        Fallback: busca por texto no submenu.
        """
        # Tenta ID fixo primeiro
        try:
            btn = self.driver.find_element(By.ID, "formGeral:j_id_5l_2e:1:j_id_5l_2j")
            print("  → Consultar extrato e saldo (ID fixo)")
            self.driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
            return True
        except NoSuchElementException:
            pass

        # Fallback: procura pelo texto
        try:
            itens = self.driver.find_elements(By.CSS_SELECTOR, self.SEL_MENU_CC)
            for item in itens:
                if "extrato" in item.text.lower() and "saldo" in item.text.lower():
                    print("  → Consultar extrato e saldo (texto)")
                    self.driver.execute_script("arguments[0].click();", item)
                    time.sleep(2)
                    return True
            # Tenta link/ancora com texto
            links = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Consultar extrato")
            if links:
                print("  → Consultar extrato e saldo (link)")
                self.driver.execute_script("arguments[0].click();", links[0])
                time.sleep(2)
                return True
        except Exception:
            pass

        print("  ✗ 'Consultar extrato e saldo' não encontrado")
        return False

    def _fechar_banner(self):
        """Fecha banner/modal promocional se aparecer (ignora se não existir)."""
        try:
            botao = WebDriverWait(self.driver, 4).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self.SEL_BANNER_CLOSE))
            )
            print("  → Fechando banner")
            self.driver.execute_script("arguments[0].click();", botao)
            time.sleep(0.8)
        except TimeoutException:
            pass  # sem banner — ok

    def _preencher_datas(self, data_inicio: str, data_fim: str) -> bool:
        """
        Preenche o filtro de datas (dss-datepicker-range).
        Formato esperado: DD/MM/AAAA
        """
        try:
            # Aguarda os campos de data aparecerem
            campo_inicio = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self.SEL_DATE_START)
                )
            )
            time.sleep(0.5)

            # Limpa e preenche data início via JS (campos custom precisam de evento)
            self._preencher_campo_data(campo_inicio, data_inicio)
            print(f"  → Data início: {data_inicio}")

            campo_fim = self.driver.find_element(By.CSS_SELECTOR, self.SEL_DATE_END)
            self._preencher_campo_data(campo_fim, data_fim)
            print(f"  → Data fim: {data_fim}")

            time.sleep(0.3)
            # Pressiona Enter no campo fim para confirmar
            from selenium.webdriver.common.keys import Keys
            campo_fim.send_keys(Keys.TAB)
            time.sleep(3)  # aguarda carregamento automático dos dados
            return True

        except (TimeoutException, NoSuchElementException) as e:
            print(f"  ✗ Falha ao preencher datas: {e}")
            return False

    def _preencher_campo_data(self, campo, valor: str):
        """Limpa e preenche campo de data com eventos."""
        self.driver.execute_script(
            """
            var el  = arguments[0];
            var val = arguments[1];
            el.focus();
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('blur',   {bubbles: true}));
            """,
            campo, valor,
        )
        time.sleep(0.4)

    def _clicar_exportar(self) -> bool:
        """
        Rola até o fim da página e clica no botão 'Exportar'.
        """
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Busca todos os botões de texto e filtra por "Exportar"
            botoes = self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, self.SEL_EXPORTAR_BTN)
                )
            )
            for btn in botoes:
                if "exportar" in btn.text.lower():
                    print("  → Clicando Exportar")
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1.5)
                    return True

            # Fallback: procura por qualquer elemento com texto exportar
            try:
                btn = self.driver.find_element(By.XPATH, "//*[normalize-space(text())='Exportar']")
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(1.5)
                return True
            except NoSuchElementException:
                pass

            print("  ✗ Botão 'Exportar' não encontrado")
            return False

        except TimeoutException:
            print("  ✗ Timeout aguardando botão Exportar")
            return False

    def _clicar_card_formato(self, texto: str) -> bool:
        """
        Clica no card de formato do modal 'Baixar extrato'.
        Os cards têm textos: 'PDF', 'Excel', 'OFX Money'.
        Estratégia: XPath buscando qualquer elemento clicável com aquele texto.
        """
        try:
            # Tenta encontrar o card pelo texto exato dentro do modal
            xpath = (
                f"//*[self::div or self::label or self::span or self::button]"
                f"[normalize-space(text())='{texto}' or normalize-space(.)='{texto}']"
            )
            elementos = WebDriverWait(self.driver, 8).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath))
            )
            for el in elementos:
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.6)
                    return True
        except TimeoutException:
            pass

        # Fallback: procura input radio próximo a um label com o texto
        try:
            label = self.driver.find_element(
                By.XPATH, f"//label[contains(normalize-space(.), '{texto}')]"
            )
            self.driver.execute_script("arguments[0].click();", label)
            time.sleep(0.6)
            return True
        except NoSuchElementException:
            pass

        print(f"  ✗ Card '{texto}' não encontrado")
        return False

    def _clicar_botao_baixar_extrato(self) -> bool:
        """Clica no botão vermelho 'Baixar extrato' dentro do modal."""
        try:
            # XPath pelo texto exato do botão
            xpath = "//button[normalize-space(text())='Baixar extrato'] | //button[normalize-space(.)='Baixar extrato']"
            btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.5)
            return True
        except TimeoutException:
            print("  ✗ Botão 'Baixar extrato' não encontrado no modal")
            return False

    def _selecionar_pdf_e_baixar(self) -> bool:
        """
        No modal 'Baixar extrato':
          - Clica no card 'PDF'  (já vem selecionado por padrão, mas força o clique)
          - Clica em 'Baixar extrato'
        """
        try:
            # Aguarda o modal abrir (título visível)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Baixar extrato') or contains(text(),'Escolha o formato')]")
                )
            )
            time.sleep(0.5)

            print("  → Selecionando card PDF")
            self._clicar_card_formato("PDF")

            print("  → Clicando 'Baixar extrato' (PDF)")
            return self._clicar_botao_baixar_extrato()

        except TimeoutException as e:
            print(f"  ✗ Modal de download não abriu: {e}")
            return False

    def _selecionar_ofx_e_baixar(self) -> bool:
        """
        No modal 'Baixar extrato':
          - Clica no card 'OFX Money'
          - Aguarda os sub-rádios aparecerem
          - Clica em 'Money 2000 ou superior'
          - Clica em 'Baixar extrato'
        """
        try:
            # Aguarda o modal abrir
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Baixar extrato') or contains(text(),'Escolha o formato')]")
                )
            )
            time.sleep(0.5)

            print("  → Selecionando card OFX Money")
            self._clicar_card_formato("OFX Money")
            time.sleep(0.8)  # aguarda sub-opções expandirem

            print("  → Selecionando 'Money 2000 ou superior'")
            # Tenta por texto exato (label ou radio próximo)
            opcao_encontrada = False
            for texto in ["Money 2000 ou superior", "Money 2000", "2000 ou superior"]:
                try:
                    el = self.driver.find_element(
                        By.XPATH,
                        f"//*[contains(normalize-space(text()), '{texto}') or contains(normalize-space(.), '{texto}')]"
                        f"[self::label or self::span or self::div or self::input]"
                    )
                    if el.is_displayed():
                        self.driver.execute_script("arguments[0].click();", el)
                        opcao_encontrada = True
                        time.sleep(0.4)
                        break
                except NoSuchElementException:
                    continue

            if not opcao_encontrada:
                print("  ⚠ Sub-opção Money 2000 não encontrada — tentando baixar assim mesmo")

            print("  → Clicando 'Baixar extrato' (OFX)")
            return self._clicar_botao_baixar_extrato()

        except TimeoutException as e:
            print(f"  ✗ Modal de download não abriu (OFX): {e}")
            return False

    def _fechar_modal_se_aberto(self):
        """Fecha o modal 'Baixar extrato' se ainda estiver visível (clica no X)."""
        try:
            from selenium.webdriver.common.keys import Keys
            # Tenta botão fechar (×) do modal
            fechar = self.driver.find_element(
                By.XPATH,
                "//button[@aria-label='Fechar' or @title='Fechar' or contains(@class,'close') or contains(@class,'fechar')]"
                "[ancestor::*[contains(@class,'modal') or contains(@class,'dialog')]]"
            )
            if fechar.is_displayed():
                self.driver.execute_script("arguments[0].click();", fechar)
                time.sleep(0.5)
                return
        except NoSuchElementException:
            pass
        # Fallback: pressiona ESC
        try:
            webdriver.ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.3)
        except Exception:
            pass

    def _mover_arquivo(self, extensao: str, nome_destino: str) -> bool:
        """
        Move o arquivo baixado (mais recente com a extensão) para output_dir
        com o nome correto.
        """
        arq = _aguardar_download(self.download_dir, "", extensao)
        if not arq:
            print(f"  ✗ Arquivo {extensao} não encontrado em {self.download_dir} após {DOWNLOAD_WAIT}s")
            return False

        destino = self.output_dir / f"{nome_destino}{extensao}"
        # Garante que não sobrescreve sem aviso
        if destino.exists():
            destino.unlink()
        shutil.move(str(arq), str(destino))
        print(f"  ✓ Salvo: {destino.name}")
        return True

    # ── Fluxo completo ─────────────────────────────────────────────────

    def extrair(self, empresa_nome: str) -> dict:
        """
        Executa o fluxo completo de extração para a empresa.
        Retorna: {"pdf": bool, "ofx": bool}
        """
        resultado = {"pdf": False, "ofx": False}

        data_inicio, data_fim, mm = _mes_anterior()
        nome_arq = _nome_arquivo(empresa_nome, mm)

        print(f"\n  [EXTRATO] {empresa_nome} — {data_inicio} a {data_fim}")

        # Passo 1: menu Conta Corrente
        if not self._clicar_menu_conta_corrente():
            return resultado

        # Passo 2: Consultar extrato e saldo
        if not self._clicar_consultar_extrato():
            return resultado

        # Passo 3: fecha banner (opcional)
        self._fechar_banner()

        # Passo 4: preenche datas
        if not self._preencher_datas(data_inicio, data_fim):
            return resultado

        # ── PDF ──────────────────────────────────────────────────────
        print("  [PDF] Abrindo modal de exportação...")
        if self._clicar_exportar():
            if self._selecionar_pdf_e_baixar():
                resultado["pdf"] = self._mover_arquivo(".pdf", nome_arq)
            # Fecha modal se ainda estiver aberto (X ou ESC)
            self._fechar_modal_se_aberto()
            time.sleep(1.5)

        # ── OFX ──────────────────────────────────────────────────────
        print("  [OFX] Abrindo modal de exportação...")
        if self._clicar_exportar():
            if self._selecionar_ofx_e_baixar():
                resultado["ofx"] = self._mover_arquivo(".ofx", nome_arq)
            self._fechar_modal_se_aberto()

        return resultado
