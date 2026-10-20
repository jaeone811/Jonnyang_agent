"""콘솔 채팅 입력 루프."""

from __future__ import annotations

import sys

from jonnyang.core.console import Console

EXIT_WORDS = {"종료", "exit", "quit", "/q", "/exit", "잘 가", "잘가", "바이", "끝"}


def _debug(dispatcher, line: str) -> list[str]:
    cmd, _, arg = line.partition(" ")
    it = dispatcher.interpret(arg)
    req = it.req
    if cmd == "/time":
        t = req.time
        return [f"text={req.text!r} at={t.at} duration={t.duration} relative={t.relative} "
                f"error={t.error} assumed={t.assumed}"]
    top = ", ".join(f"{c.intent.name}={c.score:.2f}" for c in it.candidates[:4])
    return [f"text={req.text!r}", f"morphs={[(m.form, m.tag) for m in req.morphs]}",
            f"lemmas={req.lemmas} groups={sorted(req.groups)} negated={req.negated} excluded={req.excluded}",
            f"time: at={req.time.at} duration={req.time.duration} error={req.time.error}",
            f"=> {it.kind} {it.intent.name if it.intent else ''} slots={it.slots} | {top}"]


def main() -> None:
    console = Console()
    from jonnyang.core.config import load_yaml

    persona_data = load_yaml("persona.yaml")
    banner = persona_data.get("banner")
    if banner:
        console.raw(banner.rstrip())
    console.say([persona_data.get("loading", "...")])

    from jonnyang.app import build_app
    from jonnyang.platform.system import system_platform

    ctx, dispatcher = build_app(platform=system_platform(), sink=console.notify)
    ctx.scheduler.on_error = lambda exc: console.notify([f"[scheduler error] {exc!r}"])
    console.say(dispatcher.startup())
    ctx.scheduler.start()
    try:
        while True:
            try:
                line = console.read().strip()
            except EOFError:
                break
            if not line:
                continue
            if line in EXIT_WORDS:
                break
            if line.startswith(("/nlu ", "/time ")):
                console.say(_debug(dispatcher, line))
                continue
            try:
                console.say(dispatcher.handle(line))
            except Exception as exc:  # 한 명령의 오류로 프로그램이 죽지 않게
                console.say([ctx.persona.say("error.internal", {"reason": repr(exc)}, core=("reason",))])
    except KeyboardInterrupt:
        pass
    finally:
        console.say([ctx.persona.say("farewell")])
        ctx.scheduler.stop()
        ctx.storage.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
