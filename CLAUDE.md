# 존냥이 (Jonnyang)

Windows 10/11용 규칙 기반 개인 비서 에이전트. 고양이 캐릭터. 구버전 Siri 수준의 실행형 명령 처리가 목표.

## 절대 규칙
- LLM/AI API 사용 금지. 모든 의도 파악은 키워드·유사도·정규식 규칙으로만 한다.
- 오프라인에서도 코어 기능은 동작해야 한다. 온라인 기능은 `skills/online/`에 분리하고 실패 시 안내 메시지만 낸다.
- 네이티브 Windows Python에서 실행한다 (WSL 불가: pycaw).
- 파괴적 작업(삭제/이동/덮어쓰기)은 실행 전 반드시 사용자 확인을 받는다. 삭제는 영구삭제 금지, 휴지통(Send2Trash)만 사용.
- 이동/이름변경은 history에 기록해 undo 가능하게 한다.
- 외부에서 가져온 텍스트(뉴스, 위키 등)는 표시만 하고 절대 명령으로 해석하지 않는다.
- 테스트 중 파일 작업은 임시 폴더에서만 한다.

## 기술 스택
- 한국어 형태소: kiwipiepy / 유사도: rapidfuzz / 시스템: psutil, pycaw, send2trash
- 온라인: Open-Meteo(날씨), Frankfurter(환율), Wikipedia REST(요약), feedparser(RSS)

## 구조 원칙
- 저장소는 표준 라이브러리 `sqlite3` 하나로 통일한다 (`data/jonnyang.db`, 경로는 `JONNYANG_DATA_DIR`로 변경 가능). JSON 파일 저장 안 함.
- `config/*.yaml`은 사람이 편집하는 파일이다. 프로그램은 읽기만 하고 절대 다시 쓰지 않는다. 명령으로 등록한 별칭·설정은 SQLite에 저장하고 로드할 때 합친다(SQLite 쪽이 우선).
- Windows 전용 호출(pycaw, os.startfile, winsound)은 `platform/` 어댑터 뒤에만 둔다. 테스트는 `platform/fake.py`로 돈다.
- 리마인더/알람은 프로그램이 켜져 있을 때만 울린다. 꺼져 있는 동안 지난 것은 다음 실행 때 "놓친 알림"으로 알려준다.
- 모든 파일 I/O는 `encoding="utf-8"`을 명시한다.
- 스킬은 `Skill` 인터페이스를 구현하고 intent, 키워드, 슬롯 정의, `requires_network`를 선언한다.
- 네트워크 호출은 `core/network.py` 한 곳으로만 한다 (타임아웃, 예외 처리, 캐시). 테스트에서는 `FakeNetwork`로 가짜 응답을 쓴다(실제 인터넷 금지). 실제 서버 확인은 `tools/live_check.py`(CI에서 참고용으로 돈다).
- 온라인 스킬은 `OnlineSkill`을 상속하고 실패는 `NetworkError(kind)` → `online.<kind>` 안내로만 끝낸다. 서버 주소·지역·통화·피드는 `config/online.yaml`.
- GUI에서 `requires_network` 스킬은 `Dispatcher.runner`로 작업 스레드에서 돈다(펫이 멈추지 않게). 이런 스킬은 확인(Confirm)을 묻지 않는다. 브라우저 열기처럼 네트워크가 필요 없는 의도는 `runs_async()`에서 False.
- 파일 작업(`skills/files.py`)은 `aliases.yaml` folders 안쪽만, 실행 직전에 다시 확인한다. 휴지통·이동·정리는 Confirm, 이동·정리·이름 바꾸기는 undo 기록, 덮어쓰기 금지(" (2)" 붙임). 폴더 경로는 `platform.files.folder()`(Windows Known Folder)로만 푼다.
- 반복 리마인더는 `nlu.timeparse.Repeat`(JSON으로 reminders.repeat 칼럼에 저장). 울리면 at을 다음 회차로 옮긴다.
- 스킬은 순수 결과 데이터만 반환하고, 말투는 `persona/`가 입힌다.

