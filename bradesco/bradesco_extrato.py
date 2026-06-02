"""
bradesco_extrato.py — Emissão de extratos Bradesco Net Empresa PJ.

Para cada empresa já logada executa:
  1. Extrato Bancário CC (por conta): PDF + OFX
  2. Extrato de Investimentos (por conta / tipo / produto): PDF

Nomenclatura:
  CC    : 01 - EXTRATOS BANCÁRIOS CC - BRADESCO-{empresa} ({agencia}).pdf/ofx
  Invest: 01 - EXTRATOS INVESTIMENTOS - ({produto}) - BRADESCO-{empresa}.pdf  (em subpasta do tipo)

  agencia = texto antes do " | " no label da conta  (ex: "01999")
"""

import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException
)

from sheets_reader import Empresa

TIMEOUT = 25


# ── Helpers de módulo ─────────────────────────────────────────────────────────

def _aguardar_download(download_dir: Path, antes: set[Path], timeout: int = 90) -> Path | None:
    """Aguarda até aparecer um novo arquivo completamente baixado (sem .crdownload)."""
    fim = time.time() + timeout
    while time.time() < fim:
        agora     = {f for f in download_dir.iterdir() if f.is_file()}
        novos     = agora - antes
        parciais  = [f for f in novos if f.suffix in (".crdownload", ".tmp")]
        completos = [f for f in novos if f.suffix not in (".crdownload", ".tmp")]
        if completos and not parciais:
            time.sleep(0.5)  # garante que o arquivo foi totalmente escrito
            return max(completos, key=lambda f: f.stat().st_mtime)
        time.sleep(0.5)
    return None


def _dispensar_banner(driver: webdriver.Chrome):
    """
    Clica no jqmOverlay para fechar qualquer banner/modal pós-login.
    Aguarda o overlay desaparecer antes de prosseguir.
    """
    time.sleep(1.5)
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.jqmOverlay"))
        )
        driver.execute_script("document.querySelector('div.jqmOverlay').click();")
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.jqmOverlay"))
        )
        time.sleep(0.5)
    except TimeoutException:
        pass  # Sem overlay — OK


def _mes_anterior_index(sel: Select) -> int:
    """
    Retorna o índice do mês anterior (segunda opção com valor).
    A primeira opção com valor é o mês atual; a segunda é o mês anterior.
    """
    encontrados = []
    for i, opt in enumerate(sel.options):
        if opt.get_attribute("value"):
            encontrados.append(i)
            if len(encontrados) == 2:
                return i
    # Fallback: só existe um mês disponível
    return encontrados[0] if encontrados else 1


_MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

def _mes_numero(texto_opcao: str) -> int:
    """'2026 | Abril' → 4. Fallback: mês atual."""
    import datetime
    t = texto_opcao.lower()
    for nome, num in _MESES_PT.items():
        if nome in t:
            return num
    return datetime.date.today().month

def _sanitizar(nome: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '', nome).strip()


def _agencia_de_label(texto: str) -> str:
    """'01999 | 0037002-9' → '01999'"""
    return texto.split("|")[0].strip() if "|" in texto else texto[:6].strip()


# ── Classe principal ──────────────────────────────────────────────────────────

