"""
Automação de login no Santander Net Empresa (PJ).

Etapa 1 — Home /empresas:
    Shadow DOM: preenche Agência + Conta → clica seta →

Etapa 2 — Tela de login (JSF PrimeFaces):
    Selenium direto: preenche Usuário + Senha → clica Entrar
    (sem CAPTCHA, sem teclado virtual obrigatório)
"""

import os
import time
import base64

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

load_dotenv()

SANTANDER_URL = os.getenv("SANTANDER_URL", "https://www.santander.com.br/empresas")
TIMEOUT = 20


# ── Driver ────────────────────────────────────────────────────────────

def criar_driver(headless: bool = False, download_dir: str | None = None) -> webdriver.Chrome:
    opcoes = Options()
    if headless:
        opcoes.add_argument("--headless=new")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])
    opcoes.add_experimental_option("useAutomationExtension", False)
    opcoes.add_argument("--window-size=1366,768")
    opcoes.add_argument("--start-maximized")

    # Configura pasta de download — sem diálogo "Salvar como"
    if download_dir:
        from pathlib import Path
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        prefs = {
            "download.default_directory":     str(download_dir),
            "download.prompt_for_download":   False,
            "download.directory_upgrade":     True,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
        }
        opcoes.add_experimental_option("prefs", prefs)

    # Selenium 4.6+ gerencia o ChromeDriver automaticamente — sem webdriver_manager
    driver = webdriver.Chrome(options=opcoes)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def screenshot_base64(driver: webdriver.Chrome) -> str:
    png = driver.get_screenshot_as_png()
    return base64.b64encode(png).decode("utf-8")


# ── Empresa ───────────────────────────────────────────────────────────

class EmpresaSantander:
    """Dados de acesso Santander lidos da planilha (colunas I–M)."""

    def __init__(self, nome: str, usuario: str, senha: str, agencia: str, conta: str):
        self.nome    = nome
        self.usuario = usuario
        self.senha   = senha
        self.agencia = agencia
        self.conta   = conta   # C.C.

    def __repr__(self):
        return (
            f"EmpresaSantander(nome={self.nome!r}, "
            f"ag={self.agencia!r}, conta={self.conta!r})"
        )


# ── Helper Shadow DOM ─────────────────────────────────────────────────

