"""
Login Sicredi Internet Banking PJ.

Fluxo (confirmado pelo recorder):
  1. Abre https://www.sicredi.com.br/home/
  2. Aceita cookies  [data-testid="all-cookies-button"]
  3. Clica "Acessar minha conta"  → preauth.html
  4. Preenche CNPJ + Enter  → login.html
  5. Preenche Usuário
  6. Clica cada dígito no teclado virtual (pares aleatórios, ex: "6 ou 3")
     — lê o texto visível de cada span.btn.senha para encontrar o par correto
  7. Clica div#submeter "Acessar"
  8. Confirma login: URL contém "home.html"
"""

import time
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

load_dotenv(Path(__file__).parent / ".env")

SICREDI_HOME = "https://www.sicredi.com.br/home/"
TIMEOUT      = 25


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

class EmpresaSicredi:
    def __init__(self, nome: str, usuario: str, senha: str, cnpj: str):
        self.nome    = nome
        self.usuario = usuario
        self.senha   = senha
        self.cnpj    = cnpj

    def __repr__(self):
        return f"EmpresaSicredi(nome={self.nome!r}, cnpj={self.cnpj!r})"


# ── Teclado virtual ───────────────────────────────────────────────────

def _clicar_digito(driver: webdriver.Chrome, digito: str):
    """
    Localiza e clica o botão do teclado virtual que contém o dígito.
    Cada botão exibe texto como "6 ou 3" — os pares mudam a cada sessão.
    Tenta pelo texto visível e também pelo atributo title como fallback.
    """
    botoes = driver.find_elements(By.CSS_SELECTOR, "span.btn.senha")
    for botao in botoes:
        texto = (botao.text or "").strip()
        title = (botao.get_attribute("title") or "").strip()

        # Extrai dígitos do texto visível: "6 ou 3" → ["6", "3"]
        pares = [p.strip() for p in texto.split("ou")]
        # Fallback: título "Inserir o digito X ou Y" → ["X", "Y"]
        if not any(p.isdigit() for p in pares):
            pares = [p.strip() for p in title.replace("Inserir o digito", "").split("ou")]

        if digito in pares:
            botao.click()
            time.sleep(0.25)
            return

    raise NoSuchElementException(
        f"Dígito '{digito}' não encontrado no teclado virtual. "
        f"Textos disponíveis: {[b.text for b in botoes]}"
    )


def _digitar_senha(driver: webdriver.Chrome, wait: WebDriverWait, senha: str):
    """Aguarda o teclado virtual aparecer e clica cada dígito."""
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.btn.senha")))
    print("  → Teclado virtual carregado")
    for digito in senha:
        _clicar_digito(driver, digito)
    print("  → Senha digitada")


# ── Sessão ────────────────────────────────────────────────────────────

class SicrediSession:

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.wait   = WebDriverWait(driver, TIMEOUT)

    def login_completo(self, empresa: EmpresaSicredi) -> bool:
        try:
            # Etapa 0 — Home
            print(f"  → Abrindo {SICREDI_HOME}")
            self.driver.get(SICREDI_HOME)
            time.sleep(2.0)

            # Aceita cookies
            try:
                btn = WebDriverWait(self.driver, 6).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, '[data-testid="all-cookies-button"]')
                    )
                )
                btn.click()
                print("  → Cookies aceitos")
                time.sleep(1.0)
            except TimeoutException:
                pass

            # Etapa 1 — Abre dropdown e clica "Pessoa Jurídica"
            btn_acessar = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//a[normalize-space(.)="Acessar minha conta"]')
                )
            )
            btn_acessar.click()
            print("  → Acessar minha conta clicado")
            time.sleep(1.0)

            link_pj = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, '[data-gtag-label="login-pj"]')
                )
            )
            link_pj.click()
            print("  → Pessoa Jurídica clicado")
            time.sleep(2.5)

            # Etapa 2 — CNPJ (preauth.html)
            campo_cnpj = self.wait.until(
                EC.element_to_be_clickable((By.ID, "cnpj"))
            )
            campo_cnpj.clear()
            campo_cnpj.send_keys(empresa.cnpj)
            print(f"  → CNPJ: {empresa.cnpj}")
            time.sleep(0.4)
            campo_cnpj.send_keys(Keys.RETURN)
            print("  → CNPJ submetido")
            time.sleep(3.0)

            # Etapa 3 — Usuário (login.html)
            campo_usuario = self.wait.until(
                EC.element_to_be_clickable((By.ID, "j_username"))
            )
            campo_usuario.clear()
            campo_usuario.send_keys(empresa.usuario)
            print(f"  → Usuário: {empresa.usuario}")
            time.sleep(0.4)

            # Etapa 4 — Senha (teclado virtual)
            print("  → Senha: ***")
            _digitar_senha(self.driver, self.wait, empresa.senha)
            time.sleep(0.5)

            # Etapa 5 — Submete (div#submeter "Acessar")
            el = self.wait.until(EC.element_to_be_clickable((By.ID, "submeter")))
            self.driver.execute_script("arguments[0].click();", el)
            print("  → Acessar clicado")
            time.sleep(3.0)

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
        """Confirma login aguardando URL home.html."""
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: "home.html" in d.current_url.lower()
            )
            return True
        except TimeoutException:
            try:
                erro = self.driver.find_element(
                    By.CSS_SELECTOR, ".erro, .mensagem-erro, .alert-error, #msgErro"
                )
                if erro.is_displayed():
                    print(f"  ✗ Erro: {erro.text.strip()[:80]}")
            except NoSuchElementException:
                pass
            return False

    def logout(self):
        try:
            self.driver.get(SICREDI_HOME)
            time.sleep(1)
        except Exception:
            pass
