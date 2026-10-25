"""파일 찾기·열기·정리·이동·이름 바꾸기·휴지통.

안전 규칙
- 작업 범위는 aliases.yaml의 folders(바탕화면, 다운로드 등) 안쪽뿐이다. 실행 직전에 다시 확인한다.
- 휴지통·이동·정리는 대상 목록을 보여주고 확인을 받는다. 삭제는 Send2Trash(휴지통)만, 영구삭제 없음.
- 이동·정리·이름 바꾸기는 history에 기록해 "되돌려"로 원래대로 돌린다. 덮어쓰기는 하지 않는다(" (2)" 붙임).
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jonnyang.core.config import load_yaml
from jonnyang.nlu.matcher import Intent
from jonnyang.persona.fmt import Bytes
from jonnyang.platform.base import Unsupported
from jonnyang.skills.base import Confirm, Result, Skill

NO_RE = re.compile(r"(\d+)\s*번")
ALL_RE = re.compile(r"(?:방금|아까|찾은|위에|그)\s*(?:찾은\s*)?(?:거|것|파일|애들|목록)|전부|모두"
                    r"|다\s*(?:지워|버려|삭제|옮겨)")
OLD_RE = re.compile(r"오래된|예전|묵은|한\s*달\s*(?:넘은|지난)|지난\s*달")
BAD_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
STOP_WORDS = {"파일", "폴더", "거", "것", "방금", "아까", "전부", "모두", "좀", "다", "찾", "찾기", "검색", "어디",
              "있",
              "번", "이름", "휴지통", "정리", "존냥", "존냥이", "내", "제", "나", "안", "전체"}


@dataclass
class Found:
    path: Path
    root_name: str
    size: int
    mtime: float


def _index_hint(skill: "FileSkill"):
    def hint(req) -> float:
        if NO_RE.search(req.text) and skill.last and skill.ctx.storage.get_setting("recent.list") == "files":
            return 0.4
        return 0.0
    return hint


class FileSkill(Skill):
    name = "files"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = load_yaml("files.yaml", ctx.config_dir)
        self.last: list[Found] = []
        self.intents = [
            Intent("files.search", nouns={"파일": 0.6, "화일": 0.6, "자료": 0.3}, verbs={"SHOW": 0.1},
                   extras={"찾": 0.4, "검색": 0.3, "어디": 0.2}, hint=self._search_hint,
                   avoid={"CANCEL": 0.5, "OPEN": 0.4, "SET": 0.4, "ADD": 0.4, "휴지통": 0.5, "버리": 0.5,
                          "옮기": 0.5, "이동": 0.5, "정리": 0.4},
                   examples=("다운로드에서 pdf 찾아줘", "보고서 파일 찾아줘")),
            Intent("files.open", nouns={"파일": 0.5}, verbs={"OPEN": 0.3}, hint=_index_hint(self),
                   avoid={"CANCEL": 0.5, "CLOSE": 0.5, "옮기": 0.6, "이동": 0.6, "이름": 0.6, "휴지통": 0.6,
                          "버리": 0.6, "찾": 0.4},
                   required=("index",), examples=("1번 파일 열어줘",)),
            Intent("files.organize", nouns={"정리": 0.6, "폴더": 0.1, "파일": 0.2}, extras={"종류": 0.2, "분류": 0.3},
                   hint=lambda req: 0.3 if self._folder_in(req) else 0.0,
                   avoid={"CANCEL": 0.4, "ADD": 0.4, "SHOW": 0.2},
                   examples=("다운로드 폴더 정리해줘",)),
            Intent("files.trash", nouns={"휴지통": 0.7, "파일": 0.4}, verbs={"CANCEL": 0.4},
                   extras={"버리": 0.4}, hint=self._trash_hint, avoid={"SET": 0.4, "ADD": 0.4, "OPEN": 0.4},
                   examples=("방금 찾은 거 휴지통에 버려", "다운로드에서 zip 파일 지워줘")),
            Intent("files.move", nouns={"파일": 0.4, "폴더": 0.2}, extras={"옮기": 0.5, "이동": 0.5},
                   hint=_index_hint(self), avoid={"CANCEL": 0.4}, examples=("1번 파일 문서 폴더로 옮겨줘",)),
            Intent("files.rename", nouns={"이름": 0.5, "파일명": 0.7}, extras={"바꾸": 0.3, "변경": 0.3},
                   hint=lambda req: 0.2 if req.quoted else 0.0, avoid={"CANCEL": 0.4, "CALL": 0.3},
                   examples=("1번 파일 이름을 '최종 보고서'로 바꿔줘",)),
        ]

    # ── 단어 ──
    def _type_words(self) -> dict[str, list[str]]:
        cats = {k: [e.lower() for e in v] for k, v in (self.cfg.get("categories") or {}).items()}
        out: dict[str, list[str]] = {}
        for word, spec in (self.cfg.get("type_words") or {}).items():
            out[str(word).lower()] = cats.get(spec, []) if isinstance(spec, str) else [str(e).lower() for e in spec]
        return out

    def protected_words(self) -> set[str]:
        return set(self._type_words()) | {"휴지통", "파일명"}

    def _folders(self) -> dict[str, str]:
        return {n: t for n, (k, t) in self.ctx.aliases.all().items() if k == "folder"}

    def _folder_in(self, req, exclude: str | None = None) -> str | None:
        names = [n for n in self._folders() if n != exclude and n.replace(" ", "") in req.compact]
        if not names:
            return None
        # 문장에서 먼저 나온 폴더 (예: "다운로드에서 ... 문서 폴더로" → 다운로드)
        return min(names, key=lambda n: (req.compact.find(n.replace(" ", "")), -len(n)))

    def _target_folder(self, req, source: str | None) -> str | None:
        """'~ 폴더로/으로' 의 폴더."""
        for n in sorted(self._folders(), key=len, reverse=True):
            if re.search(rf"{re.escape(n)}\s*(?:폴더)?\s*(?:로|으로|에)\b", req.text) and n != source:
                return n
        return None

    def _exts(self, req) -> list[str]:
        words = self._type_words()
        known = {e.lower() for v in (self.cfg.get("categories") or {}).values() for e in v}
        exts: list[str] = []
        for lemma in req.lemmas:
            exts += words.get(lemma.lower(), [])
        # 영문 확장자는 형태소 분석이 쪼갤 수 있어서("mp3" → mp/3) 원문에서 찾는다
        for m in re.finditer(r"(?<![A-Za-z0-9])\.?([A-Za-z][A-Za-z0-9]{1,4})(?![A-Za-z0-9])(\s*파일)?", req.text):
            word = m.group(1).lower()
            if word in words:
                exts += words[word]
            elif word in known or m.group(2):
                exts.append(word)
        return sorted(set(exts))

    def _keyword(self, req) -> str | None:
        if req.quoted:
            return req.quoted[0]
        words = self._type_words()
        folders = {n.replace(" ", "") for n in self._folders()}
        m = re.search(r"[파화]일", req.text)
        if m is None:
            return None
        file_pos = m.start()
        for lemma in req.lemmas:          # "보고서 파일 찾아줘" → 보고서 ("파일" 앞에 온 이름)
            if (len(lemma) >= 2 and lemma not in STOP_WORDS and lemma.lower() not in words and lemma not in folders
                    and re.fullmatch(r"[가-힣A-Za-z0-9_\-]+", lemma)):
                pos = req.text.find(lemma)
                if 0 <= pos < file_pos:
                    return lemma
        return None

    def _search_hint(self, req) -> float:
        if not (self._exts(req) or self._keyword(req)) or not ({"찾", "있", "검색"} & req.lemma_set):
            return 0.0
        return 0.5 if self._folder_in(req) else 0.3

    def _trash_hint(self, req) -> float:
        if "휴지통" in req.compact:
            return 0.2
        if ("CANCEL" in req.groups or "버리" in req.lemma_set) and (self._exts(req) or (
                ALL_RE.search(req.text) and self.last and self.ctx.storage.get_setting("recent.list") == "files")):
            return 0.3
        return 0.0

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        m = NO_RE.search(req.text)
        if m:
            slots["index"] = int(m.group(1))
        folder = self._folder_in(req)
        if folder:
            slots["folder"] = folder
        if intent == "files.move":
            dst = self._target_folder(req, None if "index" in slots else folder)
            if dst:
                slots["dest"] = dst
                if slots.get("folder") == dst:
                    slots.pop("folder")
        if intent == "files.rename" and req.quoted:
            slots["new_name"] = req.quoted[-1]
        exts = self._exts(req)
        if exts:
            slots["exts"] = exts
        kw = self._keyword(req)
        if kw:
            slots["keyword"] = kw
        if OLD_RE.search(req.text):
            slots["old"] = True
        if ALL_RE.search(req.text):
            slots["all_last"] = True
        return slots

    # ── 경로 ──
    def _root(self, name: str) -> Path | None:
        target = self._folders().get(name)
        if target is None:
            return None
        return self.ctx.platform.files.folder(target)

    def _roots(self) -> dict[str, Path]:
        out = {}
        for name in self._folders():
            try:
                p = self._root(name)
            except OSError:
                continue
            if p is not None:
                out[name] = p
        return out

    def _inside(self, path: Path) -> bool:
        """작업 대상이 등록된 폴더 안인지 (심볼릭 링크로 밖을 가리키는 것도 막는다)."""
        try:
            real = path.resolve()
        except OSError:
            return False
        for root in self._roots().values():
            try:
                real.relative_to(root.resolve())
                return real != root.resolve()
            except (ValueError, OSError):
                continue
        return False

    def _skip(self, p: Path) -> bool:
        name = p.name.lower()
        if name.startswith((".", "~$")) or name in [n.lower() for n in self.cfg.get("skip_names", [])]:
            return True
        return any(name.endswith(s.lower()) for s in self.cfg.get("skip_suffixes", []))

    def _scan(self, roots: dict[str, Path], exts: list[str], keyword: str | None, old: bool) -> tuple[list[Found], int]:
        max_depth = int(self.cfg.get("max_depth", 3))
        budget = int(self.cfg.get("max_scan", 5000))
        skip_dirs = {d.lower() for d in self.cfg.get("skip_dirs", [])}
        cutoff = time.time() - int(self.cfg.get("old_days", 30)) * 86400
        kw = keyword.lower() if keyword else None
        found: list[Found] = []
        for root_name, root in roots.items():
            if not root.is_dir():
                continue
            stack = [(root, 0)]
            while stack and budget > 0:
                folder, depth = stack.pop()
                try:
                    entries = list(os.scandir(folder))
                except OSError:
                    continue
                for e in entries:
                    budget -= 1
                    if budget <= 0:
                        break
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if depth < max_depth and e.name.lower() not in skip_dirs and not e.name.startswith("."):
                                stack.append((Path(e.path), depth + 1))
                            continue
                        if not e.is_file(follow_symlinks=False):
                            continue
                        p = Path(e.path)
                        if self._skip(p):
                            continue
                        if exts and p.suffix.lower().lstrip(".") not in exts:
                            continue
                        if kw and kw not in p.name.lower():
                            continue
                        st = e.stat(follow_symlinks=False)
                        if old and st.st_mtime > cutoff:
                            continue
                        found.append(Found(p, root_name, st.st_size, st.st_mtime))
                    except OSError:
                        continue
        found.sort(key=lambda f: f.mtime, reverse=True)
        return found, budget

    def _items(self, found: list[Found]) -> list[dict[str, Any]]:
        roots = self._roots()
        out = []
        for i, f in enumerate(found, 1):
            where = f.root_name
            root = roots.get(f.root_name)
            if root is not None and f.path.parent != root:
                try:
                    where = f"{f.root_name}/{f.path.parent.relative_to(root).as_posix()}"
                except ValueError:
                    pass
            out.append({"no": i, "name": f.path.name, "where": where, "size": Bytes(f.size),
                        "mtime": datetime.fromtimestamp(f.mtime)})
        return out

    def _remember(self, found: list[Found]) -> None:
        self.last = found
        self.ctx.storage.set_setting("recent.list", "files")

    # ── 실행 ──
    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result | Confirm:
        try:
            if intent == "files.search":
                return self._search(slots)
            if intent == "files.open":
                return self._open(slots)
            if intent == "files.organize":
                return self._organize(slots)
            if intent == "files.trash":
                return self._trash(slots)
            if intent == "files.move":
                return self._move(slots)
            if intent == "files.rename":
                return self._rename(slots)
        except Unsupported:
            return Result("error.unsupported", ok=False)
        raise ValueError(intent)

    def _search_roots(self, slots: dict[str, Any]) -> dict[str, Path]:
        roots = self._roots()
        if slots.get("folder") in roots:
            return {slots["folder"]: roots[slots["folder"]]}
        default = self.cfg.get("search_folders") or list(roots)
        return {n: roots[n] for n in default if n in roots}

    def _search(self, slots: dict[str, Any]) -> Result:
        exts, kw = slots.get("exts", []), slots.get("keyword")
        if not exts and not kw and not slots.get("old"):
            return Result("files.ask_what")
        roots = self._search_roots(slots)
        found, budget = self._scan(roots, exts, kw, bool(slots.get("old")))
        where = ", ".join(roots)
        if not found:
            return Result("files.none", {"where": where, "what": kw or ", ".join(exts) or "-"}, core=("where",))
        shown = found[: int(self.cfg.get("max_results", 10))]
        self._remember(shown)
        key = "files.found_more" if len(found) > len(shown) else "files.found"
        return Result(key, {"count": len(found), "shown": len(shown), "where": where}, core=("count",),
                      items=self._items(shown), item_key="files.item")

    def _pick(self, slots: dict[str, Any]) -> list[Found] | Result:
        if not self.last:
            return Result("files.no_list", ok=False)
        if "index" in slots:
            i = slots["index"]
            if not 1 <= i <= len(self.last):
                return Result("files.bad_index", {"count": len(self.last)}, core=("count",), ok=False)
            return [self.last[i - 1]]
        return list(self.last)

    def _open(self, slots: dict[str, Any]) -> Result:
        picked = self._pick(slots)
        if isinstance(picked, Result):
            return picked
        f = picked[0]
        if not f.path.exists() or not self._inside(f.path):
            return Result("files.gone", {"name": f.path.name}, core=("name",), ok=False)
        try:
            self.ctx.platform.launcher.open(str(f.path))
        except OSError as exc:
            return Result("app.error", {"name": f.path.name, "target": str(f.path), "reason": str(exc)},
                          core=("name", "target", "reason"), ok=False)
        return Result("files.opened", {"name": f.path.name}, core=("name",))

    def _targets(self, slots: dict[str, Any]) -> list[Found] | Result:
        """휴지통·이동 대상: 번호 > '방금 찾은 거' > 조건(폴더+종류/이름)으로 새로 찾기."""
        if "index" in slots or (slots.get("all_last") and self.last and not slots.get("exts")):
            return self._pick(slots)
        if not slots.get("exts") and not slots.get("keyword") and not slots.get("old"):
            return Result("files.ask_which", ok=False)
        found, _ = self._scan(self._search_roots(slots), slots.get("exts", []), slots.get("keyword"),
                              bool(slots.get("old")))
        return found

    def _check_batch(self, found: list[Found]) -> Result | None:
        if not found:
            return Result("files.none_target")
        limit = int(self.cfg.get("max_batch", 30))
        if len(found) > limit:
            return Result("files.too_many", {"count": len(found), "limit": limit}, core=("count", "limit"), ok=False)
        return None

    def _trash(self, slots: dict[str, Any]) -> Result | Confirm:
        found = self._targets(slots)
        if isinstance(found, Result):
            return found
        bad = self._check_batch(found)
        if bad:
            return bad
        items = self._items(found)

        def do_trash() -> Result:
            paths = [str(f.path) for f in found if f.path.exists() and self._inside(f.path)]
            if not paths:
                return Result("files.none_target")
            try:
                self.ctx.platform.files.trash(paths)
            except OSError as exc:
                return Result("files.error", {"reason": str(exc)}, core=("reason",), ok=False)
            self.last = [f for f in self.last if str(f.path) not in paths]
            return Result("files.trashed", {"count": len(paths)}, core=("count",))
        return Confirm("confirm.files_trash", do_trash, {"count": len(found)}, core=("count",), items=items,
                       item_key="files.item")

    @staticmethod
    def _free_name(dst: Path) -> Path:
        if not dst.exists():
            return dst
        for i in range(2, 1000):
            cand = dst.with_name(f"{dst.stem} ({i}){dst.suffix}")
            if not cand.exists():
                return cand
        raise OSError("이름이 겹치는 파일이 너무 많음")

    def _do_moves(self, plan: list[tuple[Path, Path]]) -> tuple[list[list[str]], list[str]]:
        moves: list[list[str]] = []
        made: list[str] = []
        for src, dst_dir in plan:
            if not src.exists() or not self._inside(src):
                continue
            if not dst_dir.exists():
                dst_dir.mkdir(parents=True)
                made.append(str(dst_dir))
            dst = self._free_name(dst_dir / src.name)
            os.rename(src, dst)                     # 같은 드라이브 안 이동 (덮어쓰기 없음: _free_name)
            moves.append([str(src), str(dst)])
        return moves, made

    def _move(self, slots: dict[str, Any]) -> Result | Confirm:
        if "dest" not in slots:
            return Result("files.ask_dest")
        found = self._targets(slots)
        if isinstance(found, Result):
            return found
        bad = self._check_batch(found)
        if bad:
            return bad
        dest_root = self._root(slots["dest"])
        items = self._items(found)

        def do_move() -> Result:
            try:
                moves, made = self._do_moves([(f.path, dest_root) for f in found])
            except OSError as exc:
                return Result("files.error", {"reason": str(exc)}, core=("reason",), ok=False)
            self.last = []
            return Result("files.moved", {"count": len(moves), "dest": slots["dest"]}, core=("count", "dest"),
                          undo={"moves": moves, "made": made}, undo_label="files.move")
        return Confirm("confirm.files_move", do_move, {"count": len(found), "dest": slots["dest"]},
                       core=("count", "dest"), items=items, item_key="files.item")

    def _organize(self, slots: dict[str, Any]) -> Result | Confirm:
        name = slots.get("folder")
        if not name:
            return Result("files.ask_folder")
        root = self._root(name)
        if root is None or not root.is_dir():
            return Result("files.no_folder", {"folder": name}, core=("folder",), ok=False)
        cats = {k: [e.lower() for e in v] for k, v in (self.cfg.get("categories") or {}).items()}
        plan: list[tuple[Path, Path]] = []
        counts: dict[str, list[str]] = {}
        recent = time.time() - 60          # 방금 받는 중인 파일은 건드리지 않는다
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError as exc:
            return Result("files.error", {"reason": str(exc)}, core=("reason",), ok=False)
        for e in entries:
            try:
                if not e.is_file(follow_symlinks=False) or self._skip(Path(e.path)):
                    continue
                if e.stat().st_mtime > recent:
                    continue
            except OSError:
                continue
            ext = Path(e.name).suffix.lower().lstrip(".")
            cat = next((c for c, exts in cats.items() if ext in exts), None)
            if cat:
                plan.append((Path(e.path), root / cat))
                counts.setdefault(cat, []).append(e.name)
        if not plan:
            return Result("files.organize_nothing", {"folder": name}, core=("folder",))
        items = [{"category": c, "count": len(n), "examples": ", ".join(n[:3]) + (" …" if len(n) > 3 else "")}
                 for c, n in counts.items()]

        def do_organize() -> Result:
            try:
                moves, made = self._do_moves(plan)
            except OSError as exc:
                return Result("files.error", {"reason": str(exc)}, core=("reason",), ok=False)
            return Result("files.organized", {"count": len(moves), "folder": name}, core=("count", "folder"),
                          undo={"moves": moves, "made": made}, undo_label="files.organize")
        return Confirm("confirm.files_organize", do_organize, {"count": len(plan), "folder": name},
                       core=("count", "folder"), items=items, item_key="files.organize_item")

    def _rename(self, slots: dict[str, Any]) -> Result:
        new = (slots.get("new_name") or "").strip()
        if not new:
            return Result("files.ask_name")
        picked = self._pick(slots)
        if isinstance(picked, Result):
            return picked
        if len(picked) != 1:
            return Result("files.ask_which", ok=False)
        f = picked[0]
        if BAD_NAME_RE.search(new) or new in (".", ".."):
            return Result("files.bad_name", {"name": new}, core=("name",), ok=False)
        if not Path(new).suffix and f.path.suffix:
            new += f.path.suffix                 # 확장자를 안 말하면 원래 확장자 유지
        dst = f.path.with_name(new)
        if not f.path.exists() or not self._inside(f.path):
            return Result("files.gone", {"name": f.path.name}, core=("name",), ok=False)
        if dst.exists():
            return Result("files.name_taken", {"name": new}, core=("name",), ok=False)
        os.rename(f.path, dst)
        self.last = [Found(dst, x.root_name, x.size, x.mtime) if x is f else x for x in self.last]
        return Result("files.renamed", {"old": f.path.name, "new": new}, core=("old", "new"),
                      undo={"moves": [[str(f.path), str(dst)]], "made": []}, undo_label="files.rename")

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        restored = 0
        for src, dst in reversed(payload.get("moves", [])):
            s, d = Path(src), Path(dst)
            if d.exists() and not s.exists() and self._inside(d):
                s.parent.mkdir(parents=True, exist_ok=True)
                os.rename(d, s)
                restored += 1
        for folder in reversed(payload.get("made", [])):
            try:
                Path(folder).rmdir()                # 비어 있을 때만 지워진다
            except OSError:
                pass
        if payload.get("moves") and restored == 0:
            return Result("undo.expired", ok=False)
        return Result("undo.done")
