"""
Login Bradesco Net Empresa PJ.

Fluxo:
  1. Abre https://www.ne12.bradesconetempresa.b.br/ibpjlogin/login.jsf
  2. Seleciona radio "Usuário e Senha" (rdoTipoAcesso02)
  3. Preenche usuário  (identificationForm:txtUsuario)
  4. Preenche senha    (identificationForm:txtSenha)
  5. Clica reCAPTCHA checkbox (dentro do iframe)
  6. Aguarda verificação do reCAPTCHA
  7. Clica Avançar    (identificationForm:botaoAvancar)
  8. Confirma login pela mudança de URL
"""

import io
import os
import re
import time
import base64
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

from sheets_reader import Empresa

load_dotenv()

BRADESCO_URL = os.getenv("BRADESCO_URL", "https://www.ne12.bradesconetempresa.b.br/ibpjlogin/login.jsf")
TIMEOUT      = 25


def criar_driver(headless: bool = False, download_dir: str | None = None) -> webdriver.Chrome:
    opcoes = Options()
    if headless:
        opcoes.add_argument("--headless=new")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])
    opcoes.add_experimental_option("useAutomationExtension", False)
    opcoes.add_experimental_option("detach", True)
    opcoes.add_argument("--window-size=1366,768")
    opcoes.add_argument("--start-maximized")

    if download_dir:
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        prefs = {
            "download.default_directory":        str(download_dir),
            "download.prompt_for_download":      False,
            "download.directory_upgrade":        True,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
        }
    else:
        prefs = {
            "download.prompt_for_download": False,
            "download.directory_upgrade":   True,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
        }
    opcoes.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=opcoes)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ── reCAPTCHA ─────────────────────────────────────────────────────────

def verificar_sessao_encerrada(driver: webdriver.Chrome) -> bool:
    """
    Retorna True se o modal 'Sessão encerrada' estiver visível.
    Fecha o modal clicando em btnFecharModal antes de retornar.
    """
    try:
        modal = driver.find_element(By.ID, "modalLogin")
        if modal.is_displayed():
            print("  ⚠  Modal 'Sessão encerrada' detectado — fechando")
            try:
                driver.find_element(By.ID, "btnFecharModal").click()
                time.sleep(1.0)
            except Exception:
                pass
            return True
    except NoSuchElementException:
        pass
    return False


# Descrições visuais por categoria para melhorar acurácia do Claude
_DESC_CAPTCHA: dict[str, str] = {
    "carros":            "veículos com 4 rodas e cabine fechada (sedãs, SUVs, caminhonetes)",
    "motocicletas":      "veículos com 2 rodas SEM cabine fechada — moto, scooter, guidão visível",
    "bicicletas":        "veículos com 2 rodas, sem motor e sem cabine, com pedais",
    "semáforos":         "postes com 3 luzes empilhadas verticalmente (vermelho/amarelo/verde)",
    "ônibus":            "veículos grandes e compridos com muitas janelas laterais",
    "hidrantes":         "cilindros metálicos baixos na calçada com conexões de mangueira",
    "faixas de pedestres": "listras brancas paralelas pintadas no asfalto da rua",
    "pontes":            "estruturas que cruzam rios ou vales",
    "barcos":            "embarcações flutuando em água",
    "aviões":            "aeronaves com asas fixas",
    "táxis":             "carros com identificação de táxi ou cor amarela típica",
    "caminhões":         "veículos de carga grandes com cabine e carroceria/baú",
    "trens":             "vagões sobre trilhos",
    "palmeiras":         "árvores altas com folhas longas no topo",
    "montanhas":         "elevações naturais do terreno",
    "escadas":           "estruturas com degraus para subir ou descer",
    "piscinas":          "reservatórios retangulares de água para natação",
    "parquímetros":      "postes de pagamento de estacionamento na calçada",
    "placas de trânsito": "sinais de trânsito em postes (PARE, velocidade, etc.)",
    "caixas de correio": "caixas para receber correspondência",
}

_SELETOR_BFRAME = 'iframe[src*="bframe"], iframe[title*="expira em dois minutos"]'


class _Retry(Exception):
    """Sinal interno para reiniciar ciclo do loop."""


