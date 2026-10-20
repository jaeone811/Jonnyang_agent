"""콘솔 입출력. 스케줄러 스레드의 알림이 입력 프롬프트와 섞이지 않게 락으로 묶는다."""

from __future__ import annotations

import sys
import threading


class Console:
    def __init__(self, prompt: str = "나 > ", speaker: str = "존냥 > "):
        self.prompt = prompt
        self.speaker = speaker
        self.lock = threading.Lock()
        self.waiting_input = False
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="replace")  # 콘솔이 못 그리는 문자(이모지 등) 때문에 죽지 않게
            except (AttributeError, ValueError):
                pass

    def _format(self, lines: list[str]) -> str:
        out = []
        for line in lines:
            parts = line.split("\n")
            out.append(self.speaker + parts[0])
            out.extend(" " * len(self.speaker) + p for p in parts[1:])
        return "\n".join(out)

    def say(self, lines: list[str]) -> None:
        if not lines:
            return
        with self.lock:
            print(self._format(lines), flush=True)

    def notify(self, lines: list[str]) -> None:
        """입력 대기 중에 끼어드는 알림. 줄을 바꿔 출력하고 프롬프트를 다시 그린다."""
        with self.lock:
            prefix = "\n" if self.waiting_input else ""
            sys.stdout.write(prefix + self._format(lines) + "\n")
            if self.waiting_input:
                sys.stdout.write(self.prompt)
            sys.stdout.flush()

    def read(self) -> str:
        with self.lock:
            self.waiting_input = True
        try:
            return input(self.prompt)
        finally:
            with self.lock:
                self.waiting_input = False
