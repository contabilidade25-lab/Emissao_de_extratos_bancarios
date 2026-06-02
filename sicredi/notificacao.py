"""
Notificações Toast do Windows para os scripts de emissão de extratos.
Usa winotify (pip install winotify).
"""

from winotify import Notification, audio


def notificar(titulo: str, mensagem: str) -> None:
    """Exibe uma notificação Toast na bandeja do Windows."""
    try:
        toast = Notification(
            app_id="Extratos Bancarios",
            title=titulo,
            msg=mensagem,
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        pass


def notificar_resumo(banco: str, resultados: dict) -> None:
    """Dispara notificação final com o resumo da execução."""
    ok      = len(resultados.get("ok", []))
    e_login = len(resultados.get("erro_login", []))
    e_ext   = len(resultados.get("erro_extrato", []))
    total   = ok + e_login + e_ext

    linhas = [f"Total: {total}  |  OK: {ok}"]
    if e_login:
        linhas.append(f"Erro login: {e_login}")
    if e_ext:
        linhas.append(f"Erro extrato: {e_ext}")

    notificar(f"{banco} — Execucao concluida", "\n".join(linhas))