def _preencher_angular(driver, campo, valor: str):
    """
    Preenche campo Angular (Shadow DOM) usando setter nativo + eventos,
    necessário para o formulário reativo reconhecer o valor digitado.
    """
    driver.execute_script(
        """
        var el  = arguments[0];
        var val = arguments[1];
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input',  {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        campo, valor,
    )
    time.sleep(0.3)


# ── Sessão ────────────────────────────────────────────────────────────

class SantanderSession:
    """
    Gerencia o login completo no Santander Empresas PJ:
      - Etapa 1: Agência + Conta no Shadow DOM da home
      - Etapa 2: Usuário + Senha na tela JSF
    """

    # Etapa 1 — Shadow DOM
    SHADOW_HOST = "wpc-mfe-home-header-element"
    SEL_AG      = 'input[formcontrolname="ag"]'
    SEL_CONTA   = 'input[formcontrolname="acc"]'
    SEL_BOTAO   = "button.login-icon"

    # Etapa 2 — Tela JSF (IDs com colon → usar By.ID)
    ID_USUARIO  = "formGeral:usuario"
    ID_SENHA    = "formGeral:senhaAcesso"
    ID_ENTRAR   = "btnLogin"             # input[type=button] onclick=onEnviar()
    ID_ENTRAR2  = "formGeral:btnEntrar"  # button JSF — fallback

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.wait   = WebDriverWait(driver, TIMEOUT)

    # ── Etapa 1 ───────────────────────────────────────────────────────

    def _shadow_root(self):
        host = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, self.SHADOW_HOST))
        )
        return host.shadow_root  # Selenium 4+

    def abrir_site(self):
        print(f"  → Abrindo {SANTANDER_URL}")
        self.driver.get(SANTANDER_URL)
        time.sleep(3)

    def _preencher_agencia_conta(self, agencia: str, conta: str) -> bool:
        try:
            sr = self._shadow_root()

            ag = sr.find_element(By.CSS_SELECTOR, self.SEL_AG)
            print(f"  → Agência: {agencia}")
            _preencher_angular(self.driver, ag, agencia)

            ct = sr.find_element(By.CSS_SELECTOR, self.SEL_CONTA)
            print(f"  → Conta: {conta}")
            _preencher_angular(self.driver, ct, conta)

            time.sleep(0.5)
            print("  → Clicando seta →")
            sr.find_element(By.CSS_SELECTOR, self.SEL_BOTAO).click()
            time.sleep(3)  # aguarda carregar a tela de login JSF
            return True

        except Exception as e:
            print(f"  ✗ Falha Ag/Conta: {e}")
            return False

    # ── Etapa 2 ───────────────────────────────────────────────────────

    def _preencher_usuario_senha(self, usuario: str, senha: str) -> bool:
        """
        Preenche Usuário e Senha na tela JSF.
        Aguarda a página carregar completamente antes de interagir.
        """
        try:
            # Aguarda o campo usuário estar clicável e a página estabilizar
            campo_usuario = self.wait.until(
                EC.element_to_be_clickable((By.ID, self.ID_USUARIO))
            )
            time.sleep(1.5)  # aguarda carregamento completo dos handlers JS

            print(f"  → Usuário: {usuario}")
            campo_usuario.clear()
            campo_usuario.send_keys(usuario)
            time.sleep(0.5)

            print("  → Senha: ***")
            campo_senha = self.driver.find_element(By.ID, self.ID_SENHA)
            campo_senha.clear()
            campo_senha.send_keys(senha)
            time.sleep(0.5)

            print("  → Clicando Entrar")
            try:
                self.driver.find_element(By.ID, self.ID_ENTRAR).click()
            except NoSuchElementException:
                self.driver.find_element(By.ID, self.ID_ENTRAR2).click()
            time.sleep(3)

            return True

        except (TimeoutException, NoSuchElementException) as e:
            print(f"  ✗ Falha usuário/senha: {e}")
            return False

    # ── Login completo ────────────────────────────────────────────────

    def login_completo(self, empresa: EmpresaSantander) -> bool:
        """
        Executa as duas etapas e retorna True se chegou na home bancária.
        """
        try:
            # Etapa 1
            self.abrir_site()
            if not self._preencher_agencia_conta(empresa.agencia, empresa.conta):
                return False

            # Etapa 2
            if not self._preencher_usuario_senha(empresa.usuario, empresa.senha):
                return False

            # Verifica se logou (URL ou elemento pós-login)
            logado = self._verificar_login()
            if logado:
                print(f"  ✓ Login confirmado: {empresa.nome}")
            else:
                print(f"  ✗ Login não confirmado: {empresa.nome}")
            return logado

        except TimeoutException as e:
            print(f"  ✗ Timeout {empresa.nome}: {e}")
            return False

    def _verificar_login(self) -> bool:
        """
        Verifica se o login foi bem-sucedido aguardando a URL mudar
        ou um elemento da home bancária aparecer.
        """
        try:
            # Aguarda a URL sair da tela de login
            WebDriverWait(self.driver, 15).until(
                lambda d: "login" not in d.current_url.lower()
                          and "empresas" not in d.current_url.lower()
            )
            return True
        except TimeoutException:
            # Verifica se há mensagem de erro na tela
            try:
                erro = self.driver.find_element(
                    By.CSS_SELECTOR, ".ui-messages-error, .msg-erro, #msgErro"
                )
                print(f"  ✗ Mensagem de erro: {erro.text}")
            except NoSuchElementException:
                pass
            return False

    def logout(self):
        """Volta para a home para a próxima empresa."""
        try:
            self.driver.get(SANTANDER_URL)
            time.sleep(1)
        except Exception:
            pass
