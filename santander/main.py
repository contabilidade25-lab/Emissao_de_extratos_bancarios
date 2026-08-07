"""
Ponto de entrada — Santander Net Empresa PJ.

Fluxo completo:
  1. Lê empresas da planilha Google Sheets (colunas I–M)
  2. Cria pastas Downloads/{empresa}/ para todas as empresas
  3. Para cada empresa:
       Login (Ag + Conta + Usuário + Senha)
       Extrato CC  → PDF + OFX
       Investimento → PDF (pula se empresa não tiver)
       Tudo salvo em Downloads/{empresa}/

Cancelamento: pressione ESC × 3 rápido a qualquer momento para parar.
"""

import sys
import os
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

from notificacao import notificar_resumo

from santander_login           import criar_driver, SantanderSession
from sheets_santander          import ler_empresas_santander
from santander_extrato_gravado import extrato_gravado, _mes_anterior
from drive_upload               import criar_service, enviar_empresa, DRIVE_FOLDER_ID

_DIR      = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
load_dotenv(_DIR / ".env")

DOWNLOADS  = Path.home() / "Downloads"           # raiz
BANCO_DIR  = DOWNLOADS / "SANTANDER"             # Downloads/SANTANDER/
# Empresa: BANCO_DIR / emp.nome = Downloads/SANTANDER/{empresa}/


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


# ── Seleção de empresas ───────────────────────────────────────────────

def _selecionar_empresas(empresas):
    print("\nEmpresas disponíveis:\n")
    for i, e in enumerate(empresas):
        print(f"  [{i:>2}] {e.nome}")
    print("\nDigite os índices (ex: 0,3,5 ou 2-7 ou mix 0,2-5,9)")
    escolha = input("Enter = todas: ").strip()
    if not escolha:
        return list(empresas)
    import re as _re
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


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("EMISSÃO DE EXTRATOS — SANTANDER NET EMPRESA PJ")
    print("  CC (PDF + OFX) + Investimento (PDF) — por empresa")
    print("Pressione  ESC × 3  a qualquer momento para cancelar.")
    print("=" * 60)

    print("\n[1/3] Lendo empresas da planilha Google Sheets...")
    try:
        empresas = ler_empresas_santander()
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

    _, _, mm = _mes_anterior()

    driver     = criar_driver(headless=False, download_dir=str(BANCO_DIR))
    resultados = {"ok": [], "erro_login": [], "erro_extrato": []}

    try:
        drive_service = criar_service()
    except Exception as e:
        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
        drive_service = None

    try:
        sessao = SantanderSession(driver)

        for i, empresa in enumerate(empresas, start=1):

            if stop_event.is_set():
                print("\n⛔  Cancelado (ESC×3). Encerrando...")
                break

            print(f"\n[{i}/{len(empresas)}] {empresa.nome}")
            print("-" * 50)

            # ── Login ──────────────────────────────────────────────
            logado = sessao.login_completo(empresa)
            if not logado:
                resultados["erro_login"].append(empresa.nome)
                continue
            print("  ✓ Login OK")

            if stop_event.is_set():
                print("\n⛔  Cancelado após login.")
                break

            # Pasta já criada na etapa anterior
            empresa_dir = BANCO_DIR / empresa.nome

            # ── Extrato CC ─────────────────────────────────────────
            exc_holder = [None]

            def _rodar(emp=empresa, edir=empresa_dir):
                try:
                    extrato_gravado(
                        driver       = driver,
                        empresa_nome = emp.nome,
                        mm           = mm,
                        output_dir   = edir,
                        download_dir = BANCO_DIR,
                    )
                except Exception as e:
                    exc_holder[0] = e

            t = threading.Thread(target=_rodar, daemon=True)
            t.start()

            while t.is_alive():
                if stop_event.is_set():
                    print("\n⛔  ESC×3 — interrompendo...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    t.join(timeout=3)
                    sys.exit(0)
                time.sleep(0.2)

            if exc_holder[0]:
                print(f"  ✗ Erro: {exc_holder[0]}")
                resultados["erro_extrato"].append(empresa.nome)
            else:
                resultados["ok"].append(empresa.nome)
                print(f"  → Extratos em: {empresa_dir}")
                if drive_service is not None:
                    try:
                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
                    except Exception as e:
                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")

            sessao.logout()

    finally:
        try:
            driver.quit()
        except Exception:
            pass

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
    print(f"\nExtratos em: {BANCO_DIR}")
    print("=" * 60)

    notificar_resumo("SANTANDER", resultados)


if __name__ == "__main__":
    main()