def _resolver_captcha_imagem(driver: webdriver.Chrome) -> bool:
    """
    Resolve desafio de imagem reCAPTCHA usando Claude Vision.
    Suporta grade estática e grade dinâmica (tiles substituídas após cada clique).
    """
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, _SELETOR_BFRAME))
        )
    except TimeoutException:
        return True  # Sem desafio — checkbox foi suficiente

    print("  → Desafio de imagem detectado — usando Claude Vision (sonnet)")
    client = anthropic.Anthropic()
    inicio = time.time()
    tentativa = 0

    # ── Carrega fonte para anotação ───────────────────────────────────
    _font = None
    for _fp in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibrib.ttf", "C:/Windows/Fonts/verdana.ttf"]:
        try:
            _font = ImageFont.truetype(_fp, size=18)
            break
        except Exception:
            pass

    # ── Função interna: screenshot + grade anotada + Claude ──────────
    def _pedir_claude(iframe_el, instrucao: str, descricao: str) -> list[int]:
        """
        Captura a grade inteira, desenha número em cada célula e envia
        uma única imagem anotada ao Claude — preserva contexto visual.
        """
        driver.switch_to.frame(iframe_el)
        tiles = driver.find_elements(By.CSS_SELECTOR, "td.rc-imageselect-tile")
        n = len(tiles)
        rects = [
            driver.execute_script("return arguments[0].getBoundingClientRect()", t)
            for t in tiles
        ]
        driver.switch_to.default_content()

        time.sleep(0.3)
        dpr    = driver.execute_script("return window.devicePixelRatio") or 1
        fr     = driver.execute_script("return arguments[0].getBoundingClientRect()", iframe_el)
        fx, fy = int(fr["x"] * dpr), int(fr["y"] * dpr)
        fw, fh = int(fr["width"] * dpr), int(fr["height"] * dpr)
        popup  = Image.open(io.BytesIO(driver.get_screenshot_as_png())).crop((fx, fy, fx+fw, fy+fh))

        # Desenha número no canto superior esquerdo de cada célula
        anotada = popup.copy()
        draw    = ImageDraw.Draw(anotada)
        for i, r in enumerate(rects, 1):
            px, py = int(r["x"] * dpr), int(r["y"] * dpr)
            pw, ph = int(r["width"] * dpr), int(r["height"] * dpr)
            label  = str(i)
            lw     = len(label) * 11 + 6
            lh     = 22
            draw.rectangle([px, py, px+pw-1, py+ph-1], outline=(255, 50, 50), width=3)
            draw.rectangle([px+2, py+2, px+2+lw, py+2+lh], fill=(255, 255, 255))
            draw.text((px+5, py+4), label, fill=(200, 0, 0), font=_font)

        buf = io.BytesIO()
        anotada.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=80,
            system=(
                "You are a precise reCAPTCHA image solver. "
                "The grid image has red-numbered labels on each cell. "
                "Output ONLY comma-separated cell numbers that match (e.g. '1,4,7'). "
                "If none match, output '0'. Include ALL matching cells — do not miss any. "
                "NO words, NO explanation."
            ),
            messages=[{"role": "user", "content": [
                {"type": "text", "text": (
                    f'Selecione TODAS as células que contêm "{instrucao}" ({descricao}). '
                    f'Os números estão no canto superior esquerdo de cada célula em vermelho.'
                )},
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": img_b64,
                }},
                {"type": "text", "text": (
                    f'Quais células contêm "{instrucao}"? '
                    f'Responda SOMENTE números separados por vírgula. Se nenhuma: 0'
                )},
            ]}],
        )
        resultado = resp.content[0].text.strip()
        if resultado == "0":
            return []
        vistos, posicoes = set(), []
        for m in re.findall(r'\d+', resultado):
            v = int(m)
            if 1 <= v <= n and v not in vistos:
                posicoes.append(v); vistos.add(v)
        return posicoes

    # ── Função interna: clica tiles ───────────────────────────────────
    def _clicar(posicoes: list[int]) -> bool:
        """Clica tiles. Retorna False se o iframe sumiu (desafio resolvido)."""
        try:
            fr = driver.find_element(By.CSS_SELECTOR, _SELETOR_BFRAME)
            driver.switch_to.frame(fr)
            tiles = driver.find_elements(By.CSS_SELECTOR, "td.rc-imageselect-tile")
            for pos in posicoes:
                if 1 <= pos <= len(tiles):
                    try:
                        tiles[pos - 1].click()
                        print(f"    → clicou {pos}")
                        time.sleep(0.6)
                    except Exception as e:
                        print(f"    ✗ {pos}: {e}")
            return True
        except (NoSuchElementException, StaleElementReferenceException):
            driver.switch_to.default_content()
            print("  ✓ Iframe sumiu durante clique — desafio resolvido")
            return False

    # ── Loop principal ────────────────────────────────────────────────
    while time.time() - inicio < 115:
        tentativa += 1
        driver.switch_to.default_content()

        try:
            iframe_el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _SELETOR_BFRAME))
            )
        except TimeoutException:
            print("  ✓ Desafio resolvido (iframe sumiu)")
            return True

        # Lê instrução
        driver.switch_to.frame(iframe_el)
        try:
            instrucao = driver.find_element(By.CSS_SELECTOR,
                ".rc-imageselect-desc-no-canonical strong, "
                ".rc-imageselect-desc strong, "
                ".rc-imageselect-instructions strong").text.strip()
        except NoSuchElementException:
            try:
                instrucao = driver.find_element(By.CSS_SELECTOR,
                    ".rc-imageselect-desc-no-canonical, .rc-imageselect-desc").text.strip()
            except NoSuchElementException:
                instrucao = "imagens correspondentes"
        n_tiles = len(driver.find_elements(By.CSS_SELECTOR, "td.rc-imageselect-tile"))
        driver.switch_to.default_content()

        grade     = "3x3" if n_tiles == 9 else ("4x4" if n_tiles == 16 else f"{n_tiles} células")
        descricao = _DESC_CAPTCHA.get(instrucao.lower(), instrucao)
        decorrido = int(time.time() - inicio)
        print(f"  → [{decorrido}s] Instrução: '{instrucao}' | {grade} | tentativa {tentativa}")

        # Análise inicial
        try:
            posicoes = _pedir_claude(iframe_el, instrucao, descricao)
        except Exception as e:
            print(f"  ✗ Erro Claude: {e} — aguardando 3s")
            time.sleep(3)
            continue

        print(f"  → Claude inicial: {posicoes or 'nenhuma'}")

        # ── Suporte a grade estática e dinâmica ───────────────────────────────
        # Estática : tile clicada fica destacada (rc-imageselect-tileselected) —
        #            clica todas as da fila e vai direto para Verificar.
        # Dinâmica : tile clicada é substituída por nova imagem — verifica se a
        #            nova também corresponde e clica se necessário, repetindo até
        #            não restar nenhuma correspondência.
        fila: list[int] = list(posicoes)
        tipo_dinamico: bool | None = None  # detectado após o primeiro clique
        cliques_por_pos: dict[int, int] = {}  # limita re-cliques na dinâmica

        def _poll_tile_pronta(pos_clicada: int, max_espera: float) -> bool:
            """
            Poll a cada 0,15s até a tile definir seu estado.
            Retorna True  = estática  (rc-imageselect-tileselected apareceu).
            Retorna False = dinâmica  (loading concluído ou timeout).
            Sai assim que sabe — não espera o tempo todo.
            """
            loading_visto = False
            fim = time.time() + max_espera
            time.sleep(0.1)
            while time.time() < fim:
                try:
                    fr = driver.find_element(By.CSS_SELECTOR, _SELETOR_BFRAME)
                    driver.switch_to.frame(fr)
                    tls = driver.find_elements(By.CSS_SELECTOR, "td.rc-imageselect-tile")
                    cls = tls[pos_clicada - 1].get_attribute("class") or "" if pos_clicada <= len(tls) else ""
                    driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
                    return False  # iframe sumiu → dinâmico
                if "rc-imageselect-tileselected" in cls:
                    return True   # estático — tile selecionada
                if "rc-imageselect-dynamic-selected" in cls:
                    loading_visto = True
                elif loading_visto:
                    return False  # dinâmico — loading concluído
                time.sleep(0.15)
            return False  # timeout → assume dinâmico

        while fila and (time.time() - inicio < 110):
            pos = fila.pop(0)
            cliques_por_pos[pos] = cliques_por_pos.get(pos, 0) + 1
            if not _clicar([pos]):
                return True  # iframe sumiu — desafio resolvido

            driver.switch_to.default_content()
            # Detecta tipo (1ª vez, max 1,5s) ou aguarda loading dinâmico (max 3s)
            # — sai cedo se a tile responder antes do limite
            tile_estatica = _poll_tile_pronta(pos, 3.0 if tipo_dinamico else 1.5)

            if tipo_dinamico is None:
                tipo_dinamico = not tile_estatica
                print(f"  → Grade {'DINÂMICA' if tipo_dinamico else 'ESTÁTICA'} detectada")

            if not tipo_dinamico:
                # Estática: clica o restante da fila sem re-analisar
                continue

            # Dinâmica: pausa curta para a imagem nova terminar de renderizar
            #           antes do screenshot — manter isso, só o loading foi acelerado
            time.sleep(0.5)

            # Re-analisa para capturar tiles substituídas que também correspondem
            try:
                iframe_el = driver.find_element(By.CSS_SELECTOR, _SELETOR_BFRAME)
            except NoSuchElementException:
                print("  ✓ Iframe sumiu após clique — desafio resolvido")
                return True

            try:
                novas = _pedir_claude(iframe_el, instrucao, descricao)
            except Exception as e:
                print(f"  ✗ Erro Claude: {e}")
                break

            for c in novas:
                # Máx 3 cliques na mesma posição — evita loop infinito de substituições
                if c not in fila and cliques_por_pos.get(c, 0) < 3:
                    fila.append(c)

            if fila:
                print(f"  → {len(fila)} tile(s) ainda corresponde(m): {fila}")
            else:
                print(f"  → Nenhuma correspondência — pronto para Verificar")

        # ── Verifica erros → Verificar ────────────────────────────────
        driver.switch_to.default_content()
        try:
            iframe_el = driver.find_element(By.CSS_SELECTOR, _SELETOR_BFRAME)
            driver.switch_to.frame(iframe_el)
        except (NoSuchElementException, StaleElementReferenceException):
            return True

        try:
            for sel in [".rc-imageselect-error-select-more",
                        ".rc-imageselect-error-dynamic-more",
                        ".rc-imageselect-incorrect-response"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        print("  ⚠  Seleção incorreta — nova tentativa")
                        driver.switch_to.default_content()
                        time.sleep(1.5)
                        raise _Retry()
                except NoSuchElementException:
                    pass
        except _Retry:
            continue

        try:
            driver.find_element(By.ID, "recaptcha-verify-button").click()
            print("  → Verificar clicado")
        except NoSuchElementException:
            pass

        driver.switch_to.default_content()
        time.sleep(3)

        try:
            WebDriverWait(driver, 5).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, _SELETOR_BFRAME))
            )
            print("  ✓ Desafio resolvido (bframe sumiu)")
            return True
        except TimeoutException:
            pass

        # 7 tentativas sem sucesso → recarrega para novo desafio
        if tentativa >= 7:
            print("  ⚠  7 tentativas sem sucesso — recarregando...")
            driver.switch_to.default_content()
            driver.get(driver.current_url)
            try:
                driver.switch_to.alert().accept()
            except Exception:
                pass
            time.sleep(3)
            tentativa = 0

            # Verifica se permaneceu na área do reCAPTCHA (checkbox visível)
            try:
                fr_anc = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'iframe[src*="recaptcha"][src*="anchor"]')
                    )
                )
                # Ainda no reCAPTCHA — clica o checkbox e continua sem voltar ao login
                driver.switch_to.frame(fr_anc)
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, ".recaptcha-checkbox-border")
                    )
                ).click()
                print("  → Checkbox reCAPTCHA reclicado após reload")
                driver.switch_to.default_content()
                time.sleep(2.5)
                continue  # retoma o loop externo com novo desafio
            except TimeoutException:
                # Voltou para o login — login_completo vai reiniciar
                driver.switch_to.default_content()
                return False

    driver.switch_to.default_content()
    print("  ✗ Tempo esgotado (120s)")
    return False




