import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import drive_upload


def test_drive_folder_id_has_hardcoded_default():
    assert drive_upload.DRIVE_FOLDER_ID == "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"


def test_creds_dir_falls_back_to_bradesco_folder_when_running_from_source():
    assert drive_upload._CREDS_DIR == drive_upload._DIR.parent / "bradesco"


def test_creds_dir_uses_own_folder_when_frozen(monkeypatch):
    import importlib
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    importlib.reload(drive_upload)
    assert drive_upload._CREDS_DIR == drive_upload._DIR
    monkeypatch.delattr(sys, "frozen", raising=False)
    importlib.reload(drive_upload)


def test_enviar_empresa_cria_pasta_banco_depois_pasta_empresa_e_sincroniza(tmp_path, monkeypatch):
    empresa_dir = tmp_path / "Empresa Teste"
    empresa_dir.mkdir()
    (empresa_dir / "extrato.pdf").write_text("conteudo")

    chamadas = []

    def fake_pasta_id(service, nome, parent_id):
        chamadas.append(("pasta", nome, parent_id))
        return f"id-{nome}"

    def fake_sincronizar_dir(service, local, drive_parent_id):
        chamadas.append(("sync", local, drive_parent_id))

    monkeypatch.setattr(drive_upload, "_pasta_id", fake_pasta_id)
    monkeypatch.setattr(drive_upload, "_sincronizar_dir", fake_sincronizar_dir)

    drive_upload.enviar_empresa(object(), "CAIXA ECONÔMICA", empresa_dir, "root-id")

    assert chamadas == [
        ("pasta", "CAIXA ECONÔMICA", "root-id"),
        ("pasta", "Empresa Teste", "id-CAIXA ECONÔMICA"),
        ("sync", empresa_dir, "id-Empresa Teste"),
    ]


def test_q_escapa_aspas_simples_e_barra_invertida():
    assert drive_upload._q("D'Avila") == "D\\'Avila"
    assert drive_upload._q("C:\\pasta") == "C:\\\\pasta"


def test_upload_pula_arquivo_com_mesmo_tamanho(tmp_path, monkeypatch):
    arquivo = tmp_path / "extrato.pdf"
    arquivo.write_bytes(b"conteudo de teste")

    chamadas = []

    def fake_arquivo_existente(service, nome, parent_id):
        return {"id": "id-existente", "size": str(arquivo.stat().st_size)}

    def fake_media_upload(*args, **kwargs):
        chamadas.append("upload_chamado")
        raise AssertionError("não deveria fazer upload de arquivo sem mudanças")

    monkeypatch.setattr(drive_upload, "_arquivo_existente", fake_arquivo_existente)
    monkeypatch.setattr(drive_upload, "MediaFileUpload", fake_media_upload)

    drive_upload._upload(service=object(), caminho=arquivo, parent_id="parent-id")

    assert chamadas == []