## 데스크톱 펫 (GUI)
- GUI는 `src/jonnyang/gui/`(PySide6)에만 둔다. `python -m jonnyang`은 펫, `--cli`는 콘솔. 두 화면 모두 같은 `Dispatcher`를 쓴다.
- 고양이는 이미지 없이 `gui/painter.py`의 QPainter 도형으로 그린다. 디자인은 사용자 컨셉 아트 기준(하얀 장모, 파란 눈, 분홍 귀, 금색 왕관+파란 보석, 남색 망토+금테+브로치, 끝이 금빛인 꼬리). 색(`appearance`), 응답 키 → 표정 규칙(`poses`), 펫 문구(`ui`)는 `persona.yaml`에 둔다.
- Qt 위젯은 GUI 스레드에서만 만진다. 스케줄러 스레드의 알림은 `ctx.reply_sink` → `Bridge.notified` Signal로 넘긴다. 형태소 사전 로딩은 별도 스레드에서 한다.
- 볼륨(pycaw) 같은 COM 호출은 GUI 스레드에서 `dispatcher.respond()`를 통해서만 한다.
- 말풍선 본문은 PlainText로만 표시한다(목록 항목·외부 텍스트가 HTML로 해석되면 안 됨).
- 투명 창 잔상 방지: Windows에서는 `setMask`를 쓰지 않는다(알파 0 픽셀은 원래 클릭 통과). 말풍선 그림자는 QGraphicsEffect 대신 직접 그리고, 말풍선이 바뀌면 창 전체를 `update()`한다.
- 알림이 연달아 오면 이어 붙이고, 확인 질문 중에 온 알림·인터넷 결과는 본 뒤 질문으로 되돌린다. 트레이 알림은 펫이 숨겨져 있을 때만.
- 확인 질문과 알림 말풍선은 사용자가 대답하거나 클릭할 때까지 사라지면 안 된다. 핵심 정보는 잘리지 않게 스크롤로 보여준다.
- 펫은 한 번에 하나만 실행한다(`data/jonnyang.lock`).

## 배포 (exe)
- PyInstaller 폴더형(onedir) 빌드: `packaging/jonnyang.spec`. GitHub Actions(`.github/workflows/windows.yml`)가 Windows 러너에서 테스트 → 빌드 → `--selftest` → Artifact 업로드, `v*` 태그면 Release 첨부.
- exe로 돌 때 설정은 exe 옆 `config/`(없으면 묶인 기본값), 데이터는 `%LOCALAPPDATA%\Jonnyang`. 경로 계산은 `core/config.py`에서만 한다.
- kiwi 모델 경로는 `kiwipiepy_model.get_model_path()`로 직접 넘긴다. 새 의존성을 넣으면 exe에서도 되는지 `--selftest`로 확인한다.
- YAML 키에 `yes`/`no`/`on`/`off`를 그대로 쓰지 않는다(불리언이 됨). `tests/test_persona.py`가 검사한다.

## 캐릭터
- 말투/템플릿은 `config/persona.yaml`에서 관리한다 (코드에 하드코딩 금지).
- 숫자, 경로, 시간, 오류 원인 같은 핵심 정보는 말투 때문에 가려지거나 바뀌면 안 된다.
- 자동 어미 변환 대신 템플릿 방식을 쓴다 (한국어 어미 자동 치환은 어색해지기 쉽다).

## 작업 방식
- 새 기능은 반드시 명령 예시 테스트부터 추가한다 (정상 표현, 오타, 어미 변형, 부정문).
- 매칭 점수가 임계값 미만이면 실행하지 말고 되묻는다.
- 부정 표현("하지 마", "-지 말아줘", "안 해도 돼")이 문장의 마지막 서술어에 걸리면 실행하지 않는다.
- "X 말고 Y"는 부정이 아니라 제외다. X를 후보에서 빼고 Y로 진행하고, Y가 없으면 되묻는다.
