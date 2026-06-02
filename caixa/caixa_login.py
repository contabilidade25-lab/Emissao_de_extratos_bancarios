"""
Login Caixa Econômica Federal — Internet Banking PJ.

Fluxo:
  1. Abre https://internetbanking.caixa.gov.br/sinbc/#!nb/login
  2. Seleciona "Pessoa Jurídica" (radio tpPessoaJuridica)
  3. Clica "Continuar" (btnLogin)
  4. Preenche Usuário (username) + Senha (password)
  5. Clica "Entrar" (kc-login)
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

load_dotenv(Path(__file__).parent / ".env")

CAIXA_URL = "https://internetbanking.caixa.gov.br/sinbc/#!nb/login"
TIMEOUT   = 25


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

    if download_dir:
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        prefs = {
            "download.default_directory":        str(download_dir),
            "download.prompt_for_download":      False,
            "download.directory_upgrade":        True,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
        }
        opcoes.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=opcoes)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ── Empresa ───────────────────────────────────────────────────────────

class EmpresaCaixa:
    """Dados de acesso Caixa lidos da planilha (colunas I–K)."""

    def __init__(self, nome: str, usuario: str, senha: str):
        self.nome    = nome
        self.usuario = usuario
        self.senha   = senha

    def __repr__(self):
        return f"EmpresaCaixa(nome={self.nome!r}, usuario={self.usuario!r})"


# ── Sessão ────────────────────────────────────────────────────────────

class CaixaSession:

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.wait   = WebDriverWait(driver, TIMEOUT)

    def login_completo(self, empresa: EmpresaCaixa) -> bool:
        try:
            # Etapa 1 — seleciona PJ e clica Continuar
            print(f"  → Abrindo {CAIXA_URL}")
            self.driver.get(CAIXA_URL)
            time.sleep(3)

            # Seleciona Pessoa Jurídica
            radio = self.wait.until(
                EC.presence_of_element_located((By.ID, "tpPessoaJuridica"))
            )
            self.driver.execute_script("arguments[0].click();", radio)
            print("  → Pessoa Jurídica selecionada")
            time.sleep(0.8)

            # Clica Continuar
            continuar = self.wait.until(
                EC.element_to_be_clickable((By.ID, "btnLogin"))
            )
            continuar.click()
            print("  → Continuar clicado")
            time.sleep(3)

            # Etapa 2 — tela Keycloak: usuário + senha
            campo_usuario = self.wait.until(
                EC.element_to_be_clickable((By.ID, "username"))
            )
            campo_usuario.clear()
            campo_usuario.send_keys(empresa.usuario)
            print(f"  → Usuário: {empresa.usuario}")
            time.sleep(0.4)

            campo_senha = self.driver.find_element(By.ID, "password")
            campo_senha.clear()
            campo_senha.send_keys(empresa.senha)
            print("  → Senha: ***")
            time.sleep(0.4)

            entrar = self.driver.find_element(By.ID, "kc-login")
            entrar.click()
            print("  → Entrar clicado")
            time.sleep(3)

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
        """Aguarda o botão Entrar sumir — indica que saiu da tela de login."""
        try:
            WebDriverWait(self.driver, 15).until(
                EC.invisibility_of_element_located((By.ID, "kc-login"))
            )
            # Saiu da tela — verifica se não voltou com erro visível
            try:
                erro = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "#kc-content-wrapper .alert, .alert-error, #kc-form-error"
                )
                if erro.is_displayed():
                    print(f"  ✗ Erro na tela: {erro.text.strip()[:80]}")
                    return False
            except NoSuchElementException:
                pass
            return True
        except TimeoutException:
            # Botão ainda visível após 15s — verifica mensagem de erro
            try:
                erro = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "#kc-content-wrapper .alert, .alert-error, #kc-form-error"
                )
                print(f"  ✗ Erro na tela: {erro.text.strip()[:80]}")
            except NoSuchElementException:
                pass
            return False

    def logout(self):
        """Volta para a URL inicial para a próxima empresa."""
        try:
            self.driver.get(CAIXA_URL)
            time.sleep(1)
        except Exception:
            pass
