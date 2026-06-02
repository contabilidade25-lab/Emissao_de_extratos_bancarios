"""
Agente inteligente baseado na API do Claude (visão) para guiar a automação do Bradesco.
Analisa screenshots da tela e decide a próxima ação a executar via Selenium.
"""

import os
import json
import time
from typing import Optional

import anthropic
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

from bradesco_login import BradescoSession, screenshot_base64
from sheets_reader import Empresa

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MAX_PASSOS = 20  # limite de iterações por empresa para evitar loop infinito


PROMPT_SISTEMA = """Você é um assistente especializado em automação de acesso ao Bradesco Net Empresa.
Você recebe screenshots da tela do navegador e deve decidir a próxima ação para completar o login.

CONTEXTO:
- URL de login: https://www.ne12.bradesconetempresa.b.br/ibpjlogin/login.jsf
- A tela tem um radio button "Usuário" (id: rdoTipoAcesso02) já selecionado
- Após selecionar, aparecem campos de usuário e senha
- O banco pode usar teclado virtual (clique nas teclas na tela)

FORMATO DE RESPOSTA — sempre responda com JSON válido:
{
  "status": "em_progresso" | "logado" | "erro",
  "descricao": "o que você está vendo na tela",
  "acao": {
    "tipo": "clicar" | "digitar" | "clicar_coordenada" | "aguardar" | "nenhuma",
    "seletor_css": "seletor CSS do elemento (se tipo=clicar ou digitar)",
    "texto": "texto a digitar (se tipo=digitar)",
    "x": 123,
    "y": 456,
    "descricao": "descrição da ação"
  }
}

REGRAS:
- Se já estiver logado (mudou para outra página após login), retorne status="logado"
- Se houver mensagem de erro de senha/usuário inválido, retorne status="erro"
- Para teclado virtual, use tipo="clicar_coordenada" com as coordenadas x,y do botão
- Seja preciso nas coordenadas — o teclado virtual exige cliques exatos
- Máximo 1 ação por resposta
"""


class AgenteClaudeLogin:
    """Usa Claude Vision para analisar screenshots e guiar o login."""

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.historico: list[dict] = []

    def analisar_tela(self, empresa: Empresa, screenshot_b64: str) -> dict:
        """Envia screenshot para Claude e recebe instrução da próxima ação."""

        contexto_usuario = f"""
Estou tentando fazer login no Bradesco Net Empresa com:
- Usuário: {empresa.usuario}
- Senha: {empresa.senha}

Analise o screenshot e diga a próxima ação necessária para completar o login.
Responda APENAS com JSON válido conforme o formato especificado.
"""

        mensagem = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=PROMPT_SISTEMA,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": contexto_usuario,
                        },
                    ],
                }
            ],
        )

        texto = mensagem.content[0].text.strip()

        # extrai JSON mesmo que venha com texto ao redor
        inicio = texto.find("{")
        fim = texto.rfind("}") + 1
        if inicio >= 0 and fim > inicio:
            texto = texto[inicio:fim]

        return json.loads(texto)

    def executar_acao(self, instrucao: dict) -> bool:
        """Executa a ação determinada pelo Claude via Selenium."""
        acao = instrucao.get("acao", {})
        tipo = acao.get("tipo", "nenhuma")
        descricao = acao.get("descricao", "")

        print(f"    [Claude] {instrucao.get('descricao', '')} → {descricao}")

        if tipo == "nenhuma" or tipo == "aguardar":
            time.sleep(2)
            return True

        elif tipo == "clicar":
            seletor = acao.get("seletor_css", "")
            try:
                elemento = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, seletor))
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", elemento)
                time.sleep(0.3)
                elemento.click()
                time.sleep(1)
                return True
            except Exception as e:
                print(f"    [ERRO] Falha ao clicar em '{seletor}': {e}")
                return False

        elif tipo == "digitar":
            seletor = acao.get("seletor_css", "")
            texto = acao.get("texto", "")
            try:
                elemento = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, seletor))
                )
                elemento.clear()
                elemento.send_keys(texto)
                time.sleep(0.5)
                return True
            except Exception as e:
                print(f"    [ERRO] Falha ao digitar em '{seletor}': {e}")
                return False

        elif tipo == "clicar_coordenada":
            x = acao.get("x", 0)
            y = acao.get("y", 0)
            try:
                actions = ActionChains(self.driver)
                actions.move_by_offset(0, 0)  # reset
                actions.move_to_element_with_offset(
                    self.driver.find_element(By.TAG_NAME, "body"), x, y
                )
                actions.click()
                actions.perform()
                time.sleep(0.5)
                return True
            except Exception as e:
                print(f"    [ERRO] Falha ao clicar em ({x},{y}): {e}")
                return False

        return True

    def executar_login(self, empresa: Empresa) -> bool:
        """
        Loop principal: tira screenshot → envia ao Claude → executa ação → repete.
        Para quando Claude retorna status='logado' ou 'erro'.
        """
        print(f"  [Agente] Iniciando login guiado por IA para: {empresa.nome}")

        for passo in range(1, MAX_PASSOS + 1):
            print(f"  [Agente] Passo {passo}/{MAX_PASSOS}")

            screenshot = screenshot_base64(self.driver)

            try:
                instrucao = self.analisar_tela(empresa, screenshot)
            except Exception as e:
                print(f"  [ERRO] Falha ao consultar Claude: {e}")
                return False

            status = instrucao.get("status", "em_progresso")

            if status == "logado":
                print(f"  ✓ [Agente] Login confirmado pelo Claude: {empresa.nome}")
                return True

            if status == "erro":
                print(f"  ✗ [Agente] Erro de login detectado: {instrucao.get('descricao', '')}")
                return False

            sucesso = self.executar_acao(instrucao)
            if not sucesso:
                # tenta continuar mesmo com falha de ação
                time.sleep(1)

        print(f"  ✗ [Agente] Limite de {MAX_PASSOS} passos atingido sem concluir login")
        return False
