# 존냥이 (Jonnyang) =^.^=

Windows 10/11용 규칙 기반 한국어 개인 비서. 고양이 캐릭터. LLM/AI API 없이 키워드·형태소·유사도 규칙으로만 명령을 알아듣는다.

바탕화면 구석에 떠 있는 데스크톱 펫이다. 말풍선에 지금 하는 일(타이머 남은 시간, 다음 알람, 대답 기다리는 중)이 보이고, 고양이 밑 입력창에 말을 걸면 된다.

| 응답 | 작업 중 | 확인 필요 | 알림 |
|---|---|---|---|
| ![](docs/images/pet-reply.png) | ![](docs/images/pet-working.png) | ![](docs/images/pet-confirm.png) | ![](docs/images/pet-alert.png) |

표정: ![](docs/images/pet-poses.png)

## 설치 (Windows)

1. **64비트 Python 3.12 또는 3.13** 설치 (pycaw는 3.10 이상 필요, kiwipiepy Windows 휠은 x86-64용만 있음).
   - `python`을 치면 Microsoft Store가 뜨면: 설정 → 앱 → 앱 실행 별칭에서 python 끄거나 `py -3.12` 사용.
2. **프로젝트 폴더(`pyproject.toml`이 있는 곳)에서** 가상환경 만들고 설치:
   ```powershell
   cd C:\경로\Jonnyang_agent
   py -3.12 -m venv .venv
   Test-Path .\.venv\Scripts\python.exe    # True가 나와야 다음 단계로
   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
   ```
   - kiwipiepy 모델(약 105MB)이 같이 받아진다. 느려도 정상이다.
   - 활성화(`Activate.ps1`) 없이 `.\.venv\Scripts\python.exe`를 직접 쓰면 실행 정책 문제도 피한다.
3. 실행:
   ```powershell
   .\.venv\Scripts\jonnyang-pet.exe              # 데스크톱 펫 (콘솔 창 없이)
   .\.venv\Scripts\python.exe -m jonnyang         # 같은 펫, 오류가 콘솔에 보임 (문제 생기면 이걸로)
   .\.venv\Scripts\python.exe -m jonnyang --cli   # 예전 콘솔 채팅
   ```
   - 바로가기를 만들려면 `jonnyang-pet.exe`를 우클릭 → 바로 가기 만들기. 시작프로그램 폴더(`Win+R` → `shell:startup`)에 넣으면 부팅 때 같이 뜬다.
   - 콘솔 모드에서 이모지가 네모로 나오면 Windows Terminal을 쓰거나 "이모지 꺼"라고 말하면 된다. 콘솔 디버그: `/nlu 문장`, `/time 문장`.

### 펫 다루기

| 동작 | 결과 |
|---|---|
| 입력창에 쓰고 Enter | 명령 실행. ↑/↓로 이전 입력 |
| 고양이 끌기 | 위치 이동 (다음 실행 때 기억) |
| 고양이 클릭 | 쓰다듬기. 알림 말풍선이 떠 있으면 확인 처리 |
| 고양이 더블클릭 | 입력창 숨기기 / 보이기 |
| 고양이 우클릭 | 메뉴: 입력창, 도움말, 냥체·이모지 켜고 끄기, 숨기기, 종료 |
| 트레이 아이콘 클릭 | 숨긴 존냥이 다시 보이기 |
| 말풍선의 응/아니·번호 버튼 | 확인·되묻기에 바로 대답 |

- 말풍선 상태(Codex 펫처럼): 🔵 작업 중 / 🟠 대답 기다리는 중 / 🟢 완료 / 🔴 문제 생김 / 🟧 알림.
- 응답은 몇 초 뒤 사라지고 진행 중인 일이 있으면 그걸 보여준다. 할 일이 없으면 말풍선이 숨고, 고양이에 마우스를 올리면 다시 뜬다.
- 확인 질문과 알림(타이머 끝 등)은 대답하거나 클릭할 때까지 남는다. 창을 숨겨둔 상태면 트레이 알림도 뜬다.
- 10분 동안 아무것도 안 하면 존다(zZ). 클릭하거나 말을 걸면 깬다.
- 한 번에 하나만 실행된다(리마인더가 두 번 울리지 않게). 이미 떠 있으면 안내만 뜬다.

### 설치가 안 될 때

| 증상 | 원인 / 해결 |
|---|---|
| `'.venv' 모듈을 로드할 수 없습니다` (CouldNotAutoLoadModule) | `.venv\Scripts\python.exe` 파일이 없어서 PowerShell이 `.venv`를 모듈 이름으로 읽은 것. 가상환경이 안 만들어졌거나 다른 폴더에 있다. `Test-Path .\.venv\Scripts\python.exe`로 확인하고, False면 2단계 `py -3.12 -m venv .venv`부터 다시. |
| `py`를 찾을 수 없음 | python.org 설치 프로그램으로 다시 설치하면서 "py launcher" 체크. 또는 `python -m venv .venv` (단 `python --version`이 3.10 이상 64비트여야 함). |
| `No suitable Python runtime found` | `py --list`로 설치된 버전 확인. 3.12가 없으면 있는 버전(3.10 이상)으로 `py -3.13 -m venv .venv`처럼 바꾼다. |
| `python`이 Microsoft Store를 염 | 설정 → 앱 → 고급 앱 설정 → 앱 실행 별칭에서 python 끄기. |