class BradescoExtrato:

    def __init__(self, driver: webdriver.Chrome, download_dir: Path):
        self.driver  = driver
        self.wait    = WebDriverWait(driver, TIMEOUT)
        self.dl_dir  = download_dir

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _entrar_pagina_central(self):
        """
        Muda o contexto Selenium para o frame 'paginaCentral' se ele existir.
        O conteúdo do portal Bradesco carrega nesse frame após clicar nos menus.
        """
        self.driver.switch_to.default_content()
        try:
            frame = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "frame[name='paginaCentral'], iframe[name='paginaCentral']")
                )
            )
            self.driver.switch_to.frame(frame)
        except TimeoutException:
            pass  # Portal sem frameset — conteúdo já está no contexto principal

    def _fechar_modal_salvar(self):
        js = """
function findAndClick(doc, depth) {
    if (depth > 5) return false;
    try {
        var el = doc.getElementById('formSalvarComo:btnEnviarFechar_X');
        if (el) { el.click(); return true; }
        var frames = doc.querySelectorAll('iframe, frame');
        for (var i = 0; i < frames.length; i++) {
            try {
                if (findAndClick(frames[i].contentDocument, depth + 1)) return true;
            } catch(e) {}
        }
    } catch(e) {}
    return false;
}
return findAndClick(document, 0);
"""
        try:
            self.driver.switch_to.default_content()
            self.driver.execute_script(js)
            time.sleep(0.8)
        except Exception:
            pass

    # JS reutilizado em todos os métodos de salvar
    _JS_CLICK_ID = """
var id = arguments[0];
function findAndClick(doc, depth) {
    if (depth > 5) return false;
    try {
        var el = doc.getElementById(id);
        if (el) { el.click(); return true; }
        var frames = doc.querySelectorAll('iframe, frame');
        for (var i = 0; i < frames.length; i++) {
            try { if (findAndClick(frames[i].contentDocument, depth + 1)) return true; } catch(e) {}
        }
    } catch(e) {}
    return false;
}
return findAndClick(document, 0);
"""

    def _abrir_modal_salvar(self) -> str | None:
        """
        Clica em 'Salvar como arquivo', aguarda o modal abrir e muda para
        default_content (onde o modal é acessível via JS).
        Retorna o handle da janela principal (ou None se falhou).
        """
        janelas_antes    = set(self.driver.window_handles)
        janela_principal = list(janelas_antes)[0]

        try:
            self.wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "a[onclick*='seiSalvarComo']")
                )
            ).click()
        except TimeoutException:
            print("    ✗ 'Salvar como arquivo' não encontrado")
            return None

        time.sleep(2)
        nova_janela = set(self.driver.window_handles) - janelas_antes
        if nova_janela:
            self.driver.switch_to.window(nova_janela.pop())
        else:
            self.driver.switch_to.default_content()

        return janela_principal

    def _clicar_id_no_modal(self, id_elem: str, timeout: int = 15) -> bool:
        """Clica num elemento pelo ID usando busca recursiva em todos os frames."""
        fim = time.time() + timeout
        while time.time() < fim:
            if self.driver.execute_script(self._JS_CLICK_ID, id_elem):
                return True
            time.sleep(0.5)
        return False

    def _salvar_pdf_e_ofx(self, nome: str, destino: Path):
        """
        Abre o modal UMA vez, baixa PDF e OFX em sequência e fecha o modal.
        Usado no extrato CC onde ambos os formatos ficam no mesmo painel.
        """
        janela_principal = self._abrir_modal_salvar()
        if not janela_principal:
            raise RuntimeError("Modal 'Salvar como arquivo' não abriu")

        # ── PDF ────────────────────────────────────────────────────────
        antes = {f for f in self.dl_dir.iterdir() if f.is_file()}
        print("    → Baixando PDF...")
        if not self._clicar_id_no_modal("formSalvarComo:pdf"):
            self._fechar_modal_salvar()
            self._limpar_modal(janela_principal)
            raise RuntimeError("Link PDF não encontrado no modal (15s)")
        arq = _aguardar_download(self.dl_dir, antes)
        self._mover(arq, destino / f"{nome}.pdf")

        # ── OFX (modal ainda aberto) ───────────────────────────────────
        antes = {f for f in self.dl_dir.iterdir() if f.is_file()}
        print("    → Baixando OFX...")
        if not self._clicar_id_no_modal("formSalvarComo:ofx", timeout=10):
            self._fechar_modal_salvar()
            self._limpar_modal(janela_principal)
            raise RuntimeError("Link OFX não encontrado no modal (10s)")
        arq = _aguardar_download(self.dl_dir, antes)
        self._mover(arq, destino / f"{nome}.ofx")

        # ── Fecha o modal UMA vez ──────────────────────────────────────
        self._fechar_modal_salvar()
        self._limpar_modal(janela_principal)

    def _salvar_formato(self, formato: str) -> Path | None:
        """
        Abre o modal, baixa UM formato (PDF ou OFX) e fecha o modal.
        Usado no extrato de investimentos (só PDF).
        """
        antes            = {f for f in self.dl_dir.iterdir() if f.is_file()}
        janela_principal = self._abrir_modal_salvar()
        if not janela_principal:
            return None

        id_link = f"formSalvarComo:{formato.lower()}"
        if not self._clicar_id_no_modal(id_link):
            print(f"    ✗ Link '{formato}' não encontrado em nenhum frame (15s)")
            self._fechar_modal_salvar()
            self._limpar_modal(janela_principal)
            return None

        print(f"    → Download {formato} iniciado...")
        arq = _aguardar_download(self.dl_dir, antes)
        time.sleep(0.5)
        self._fechar_modal_salvar()
        self._limpar_modal(janela_principal)
        return arq

    def _limpar_modal(self, janela_principal: str):
        """Fecha popup/janela secundária (se houver) e volta para paginaCentral."""
        try:
            if self.driver.current_window_handle != janela_principal:
                self.driver.close()
                self.driver.switch_to.window(janela_principal)
        except Exception:
            pass
        # Remove APENAS o overlay travado — NÃO remove jqmWindow pois
        # o formSalvarComo fica dentro dele e precisa ser reutilizado
        try:
            self.driver.switch_to.default_content()
            self.driver.execute_script(
                "document.querySelectorAll('div.jqmOverlay')"
                ".forEach(el => el.remove());"
            )
        except Exception:
            pass
        self._entrar_pagina_central()

    def _mover(self, origem: Path | None, destino: Path) -> bool:
        if not origem or not origem.exists():
            print(f"    ✗ Arquivo não encontrado para mover: {origem}")
            return False
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            destino.unlink()
        origem.rename(destino)
        print(f"    ✓ {destino.name}")
        return True

    def _opcoes_select(
        self,
        css: str,
        skip_vazio: bool = True,
        skip_texto: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        """Retorna [(value, text), ...] de um <select>, filtrando as indesejadas."""
        try:
            sel = Select(self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css))
            ))
            resultado = []
            for o in sel.options:
                val = o.get_attribute("value") or ""
                txt = o.text.strip()
                if skip_vazio and not val:
                    continue
                if skip_texto and any(s in txt.lower() for s in skip_texto):
                    continue
                resultado.append((val, txt))
            return resultado
        except TimeoutException:
            return []

    # ── Extrato CC ────────────────────────────────────────────────────────────

    def extratos_cc(self, empresa: Empresa, empresa_dir: Path):
        """Baixa PDF + OFX do Extrato Consolidado para cada conta CC."""
        print("\n  [CC] Acessando Saldos e Extratos...")
        _dispensar_banner(self.driver)

        # Menu Saldos e Extratos (fica no frame de nav; clica do contexto principal)
        self.driver.switch_to.default_content()
        try:
            self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.topmenu_S"))
            ).click()
            time.sleep(2)
        except TimeoutException:
            print("  ✗ Menu 'Saldos e Extratos' não encontrado")
            return

        # Entra no paginaCentral (onde o submenu carregou)
        self._entrar_pagina_central()

        # Extrato Consolidado
        try:
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "a[href*='extratoConsolidadoCC']")
                )
            ).click()
            time.sleep(2)
        except TimeoutException:
            print("  ✗ 'Extrato Consolidado' não encontrado")
            return

        # Aguarda a página do extrato carregar no mesmo frame
        self._entrar_pagina_central()

        # Radio "Por Mês"
        try:
            radio = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "input[id*='tipoConsultaPorMes1'][value='0'], "
                     "input[id*='tipoConsultaPorMes'][value='0']")
                )
            )
            if not radio.is_selected():
                self.driver.execute_script("arguments[0].click();", radio)
                time.sleep(0.5)
        except TimeoutException:
            print("  ✗ Rádio 'Por Mês' não encontrado")
            return

        # Select mês anterior
        try:
            sel_mes = Select(self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "select[id*='selectMesProgramado']")
                )
            ))
            idx_mes = _mes_anterior_index(sel_mes)
            sel_mes.select_by_index(idx_mes)
            texto_mes = sel_mes.options[idx_mes].text
            num_mes   = _mes_numero(texto_mes)
            print(f"  → Mês: {texto_mes} ({num_mes:02d})")
            time.sleep(0.5)
        except TimeoutException:
            print("  ✗ Select de mês não encontrado")
            return

        # Coleta labels e quantidade de contas
        try:
            labels_contas = self.driver.find_elements(
                By.CSS_SELECTOR, "table#contas label"
            )
            n_contas = len(labels_contas)
        except Exception:
            n_contas = 0

        print(f"  → {n_contas} conta(s) encontrada(s)")
        if n_contas == 0:
            print("  ✗ Nenhuma conta encontrada na lista")
            return

        for i in range(n_contas):
            # Re-lê label (pode ter mudado após Voltar)
            try:
                labels_contas = self.driver.find_elements(
                    By.CSS_SELECTOR, "table#contas label"
                )
                texto_conta = labels_contas[i].text.strip() if i < len(labels_contas) else f"Conta{i+1}"
            except Exception:
                texto_conta = f"Conta{i+1}"

            agencia = _agencia_de_label(texto_conta)
            print(f"\n  [CC] Conta {i+1}/{n_contas}: {texto_conta}")

            # Desmarca "Todas as contas"
            try:
                cb_todas = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "input[title*='todas as contas'], input[name*='_id73']"
                )
                if cb_todas.is_selected():
                    self.driver.execute_script("arguments[0].click();", cb_todas)
                    time.sleep(0.2)
            except NoSuchElementException:
                pass

            # Desmarca todas as contas individuais
            for cb in self.driver.find_elements(
                By.CSS_SELECTOR, "table#contas input[name='contas']"
            ):
                if cb.is_selected():
                    self.driver.execute_script("arguments[0].click();", cb)
                    time.sleep(0.15)

            # Marca somente esta conta
            cbs = self.driver.find_elements(
                By.CSS_SELECTOR, "table#contas input[name='contas']"
            )
            if i < len(cbs):
                self.driver.execute_script("arguments[0].click();", cbs[i])
                time.sleep(0.3)

            # Buscar
            try:
                self.wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR,
                         "input[title='Buscar'], "
                         "input[type='image'][class*='bt_buscar'], "
                         "input[type='submit'][value='Buscar']")
                    )
                ).click()
                time.sleep(4)
            except TimeoutException:
                print("    ✗ Botão 'Buscar' não encontrado")
                continue

            # Expande "Últimos Lançamentos"
            try:
                el = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "span[title*='Últimos Lançamentos'], "
                    "span.expansivel.fechado:not(.invisivelImpressao)"
                )
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(0.8)
            except NoSuchElementException:
                pass

            # Expande "Saldos Invest Fácil / Plus"
            try:
                el = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "span[title*='Saldos Invest'], "
                    "span.expansivel.invisivelImpressao.fechado"
                )
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(0.8)
            except NoSuchElementException:
                pass

            # Nome base do arquivo
            nome = _sanitizar(
                f"{num_mes:02d} - EXTRATOS BANCÁRIOS CC ({agencia}) - BANCO BRADESCO - {empresa.nome}"
            )

            # PDF + OFX em sessão única de modal (abre → baixa PDF → baixa OFX → fecha)
            try:
                self._salvar_pdf_e_ofx(nome, empresa_dir)
            except Exception as e:
                print(f"    ✗ Conta {texto_conta} — erro ao baixar ({e}); pulando para a próxima")
                try:
                    self._limpar_modal(list(self.driver.window_handles)[0])
                except Exception:
                    pass
                continue

            # Voltar (se não for a última conta)
            if i < n_contas - 1:
                try:
                    btn_voltar = self.driver.find_element(
                        By.CSS_SELECTOR,
                        "a.lnkVoltar, a[title='Voltar'][id*='_id2140']"
                    )
                    btn_voltar.click()
                    time.sleep(2)
                    self._entrar_pagina_central()
                    # Re-aplica rádio e mês
                    radio = self.driver.find_element(
                        By.CSS_SELECTOR,
                        "input[id*='tipoConsultaPorMes1'][value='0'], "
                        "input[id*='tipoConsultaPorMes'][value='0']"
                    )
                    if not radio.is_selected():
                        self.driver.execute_script("arguments[0].click();", radio)
                        time.sleep(0.5)
                    sel_mes = Select(self.driver.find_element(
                        By.CSS_SELECTOR, "select[id*='selectMesProgramado']"
                    ))
                    sel_mes.select_by_index(idx_mes)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"    ✗ Erro ao voltar para próxima conta: {e}")

    # ── Extrato Investimentos ─────────────────────────────────────────────────

    def extratos_investimentos(self, empresa: Empresa, empresa_dir: Path):
        """Baixa PDF de cada produto de investimento (por conta / tipo / produto)."""
        print("\n  [INVEST] Acessando Investimentos...")
        _dispensar_banner(self.driver)

        # Menu Investimentos (frame de nav)
        self.driver.switch_to.default_content()
        try:
            self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.topmenu_I"))
            ).click()
            time.sleep(2)
        except TimeoutException:
            print("  ✗ Menu 'Investimentos' não encontrado")
            return

        # Entra no paginaCentral (submenu carregou aqui)
        self._entrar_pagina_central()

        # Saldo / Extrato
        try:
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "a[href*='extratoinvestimentos']")
                )
            ).click()
            time.sleep(2)
        except TimeoutException:
            print("  ✗ 'Saldo / Extrato' não encontrado")
            return

        self._entrar_pagina_central()

        # Lê contas do sexyCombo
        contas = self._ler_sexy_combo()
        print(f"  → {len(contas)} conta(s) de investimento")

        num_mes_invest = None   # preenchido na primeira conta processada
        algum_pdf_baixado = False

        for idx_conta, conta_texto in enumerate(contas):
            agencia = _agencia_de_label(conta_texto)
            # Subpasta por conta dentro da pasta da empresa (evita misturar contas)
            conta_dir = empresa_dir / _sanitizar(agencia) if len(contas) > 1 else empresa_dir
            print(f"\n  [INVEST] Conta {idx_conta+1}/{len(contas)}: {conta_texto}")

            self._escolher_sexy_combo(idx_conta)
            time.sleep(1)

            idx_mes = self._configurar_mes_invest()

            # Captura o número do mês para o nome dos arquivos (apenas na 1ª conta)
            if num_mes_invest is None:
                try:
                    _sel_m = Select(self.driver.find_element(
                        By.CSS_SELECTOR, "select[id*='comboPeriodoMes']"
                    ))
                    num_mes_invest = _mes_numero(_sel_m.options[idx_mes].text)
                except Exception:
                    import datetime
                    num_mes_invest = datetime.date.today().month

            # Tipos de investimento (skip Selecione)
            tipos = self._opcoes_select(
                "select[id*='comboTipoInvestimento']",
                skip_vazio=True,
                skip_texto=["selecione"],
            )
            print(f"  → {len(tipos)} tipo(s) de investimento")

            for _, tipo_texto in tipos:
                print(f"\n    [TIPO] {tipo_texto}")

                # Seleciona tipo por TEXTO (o value é encriptado e muda após Voltar)
                Select(self.driver.find_element(
                    By.CSS_SELECTOR, "select[id*='comboTipoInvestimento']"
                )).select_by_visible_text(tipo_texto)
                time.sleep(1.5)

                # Produtos (skip Selecione + Todos)
                produtos = self._opcoes_select(
                    "select[id*='comboProduto']",
                    skip_vazio=True,
                    skip_texto=["selecione", "todos"],
                )
                print(f"    → {len(produtos)} produto(s)")

                for _, prod_texto in produtos:
                    print(f"\n      [PROD] {prod_texto}")

                    # Re-seleciona tipo por texto (form reseta após Voltar)
                    Select(self.driver.find_element(
                        By.CSS_SELECTOR, "select[id*='comboTipoInvestimento']"
                    )).select_by_visible_text(tipo_texto)

                    # Aguarda a opção do produto aparecer no combo (carregamento assíncrono)
                    WebDriverWait(self.driver, 15).until(
                        lambda d: any(
                            o.text.strip() == prod_texto
                            for o in Select(d.find_element(
                                By.CSS_SELECTOR, "select[id*='comboProduto']"
                            )).options
                        )
                    )

                    # Seleciona produto por texto
                    Select(self.driver.find_element(
                        By.CSS_SELECTOR, "select[id*='comboProduto']"
                    )).select_by_visible_text(prod_texto)
                    time.sleep(0.5)

                    # Avançar
                    try:
                        self.wait.until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR,
                                 "input.consultarExtrato[title='Avançar'], "
                                 "input[title='Avançar'].bt_avancar")
                            )
                        ).click()
                        time.sleep(3)
                    except TimeoutException:
                        print("      ✗ 'Avançar' não encontrado — pulando produto")
                        continue

                    # ── Verifica estado da página após Avançar ────────────────
                    # Correto  → chegou na tela de extrato (tem "Salvar como arquivo"
                    #             ou span.expansivel)
                    # Sem dados → ainda está no formulário (comboTipoInvestimento
                    #             presente) ou botão não navegou
                    # Desconhecido → nem um nem outro

                    _no_extrato = bool(
                        self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "a[onclick*='seiSalvarComo'], span.expansivel[tabindex]"
                        )
                    )
                    _no_form = bool(
                        self.driver.find_elements(
                            By.CSS_SELECTOR, "select[id*='comboTipoInvestimento']"
                        )
                    )

                    if not _no_extrato:
                        # Ainda no form ou estado desconhecido — sem dados / sem efeito
                        print(f"      → Sem dados para '{prod_texto}' (Avançar sem efeito) — pulando")
                        if _no_form:
                            # Ainda no formulário: não precisa Voltar, só continua
                            continue
                        # Estado desconhecido: tenta recuperar antes de continuar
                        self._entrar_pagina_central()
                        try:
                            self._escolher_sexy_combo(idx_conta)
                            time.sleep(0.8)
                            self._configurar_mes_invest(idx_mes)
                        except Exception:
                            pass
                        continue

                    # Chegou no extrato — expande todas as linhas
                    try:
                        exps = self.wait.until(
                            EC.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, "span.expansivel[tabindex]")
                            )
                        )
                        for exp in exps:
                            try:
                                self.driver.execute_script("arguments[0].click();", exp)
                                time.sleep(0.6)
                            except Exception:
                                pass
                    except TimeoutException:
                        pass

                    # PDF — subpasta = tipo de investimento (dentro da pasta da conta)
                    tipo_dir = conta_dir / _sanitizar(tipo_texto)
                    nome = _sanitizar(
                        f"{num_mes_invest:02d} - EXTRATOS INVESTIMENTOS - ({prod_texto}) - BRADESCO-{empresa.nome}"
                    )
                    print(f"      → Baixando PDF...")
                    arq = self._salvar_formato("PDF")
                    if self._mover(arq, tipo_dir / f"{nome}.pdf"):
                        algum_pdf_baixado = True

                    # Voltar — tenta múltiplos seletores e fallback driver.back()
                    _voltou = False
                    for _sel_voltar in [
                        "input[title='Voltar'].bt_voltar",
                        "input[id*='_id642'][title='Voltar']",
                        "input[type='submit'][title='Voltar']",
                        "input[type='button'][title='Voltar']",
                        "a[title='Voltar']",
                        "button[title='Voltar']",
                    ]:
                        try:
                            btn = self.driver.find_element(By.CSS_SELECTOR, _sel_voltar)
                            self.driver.execute_script("arguments[0].click();", btn)
                            time.sleep(2)
                            _voltou = True
                            break
                        except Exception:
                            continue

                    if not _voltou:
                        # Fallback: navega com driver.back()
                        try:
                            self.driver.back()
                            time.sleep(2)
                            _voltou = True
                            print(f"      ⚠ Voltou via browser.back()")
                        except Exception as e:
                            print(f"      ✗ Não foi possível voltar: {e}")

                    # Re-entra no frame e restaura conta + mês
                    self._entrar_pagina_central()
                    try:
                        self._escolher_sexy_combo(idx_conta)
                        time.sleep(0.8)
                        self._configurar_mes_invest(idx_mes)
                    except Exception:
                        pass

                    if not _voltou:
                        # Formulário inacessível — verifica antes de abandonar
                        _form_ok = False
                        try:
                            self.driver.find_element(
                                By.CSS_SELECTOR, "select[id*='comboTipoInvestimento']"
                            )
                            _form_ok = True
                        except Exception:
                            pass
                        if not _form_ok:
                            print(f"      ✗ Formulário inacessível — pulando produtos restantes deste tipo")
                            break

        # Se nenhum PDF foi baixado, registra arquivo marcador
        if not algum_pdf_baixado:
            import datetime
            mes = num_mes_invest or (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).month
            nome_sem = _sanitizar(
                f"{mes:02d} - EXTRATOS INVESTIMENTOS - (SEM INVESTIMENTO)"
                f" - BRADESCO-{empresa.nome}"
            )
            arq_sem = empresa_dir / f"{nome_sem}.txt"
            arq_sem.write_text("Sem investimentos no período.", encoding="utf-8")
            print(f"  → Sem investimentos — {arq_sem.name}")

    # ── Helpers SexyCombo / Mês ───────────────────────────────────────────────

    # JS que busca select#contaDebito em todos os frames recursivamente
    # (mesma técnica do _JS_CLICK_ID — funciona independente do frame ativo)
    _JS_LER_CONTAS = """
function lerOpcoes(doc, depth) {
    if (depth > 5) return null;
    try {
        var sel = doc.getElementById('contaDebito');
        if (sel && sel.options && sel.options.length > 0) {
            var lista = [];
            for (var i = 0; i < sel.options.length; i++) {
                var t = (sel.options[i].text || '').trim();
                if (t) lista.push(t);
            }
            if (lista.length > 0) return lista;
        }
    } catch(e) {}
    try {
        var frames = doc.querySelectorAll('frame, iframe');
        for (var i = 0; i < frames.length; i++) {
            try {
                var r = lerOpcoes(frames[i].contentDocument, depth + 1);
                if (r) return r;
            } catch(e) {}
        }
    } catch(e) {}
    return null;
}
return lerOpcoes(document, 0);
"""

    def _ler_sexy_combo(self) -> list[str]:
        """
        Lê as contas do sexyCombo usando busca JS recursiva a partir de
        default_content — independe de qual frame o select está.
        """
        fim = time.time() + 10
        while time.time() < fim:
            try:
                self.driver.switch_to.default_content()
                textos = self.driver.execute_script(self._JS_LER_CONTAS)
                if textos:
                    self._entrar_pagina_central()
                    return textos
            except Exception:
                pass
            time.sleep(0.5)

        # Re-entra no frame para o código seguinte não quebrar
        self._entrar_pagina_central()
        return [""]

    def _escolher_sexy_combo(self, idx: int):
        """
        Seleciona a conta idx no sexyCombo.
        Sempre abre o dropdown antes de clicar no li — garante que os eventos
        do widget disparam e o formulário recarrega os dados da conta correta.
        Verifica após a seleção se o texto do input mudou para a conta esperada.
        """
        try:
            items = self.driver.find_elements(By.CSS_SELECTOR, "div.list-wrapper li")
        except Exception:
            return

        if len(items) <= 1:
            return  # conta única

        if idx >= len(items):
            return

        texto_esperado = ""
        try:
            texto_esperado = items[idx].text.strip()
        except Exception:
            pass

        # Abre o dropdown com click real no input (garante eventos do widget)
        try:
            inp = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input#contaDebito__sexyCombo")
                )
            )
            inp.click()
            time.sleep(0.6)
        except Exception:
            pass

        # Clica no li desejado (tenta click real, fallback JS)
        try:
            items = self.driver.find_elements(By.CSS_SELECTOR, "div.list-wrapper li")
            if idx < len(items):
                try:
                    items[idx].click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", items[idx])
        except Exception as e:
            print(f"    ✗ sexyCombo clique: {e}")
            return

        time.sleep(1.0)  # aguarda o form recarregar para a conta selecionada

        # Verifica se a conta foi realmente trocada
        if texto_esperado:
            try:
                inp_val = self.driver.find_element(
                    By.CSS_SELECTOR, "input#contaDebito__sexyCombo"
                ).get_attribute("value") or ""
                agencia_esp = texto_esperado.split("|")[0].strip()
                if agencia_esp and agencia_esp not in inp_val:
                    print(f"    ⚠ sexyCombo: esperado '{texto_esperado}', atual '{inp_val}' — retentando")
                    # Retenta uma vez
                    try:
                        inp = self.driver.find_element(
                            By.CSS_SELECTOR, "input#contaDebito__sexyCombo"
                        )
                        inp.click()
                        time.sleep(0.6)
                        items = self.driver.find_elements(
                            By.CSS_SELECTOR, "div.list-wrapper li"
                        )
                        if idx < len(items):
                            try:
                                items[idx].click()
                            except Exception:
                                self.driver.execute_script(
                                    "arguments[0].click();", items[idx]
                                )
                        time.sleep(1.0)
                    except Exception:
                        pass
            except Exception:
                pass

    def _configurar_mes_invest(self, idx: int | None = None) -> int:
        """
        Seleciona rádio 'Por Mês' e mês anterior no formulário de investimentos.
        Retorna o índice do mês selecionado.
        """
        try:
            radio = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "input[id*='tipoConsultaPorMes'][value='mes'], "
                     "input[id*='tipoConsultaPorMes']")
                )
            )
            if not radio.is_selected():
                self.driver.execute_script("arguments[0].click();", radio)
                time.sleep(0.5)
        except TimeoutException:
            pass

        try:
            sel_el = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "select[id*='comboPeriodoMes']")
                )
            )
            sel_mes = Select(sel_el)
            if idx is None:
                idx = _mes_anterior_index(sel_mes)
            sel_mes.select_by_index(idx)
            time.sleep(0.5)
        except TimeoutException:
            idx = idx if idx is not None else 1

        return idx if idx is not None else 1
