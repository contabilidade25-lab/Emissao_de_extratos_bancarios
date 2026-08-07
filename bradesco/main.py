"""
Ponto de entrada — Bradesco Net Empresa PJ.

Fluxo:
  1. Lê empresas da planilha Google Sheets (colunas A–C, linhas 3+)
  2. Cria Downloads/BRADESCO/{empresa}/ para todas as empresas
  3. Para cada empresa:
       Login (Usuário + Senha + reCAPTCHA)
       Extrato CC → PDF + OFX
       Extrato Investimentos → PDF por tipo/produto
       Tudo salvo em Downloads/BRADESCO/{empresa}/

Cancelamento: pressione ESC × 3 rápido a qualquer momento para parar.
"""

import sys
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

from notificacao import notificar_resumo

from bradesco_login   import criar_driver, BradescoSession
from bradesco_extrato import BradescoExtrato
from sheets_reader    import ler_empresas
from drive_upload     import criar_service, enviar_empresa, DRIVE_FOLDER_ID

_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
load_dotenv(_DIR / ".env")

DOWNLOADS = Path.home() / "Downloads"
BANCO_DIR = DOWNLOADS / "BRADESCO"


# ── Listener ESC × 3 ─────────────────────────────────────────────────

def _iniciar_cancelamento(stop_event: threading.Event):
    try:
        from pynput import keyboard as kb
        esc_times = []

        def on_press(key):
            nonlocal esc_times
            if key == kb.Key.esc:
                agora = time.time()
                esc_times = [t for t in esc_times if agora - t < 1.2]
                esc_times.append(agora)
                if len(esc_times) >= 3:
                    stop_event.set()
                    return False

        listener = kb.Listener(on_press=on_press)
        listener.start()
        stop_event.wait()
        try:
            listener.stop()
        except Exception:
            pass
    except ImportError:
        pass


# ── Main ──────────────────────────────────────────────────────────────

def _selecionar_empresas(empresas):
    """
    Exibe lista e permite escolher empresas específicas.
    Aceita:
      - Enter → todas
      - índices separados por vírgula: 0,3,5
      - intervalo: 2-7
      - mix: 0,2-5,9
    Retorna a sublista selecionada.
    """
    print("\nEmpresas disponíveis:\n")
    for i, e in enumerate(empresas):
        print(f"  [{i:>2}] {e.nome}")

    print("\nDigite os índices (ex: 0,3,5 ou 2-7 ou mix 0,2-5,9)")
    escolha = input("Enter = todas: ").strip()

    if not escolha:
        return list(empresas)

    import re as _re
    # Remove parênteses e outros caracteres que não sejam dígito, hífen ou vírgula
    escolha = _re.sub(r"[^\d,\-]", "", escolha)

    selecionados = set()
    for parte in escolha.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            try:
                selecionados.update(range(int(a), int(b) + 1))
            except ValueError:
                print(f"  Ignorado (inválido): '{parte}'")
        elif parte.isdigit():
            selecionados.add(int(parte))
        else:
            print(f"  Ignorado (inválido): '{parte}'")

    resultado = [empresas[i] for i in sorted(selecionados) if 0 <= i < len(empresas)]
    if not resultado:
        print("Nenhuma empresa selecionada — saindo.")
        sys.exit(0)
    return resultado


def main():
    print("=" * 60)
    print("EMISSÃO DE EXTRATOS — BRADESCO NET EMPRESA PJ")
    print("Pressione  ESC × 3  a qualquer momento para cancelar.")
    print("=" * 60)

    print("\n[1/3] Lendo empresas da planilha Google Sheets...")
    try:
        empresas = ler_empresas()
    except FileNotFoundError as e:
        print(f"\nERRO: {e}")
        sys.exit(1)

    if not empresas:
        print("Nenhuma empresa válida encontrada.")
        sys.exit(0)

    print(f"\n{len(empresas)} empresa(s) encontrada(s).")

    # ── Modo de execução ──────────────────────────────────────────────
    print("\nModo de execução:")
    print("  [1] Processar TODAS as empresas")
    print("  [2] Selecionar empresas específicas")
    modo = input("\nEscolha [1/2] (Enter = 1): ").strip()

    if modo == "2":
        empresas = _selecionar_empresas(empresas)

    print(f"\n{len(empresas)} empresa(s) para processar.\n")

    # ── Cria pastas antes de começar ──────────────────────────────────
    print("[2/3] Criando pastas de destino...")
    BANCO_DIR.mkdir(parents=True, exist_ok=True)
    for emp in empresas:
        pasta = BANCO_DIR / emp.nome
        if not pasta.exists():
            pasta.mkdir(parents=True, exist_ok=True)
            print(f"  + Criada: {pasta}")
        else:
            print(f"  ✓ Já existe: {pasta}")
    print()

    stop_event = threading.Event()
    threading.Thread(target=_iniciar_cancelamento, args=(stop_event,), daemon=True).start()

    driver     = criar_driver(headless=False, download_dir=str(BANCO_DIR))
    resultados = {"ok": [], "erro_login": [], "erro_extrato": []}

    try:
        drive_service = criar_service()
    except Exception as e:
        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
        drive_service = None

    try:
        sessao  = BradescoSession(driver)
        extrato = BradescoExtrato(driver, BANCO_DIR)

        print("[3/3] Processando empresas...\n")

        for i, empresa in enumerate(empresas, start=1):

            if stop_event.is_set():
                print("\n⛔  Cancelado (ESC×3). Encerrando...")
                break

            print(f"\n[{i}/{len(empresas)}] {empresa.nome}")
            print("-" * 50)

            logado = sessao.login_completo(empresa)
            if not logado:
                resultados["erro_login"].append(empresa.nome)
                sessao.logout()
                continue
            print("  ✓ Login OK")

            if stop_event.is_set():
                print("\n⛔  Cancelado após login.")
                break

            empresa_dir = BANCO_DIR / empresa.nome
            erro = False

            try:
                extrato.extratos_cc(empresa, empresa_dir)
            except Exception as e:
                print(f"  ✗ Erro CC: {e}")
                erro = True

            if not stop_event.is_set() and not erro:
                try:
                    extrato.extratos_investimentos(empresa, empresa_dir)
                except Exception as e:
                    print(f"  ✗ Erro Invest: {e}")
                    erro = True

            if erro:
                resultados["erro_extrato"].append(empresa.nome)
            else:
                resultados["ok"].append(empresa.nome)
                if drive_service is not None:
                    try:
                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
                    except Exception as e:
                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")

            sessao.logout()

    finally:
        pass  # browser permanece aberto para inspeção

    # ── Resumo ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESUMO FINAL")
    print("=" * 60)
    print(f"  OK          : {len(resultados['ok'])}")
    print(f"  Erro login  : {len(resultados['erro_login'])}")
    print(f"  Erro extrato: {len(resultados['erro_extrato'])}")
    for cat, lst in [("ERRO LOGIN", resultados["erro_login"]),
                     ("ERRO EXTRATO", resultados["erro_extrato"])]:
        if lst:
            print(f"\n{cat}:")
            for n in lst:
                print(f"  - {n}")
    print(f"\nPastas em: {BANCO_DIR}")
    print("=" * 60)

    notificar_resumo("BRADESCO", resultados)


if __name__ == "__main__":
    main()
