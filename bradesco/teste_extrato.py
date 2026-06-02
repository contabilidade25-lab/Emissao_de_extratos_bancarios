"""
Testa o fluxo completo de extrato Bradesco para uma empresa específica:
  Login → Extrato CC (PDF + OFX) → Extrato Investimentos (PDF por produto)
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from bradesco_login  import criar_driver, BradescoSession
from bradesco_extrato import BradescoExtrato
from sheets_reader   import ler_empresas

DOWNLOADS  = Path.home() / "Downloads"
BANCO_DIR  = DOWNLOADS / "BRADESCO"


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
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        idx = int(sys.argv[1])
    elif len(empresas) > 1:
        escolha = input(f"\nQual testar? [0-{len(empresas)-1}] (Enter = 0): ").strip()
        if escolha.isdigit():
            idx = int(escolha)

    empresa = empresas[idx]
    print(f"\nTestando extrato: {empresa.nome}")
    print("=" * 60)

    BANCO_DIR.mkdir(parents=True, exist_ok=True)
    empresa_dir = BANCO_DIR / empresa.nome
    empresa_dir.mkdir(parents=True, exist_ok=True)

    driver = criar_driver(headless=False, download_dir=str(BANCO_DIR))
    try:
        # ── Login ──────────────────────────────────────────────────────
        sessao = BradescoSession(driver)
        ok = sessao.login_completo(empresa)
        if not ok:
            print("\n✗ Login falhou.")
            input("Pressione Enter para fechar o browser...")
            return

        print("\n✓ Login OK — iniciando extratos\n")

        extrato = BradescoExtrato(driver, BANCO_DIR)

        # ── Extrato CC ─────────────────────────────────────────────────
        extrato.extratos_cc(empresa, empresa_dir)

        # ── Extrato Investimentos ──────────────────────────────────────
        extrato.extratos_investimentos(empresa, empresa_dir)

        # ── Resultado ─────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("CONCLUÍDO")
        arquivos = list(empresa_dir.iterdir())
        print(f"Arquivos em {empresa_dir}:")
        for f in sorted(arquivos):
            print(f"  {f.name}")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Erro: {e}")
        input("\nBrowser aberto para inspeção. Pressione Enter para fechar...")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    input("\nPressione Enter para fechar o browser...")


if __name__ == "__main__":
    main()