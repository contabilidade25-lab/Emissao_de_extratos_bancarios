"""
Ponto de entrada principal.
Lê empresas do Google Sheets → abre browser → agente Claude guia o login de cada uma.
"""

import sys
from pathlib import Path

from sheets_reader import ler_empresas
from bradesco_login import criar_driver, BradescoSession
from agente_claude import AgenteClaudeLogin

OUTPUT_DIR = Path("extratos")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("EMISSÃO DE EXTRATOS — BRADESCO NET EMPRESA")
    print("=" * 60)

    print("\n[1/2] Lendo credenciais da planilha Google Sheets...")
    try:
        empresas = ler_empresas()
    except FileNotFoundError as e:
        print(f"\nERRO: {e}")
        sys.exit(1)

    if not empresas:
        print("Nenhuma empresa válida encontrada na planilha.")
        sys.exit(0)

    print(f"\n{len(empresas)} empresa(s) para processar.\n")

    print("[2/2] Iniciando automação com agente Claude...\n")
    driver = criar_driver(headless=False)

    resultados = {"ok": [], "erro": []}

    try:
        sessao = BradescoSession(driver)
        agente = AgenteClaudeLogin(driver)

        for i, empresa in enumerate(empresas, start=1):
            print(f"\n[{i}/{len(empresas)}] {empresa.nome}")

            # Abre o site e seleciona tipo de acesso
            aberto = sessao.login(empresa)
            if not aberto:
                resultados["erro"].append(empresa.nome)
                continue

            # Agente Claude assume o controle para completar o login
            logado = agente.executar_login(empresa)

            if logado:
                # TODO: chamar módulo de emissão de extrato
                # extrato.emitir(sessao, empresa, OUTPUT_DIR)
                resultados["ok"].append(empresa.nome)
                sessao.logout()
            else:
                resultados["erro"].append(empresa.nome)

    finally:
        driver.quit()

    print("\n" + "=" * 60)
    print(f"CONCLUÍDO: {len(resultados['ok'])} OK  |  {len(resultados['erro'])} com erro")

    if resultados["erro"]:
        print("\nEmpresas com erro:")
        for nome in resultados["erro"]:
            print(f"  - {nome}")

    print("=" * 60)


if __name__ == "__main__":
    main()