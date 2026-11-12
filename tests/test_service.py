from pathlib import Path
from veil.service import VeilService


def test_service_lifecycle_no_audio_muting(tmp_path):
    srv = VeilService(vault_dir=tmp_path, socket_path=tmp_path / "test.sock", start_ipc=False)
    assert not srv.is_active
    
    # Toggle to active
    state = srv.toggle()
    assert state is True
    assert srv.is_active is True
    
    # Boss key execution (must not fail or mute sound)
    bk_res = srv.boss_key()
    assert bk_res is True
    assert srv.is_active is True
    
    # Toggle back to inactive
    state = srv.toggle()
    assert state is False
    assert srv.is_active is False
    
    srv.stop()
