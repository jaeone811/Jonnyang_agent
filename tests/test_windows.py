"""Windows 실제 시스템 스모크 테스트. 읽기만 하고 아무것도 바꾸지 않는다.

실행: pytest -m windows
"""

import sys

import pytest

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")]


def test_read_volume():
    from jonnyang.platform.system import WindowsVolume

    v = WindowsVolume()
    try:
        level = v.get()
    except OSError as exc:   # comtypes COMError는 OSError가 아님 → 아래에서 따로 처리
        pytest.skip(f"오디오 장치 없음: {exc}")
    except Exception as exc:
        if type(exc).__name__ == "COMError":   # 오디오 장치가 없는 CI 러너
            pytest.skip(f"오디오 장치 없음: {exc}")
        raise
    assert 0 <= level <= 100
    assert isinstance(v.is_muted(), bool)


def test_sysinfo():
    from jonnyang.platform.system import PsutilSysInfo

    s = PsutilSysInfo()
    assert 0 <= s.cpu_percent() <= 100
    assert s.memory()[1] > 0
    assert s.disks()


def test_kiwi_loads_from_this_path():
    """사용자 폴더명이 한글이어도 모델이 로드되는지 확인 (Kiwi 0.23.2에서 수정된 버그)."""
    from kiwipiepy import Kiwi

    assert Kiwi().tokenize("존냥아 안녕")
