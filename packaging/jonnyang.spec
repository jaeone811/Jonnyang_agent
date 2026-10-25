# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 설정: python -m PyInstaller --noconfirm --clean packaging/jonnyang.spec
# 결과: dist/Jonnyang/Jonnyang.exe (+ _internal 폴더). 한 파일(onefile)로 안 묶는 이유:
# 실행할 때마다 200MB 넘게 임시 폴더에 풀어야 해서 느리고 백신 오탐도 잦다.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent

datas, binaries, hiddenimports = [], [], []
for pkg in ("kiwipiepy", "kiwipiepy_model"):     # 형태소 분석기 확장 모듈 + 모델 파일(약 105MB)
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas.append((str(ROOT / "config"), "config"))   # exe 옆 config/가 없을 때 쓰는 기본값
datas.append((str(ROOT / "src" / "jonnyang" / "gui" / "sprites"), "sprites"))   # 펫 그림 (exe 옆 sprites/가 우선)
hiddenimports.append("jonnyang.platform.system")
# 뉴스(RSS)와 휴지통은 쓸 때 import하므로 확실히 묶이게 적어 둔다
hiddenimports += ["feedparser", "send2trash", "send2trash.util"]
if sys.platform == "win32":
    # send2trash: pywin32가 없으면 ctypes로 SHFileOperation을 쓰는 legacy 쪽을 쓴다
    hiddenimports += ["pycaw.pycaw", "pycaw.utils", "send2trash.win", "send2trash.win.legacy"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # numpy/scipy: kiwipiepy의 부가 모듈(collect_all로 딸려옴)만 쓰고 형태소 분석에는 안 쓴다. 약 65MB 절약.
    excludes=["tkinter", "pytest", "ruff", "numpy", "scipy"],
    noarchive=False,
)


def _keep(entry) -> bool:
    dest = entry[0].replace("\\", "/")
    if "/translations/" in dest:            # Qt 번역 99개 언어 중 한국어만
        return "_ko." in dest.rsplit("/", 1)[-1]
    return True


a.datas = [e for e in a.datas if _keep(e)]
pyz = PYZ(a.pure)

icon = ROOT / "build" / "jonnyang.ico"


def _version_info():
    """exe 속성의 '자세히' 탭 정보(제품 이름·버전·설명). 이게 없는 서명 안 된 exe는 백신이 더 의심한다."""
    if sys.platform != "win32":
        return None
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    ver = next(line.split('"')[1] for line in (ROOT / "src" / "jonnyang" / "__init__.py").read_text(
        encoding="utf-8").splitlines() if line.startswith("__version__"))
    nums = tuple(int(x) for x in (ver.split(".") + ["0"] * 4)[:4])
    strings = [StringStruct("CompanyName", "Jonnyang"),
               StringStruct("FileDescription", "Jonnyang desktop pet assistant"),
               StringStruct("FileVersion", ver),
               StringStruct("InternalName", "Jonnyang"),
               StringStruct("LegalCopyright", "Jonnyang project"),
               StringStruct("OriginalFilename", "Jonnyang.exe"),
               StringStruct("ProductName", "Jonnyang"),
               StringStruct("ProductVersion", ver)]
    return VSVersionInfo(ffi=FixedFileInfo(filevers=nums, prodvers=nums),
                         kids=[StringFileInfo([StringTable("041204B0", strings)]),
                               VarFileInfo([VarStruct("Translation", [0x0412, 1200])])])


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jonnyang",
    console=False,               # 펫만 뜨고 검은 콘솔 창은 안 뜬다
    icon=str(icon) if icon.exists() else None,
    version=_version_info(),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Jonnyang", upx=False)
