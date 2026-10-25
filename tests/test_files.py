"""파일 스킬. 모든 파일 작업은 pytest 임시 폴더(tmp_path) 안에서만 한다."""

import os
import time

import pytest


@pytest.fixture
def fs(make_app, tmp_path):
    dl = tmp_path / "Downloads"
    docs = tmp_path / "Documents"
    desk = tmp_path / "Desktop"
    for d in (dl, docs, desk):
        d.mkdir()
    old = time.time() - 90 * 86400
    files = {
        dl / "보고서_최종.pdf": b"%PDF", dl / "사진1.jpg": b"jpg", dl / "사진2.png": b"png",
        dl / "setup.exe": b"MZ", dl / "자료.zip": b"PK", dl / "메모.txt": b"hi", dl / "받는중.pdf.crdownload": b"..",
        dl / "이상한.xyz": b"?", docs / "계약서.docx": b"doc", desk / "예산.xlsx": b"xls",
        dl / "깊은" / "안쪽" / "보고서_초안.pdf": b"%PDF",
    }
    for p, data in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.utime(p, (old, old))                    # 1분 안에 바뀐 파일은 정리 대상에서 빠지므로 예전 파일로 만든다
    app = make_app(files_root=tmp_path)
    app.root = tmp_path
    return app


def test_search_by_type_in_folder(fs):
    out = fs.say("다운로드에서 pdf 찾아줘")
    assert "보고서_최종.pdf" in out and "보고서_초안.pdf" in out and "다운로드/깊은/안쪽" in out
    assert "crdownload" not in out


def test_search_by_name_default_folders(fs):
    out = fs.say("'계약서' 파일 찾아줘")
    assert "계약서.docx" in out and "문서" in out
    out = fs.say("엑셀 파일 찾아줘")
    assert "예산.xlsx" in out


def test_search_nothing(fs):
    assert "못 찾았" in fs.say("다운로드에서 mp3 찾아줘")


def test_open_found_file_by_number(fs):
    fs.say("다운로드에서 pdf 찾아줘")
    fs.say("1번 파일 열어줘")
    assert fs.platform.launcher.opened and fs.platform.launcher.opened[0].endswith(".pdf")


def test_trash_needs_confirmation_and_lists_targets(fs):
    out = fs.say("다운로드에서 zip 파일 지워줘")
    assert "자료.zip" in out and "(응/아니)" in out
    assert (fs.root / "Downloads" / "자료.zip").exists()        # 확인 전에는 안 건드린다
    out = fs.say("응")
    assert "휴지통" in out
    assert not (fs.root / "Downloads" / "자료.zip").exists()
    assert (fs.root / ".trash" / "자료.zip").exists()           # 영구삭제가 아니라 휴지통(가짜)으로


def test_trash_cancel_keeps_files(fs):
    fs.say("다운로드에서 zip 파일 지워줘")
    fs.say("아니")
    assert (fs.root / "Downloads" / "자료.zip").exists()


def test_trash_found_list(fs):
    fs.say("다운로드에서 pdf 찾아줘")
    out = fs.say("방금 찾은 거 휴지통에 버려")
    assert "보고서_최종.pdf" in out and "보고서_초안.pdf" in out
    fs.say("응")
    assert not (fs.root / "Downloads" / "보고서_최종.pdf").exists()


def test_trash_without_filter_asks(fs):
    out = fs.say("다운로드 파일 지워줘")
    assert "(응/아니)" not in out


def test_organize_confirm_then_undo(fs):
    dl = fs.root / "Downloads"
    out = fs.say("다운로드 폴더 정리해줘")
    assert "이미지: 2개" in out and "(응/아니)" in out and "설치파일" in out
    assert (dl / "사진1.jpg").exists()
    out = fs.say("응")
    assert "정리했다" in out
    assert (dl / "이미지" / "사진1.jpg").exists() and (dl / "설치파일" / "setup.exe").exists()
    assert (dl / "이상한.xyz").exists()                          # 모르는 확장자는 그대로
    assert (dl / "받는중.pdf.crdownload").exists()               # 받는 중인 파일은 안 건드린다
    fs.say("되돌려줘")
    fs.say("응")
    assert (dl / "사진1.jpg").exists() and not (dl / "이미지").exists()


def test_organize_never_overwrites(fs):
    dl = fs.root / "Downloads"
    (dl / "이미지").mkdir()
    (dl / "이미지" / "사진1.jpg").write_bytes(b"other")
    fs.say("다운로드 폴더 정리해줘")
    fs.say("응")
    assert (dl / "이미지" / "사진1.jpg").read_bytes() == b"other"
    assert (dl / "이미지" / "사진1 (2).jpg").read_bytes() == b"jpg"


def test_move_and_undo(fs):
    fs.say("다운로드에서 pdf 찾아줘")
    out = fs.say("1번 파일 문서 폴더로 옮겨줘")
    assert "(응/아니)" in out and "문서" in out
    fs.say("응")
    moved = list((fs.root / "Documents").glob("*.pdf"))
    assert len(moved) == 1
    fs.say("되돌려줘")
    fs.say("응")
    assert not list((fs.root / "Documents").glob("*.pdf"))


def test_rename_keeps_extension_and_undo(fs):
    fs.say("다운로드에서 txt 찾아줘")
    out = fs.say("1번 파일 이름을 '중요 메모'로 바꿔줘")
    assert "중요 메모.txt" in out
    assert (fs.root / "Downloads" / "중요 메모.txt").exists()
    fs.say("되돌려줘")
    fs.say("응")
    assert (fs.root / "Downloads" / "메모.txt").exists()


def test_rename_rejects_bad_name_and_existing(fs):
    fs.say("다운로드에서 txt 찾아줘")
    assert "못 쓴다" in fs.say("1번 파일 이름을 'a/b'로 바꿔줘")
    assert "이미" in fs.say("1번 파일 이름을 '자료.zip'으로 바꿔줘")


def test_only_inside_known_folders(fs, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside.pdf"
    outside.write_bytes(b"x")
    try:
        skill = fs.ctx.skills["files"]
        assert not skill._inside(outside)
        assert not skill._inside(fs.root / "Downloads")          # 폴더 자체는 대상이 아니다
        assert skill._inside(fs.root / "Downloads" / "메모.txt")
    finally:
        outside.unlink()


def test_files_unsupported_without_platform(app):
    assert "Windows" in app.say("다운로드에서 pdf 찾아줘")