WSL에서는 볼륨 조절(pycaw)이 안 된다. 개발은 아무 OS에서 해도 되고, 테스트는 가짜 OS 어댑터로 돈다.

## 할 수 있는 것 (1단계, 오프라인)

| 분류 | 예시 |
|---|---|
| 타이머 | "3분 타이머", "라면 타이머 4분", "타이머 얼마나 남았어", "2번 타이머 취소", "타이머 전부 꺼" |
| 알람 | "내일 아침 7시 알람", "30분 뒤에 깨워줘", "알람 다 꺼줘" |
| 리마인더 | "내일 오후 3시에 병원 가라고 알려줘", "금요일에 보고서 제출 리마인더", "리마인더 뭐 있어" |
| 목록 | "쇼핑 목록에 우유랑 계란 추가해", "할 일 목록 보여줘", "쇼핑 목록에서 우유 빼줘" |
| 계산 | "40의 15%", "3만 2천원 4명이서 나눠", "5만원에서 20% 할인", "12 곱하기 7" |
| 단위 | "5평은 몇 제곱미터", "10마일을 킬로미터로", "화씨 100도는 섭씨로" |
| 볼륨 | "볼륨 올려", "소리 20 줄여", "볼륨 50으로", "음소거", "음소거 해제" |
| 앱/폴더 | "메모장 켜줘", "다운로드 폴더 열어", "메모장을 노트라고 불러" |
| 시스템 | "CPU 얼마나 써", "메모리 사용량", "디스크 용량", "배터리 얼마나 남았어" |
| 기타 | "뭐 할 수 있어?", "되돌려줘", "냥체 꺼", "이모지 꺼", "말투 시크하게", "호출어 켜" |

- 부정문은 실행 안 함: "볼륨 올리지 마", "알람 안 맞춰도 돼"
- "X 말고 Y"는 Y를 실행: "타이머 말고 내일 7시 알람", "끄지 말고 소리 줄여줘"
- 지우기·비우기·덮어쓰기·되돌리기는 대상 목록을 보여주고 "응/아니"로 확인받는다.
- 점수가 애매하면 실행하지 않고 되묻는다("타이머" → "1. 타이머 맞추기 2. 남은 시간 보기").

## 고치고 싶을 때

| 파일 | 내용 |
|---|---|
| `config/persona.yaml` | 모든 대사. 프로필(soft 순한 냥체 / chic 시크 / dc 디시 / plain 냥체 끔), 고양이·말풍선 색(`appearance`), 응답별 표정(`poses`), 펫 문구(`ui`) |
| `config/aliases.yaml` | 앱·폴더 별칭 (실행 파일, 전체 경로, `ms-settings:` 같은 URI) |
| `config/lexicon.yaml` | 동의어 묶음(켜/틀/실행 → OPEN 등), 형태소 분석기 사용자 단어 |
| `config/settings.yaml` | 호출어 필수 여부, 매칭 임계값, 확인 대기 시간, 리마인더 기본 시각 |

프로그램은 `config/`를 읽기만 한다. 명령으로 바꾼 설정·별칭·목록·리마인더는 `data/jonnyang.db`(SQLite)에 저장된다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest            # 전체 (Windows 전용 3개는 다른 OS에서 skip)
.\.venv\Scripts\python.exe -m pytest -m windows # 실제 볼륨 읽기·시스템 정보·한글 경로 kiwi 로딩 (읽기만 함)
.\.venv\Scripts\python.exe tools\eval_nlu.py --sweep   # 의도 정확도 리포트 + 임계값 스윕
.\.venv\Scripts\python.exe tools\render_pet.py docs\images   # 펫 화면 스크린샷 다시 뽑기
```

GUI 테스트(`tests/test_gui.py`)는 화면 없이(`QT_QPA_PLATFORM=offscreen`) 돈다.

새 기능은 `tests/data/intents/*.yaml`에 명령 예시(정상, 오타, 어미 변형, 부정문)부터 추가한다. 실사용에서 잘못 알아들은 문장도 여기에 넣는다.

## 한계 (1단계)

- 리마인더·알람은 프로그램이 켜져 있을 때만 울린다. 꺼져 있던 동안 지난 것은 다음 실행 때 "놓친 알림"으로 알려준다.
- 반복 알림("매일", "평일마다"), 시간 범위("3시부터 5시"), 공휴일·음력, "이따가" 같은 모호한 시간은 안 된다(안내 메시지만 냄).
- 붙여 쓴 한 글자 한자어 수사는 숫자로 안 바꾼다: "오 분"은 되고 "오분"은 안 된다("구분", "엔진 오일" 오인 방지).
- 날씨·환율·위키·뉴스는 2단계(`skills/online/`).
- 펫을 부르는 전역 단축키는 아직 없다(입력창을 클릭해야 한다).