def _clicar_recaptcha(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
    """
    Clica o checkbox reCAPTCHA e, se aparecer desafio de imagem,
    resolve automaticamente com Claude Vision.
    """
    try:
        # Localiza iframe do checkbox (anchor) — api2 ou enterprise
        iframe_anchor = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'iframe[src*="recaptcha"][src*="anchor"]')
            )
        )
        driver.switch_to.frame(iframe_anchor)

        checkbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".recaptcha-checkbox-border"))
        )
        checkbox.click()
        print("  → reCAPTCHA checkbox clicado")
        driver.switch_to.default_content()
        time.sleep(2.5)

        # Sempre verifica se apareceu desafio de imagem (bframe)
        # Não usar URL como atalho — o reCAPTCHA aparece numa página já diferente de login.jsf
        ok = _resolver_captcha_imagem(driver)
        if ok:
            print("  ✓ reCAPTCHA OK")
        else:
            print("  ✗ reCAPTCHA falhou")
        return ok

    except TimeoutException:
        driver.switch_to.default_content()
        print("  ✗ reCAPTCHA iframe não encontrado")
        return False


# ── Sessão ────────────────────────────────────────────────────────────

class BradescoSession:

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.wait   = WebDriverWait(driver, TIMEOUT)

    def login_completo(self, empresa: Empresa, _tentativa: int = 1, _captcha_retry: int = 0) -> bool:
        try:
            # Etapa 1 — Abre o site
            print(f"  → Abrindo {BRADESCO_URL}" + (f" (tentativa {_tentativa})" if _tentativa > 1 else ""))
            self.driver.get(BRADESCO_URL)
            time.sleep(3.0)

            # Etapa 2 — Seleciona "Usuário e Senha"
            radio = self.wait.until(
                EC.presence_of_element_located((By.ID, "rdoTipoAcesso02"))
            )
            if not radio.is_selected():
                self.driver.execute_script("arguments[0].click();", radio)
                print("  → Tipo acesso: Usuário e Senha")
                time.sleep(1.0)

            # Etapa 3 — Usuário
            campo_user = self.wait.until(
                EC.element_to_be_clickable(
                    (By.ID, "identificationForm:txtUsuario")
                )
            )
            campo_user.clear()
            campo_user.send_keys(empresa.usuario)
            print(f"  → Usuário: {empresa.usuario}")
            time.sleep(0.3)

            # Etapa 4 — Senha
            campo_senha = self.driver.find_element(
                By.ID, "identificationForm:txtSenha"
            )
            campo_senha.clear()
            campo_senha.send_keys(empresa.senha)
            print("  → Senha: ***")
            time.sleep(0.3)

            # Etapa 5 — Lembrar acesso
            try:
                chk = self.driver.find_element(By.ID, "chkRepetir")
                if not chk.is_selected():
                    self.driver.execute_script("arguments[0].click();", chk)
                    print("  → Lembrar acesso marcado")
                    time.sleep(0.5)
            except NoSuchElementException:
                pass

            # Etapa 6 — Avançar
            avancar = self.wait.until(
                EC.element_to_be_clickable(
                    (By.ID, "identificationForm:botaoAvancar")
                )
            )
            self.driver.execute_script("arguments[0].click();", avancar)
            print("  → Avançar clicado")
            time.sleep(3.0)

            # Modal "Sessão encerrada" → fecha e retenta uma vez
            if verificar_sessao_encerrada(self.driver):
                if _tentativa < 2:
                    print("  → Retentando login após sessão encerrada...")
                    time.sleep(2.0)
                    return self.login_completo(empresa, _tentativa=2, _captcha_retry=_captcha_retry)
                print(f"  ✗ Sessão encerrada persistente: {empresa.nome}")
                return False

            # Etapa 7 — reCAPTCHA (aparece após Avançar)
            ok = _clicar_recaptcha(self.driver, self.wait)
            if not ok:
                # Recarrega e tenta o login completo de novo — não pula a empresa
                print(f"  ⚠  reCAPTCHA falhou — reiniciando login ({_captcha_retry + 1})...")
                time.sleep(2.0)
                return self.login_completo(empresa, _tentativa=1, _captcha_retry=_captcha_retry + 1)
            time.sleep(0.5)

            # Checa modal após reCAPTCHA
            if verificar_sessao_encerrada(self.driver):
                print(f"  ✗ Sessão encerrada após reCAPTCHA: {empresa.nome}")
                return False

            logado = self._verificar_login()
            if logado:
                print(f"  ✓ Login confirmado: {empresa.nome}")
            else:
                print(f"  ✗ Login não confirmado: {empresa.nome}")
            return logado

        except (TimeoutException, NoSuchElementException) as e:
            print(f"  ✗ Falha no login ({empresa.nome}): {e}")
            return False

    def _verificar_login(self) -> bool:
        """Confirma login: URL sai da página de login e menu principal aparece."""
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: "login.jsf" not in d.current_url.lower()
            )
            # Aguarda o menu principal carregar — dashboard pronto para navegar
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.topmenu_S"))
            )
            return True
        except TimeoutException:
            try:
                erro = self.driver.find_element(
                    By.CSS_SELECTOR,
                    ".frmMsgErro, .msgErro, #msgErro, .alert-error"
                )
                if erro.is_displayed():
                    print(f"  ✗ Erro: {erro.text.strip()[:80]}")
            except NoSuchElementException:
                pass
            return False

    def logout(self):
        try:
            botao = self.driver.find_element(By.PARTIAL_LINK_TEXT, "Sair")
            botao.click()
            time.sleep(1)
        except Exception:
            pass
        try:
            self.driver.get(BRADESCO_URL)
            time.sleep(1)
        except Exception:
            pass
