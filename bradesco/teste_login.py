"""
Testa login Bradesco para uma empresa específica.
Uso:
  python teste_login.py
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from bradesco_login import criar_driver, BradescoSession
from sheets_reader  import ler_empresas


def main():
    print("Lendo empresas da planilha...")
    empresas = ler_empresas()

    if not empresas:
        print("Nenhuma empresa encontrada.")
        sys.exit(1)

    print(f"\n{len(empresas)} empresa(s):\n")
    for i, e in enumerate(empresas):
        print(f"  [{i}] {e.nome}")

    idx = 0
    if len(empresas) > 1:
        escolha = input(f"\nQual testar? [0-{len(empresas)-1}] (Enter = 0): ").strip()
        if escolha.isdigit():
            idx = int(escolha)

    empresa = empresas[idx]
    print(f"\nTestando login: {empresa.nome}")
    print("-" * 50)

    driver = criar_driver(headless=False)
    try:
        sessao = BradescoSession(driver)
        ok = sessao.login_completo(empresa)
        if ok:
            print("\n✓ Login bem-sucedido!")
            input("Pressione Enter para fechar o browser...")
        else:
            print("\n✗ Login falhou.")
            input("Pressione Enter para fechar o browser...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
