# 존냥이 1단계(오프라인 코어) 구현 계획

> 상태: **1단계 구현 완료** (2026-10-20), **2단계 구현 완료** (2026-10-25). 맨 아래 "승인된 결정", "구현 결과", "2단계" 참고.
> 아래 표의 사실은 실제 패키지 설치/소스 확인 또는 공식 문서로 확인한 내용이다.

---

## 0. 미리 검증한 사실 (계획의 근거)

scratch venv(Linux, Python 3.13)에 `kiwipiepy 0.24.0`, `rapidfuzz 3.14.6`을 설치해 실제 명령문을 돌려봤고, `pycaw`/`comtypes`는 wheel 소스를 직접 열어 확인했다.

| 항목 | 확인 결과 | 계획에 미치는 영향 |
|---|---|---|
| kiwipiepy 모델 | `pip install kiwipiepy`가 `kiwipiepy_model`(약 105MB)을 의존성으로 같이 설치 | 별도 모델 다운로드 단계 불필요 |
| kiwipiepy 로딩 | `Kiwi()` 생성에 약 3초 | 시작 시 1회만 로드, 로딩 메시지 출력. 테스트는 session fixture로 공유 |
| `"존냥아 타이머 3분 맞춰줘"` | `존냥아/NNP` 한 덩어리로 나옴 | 호출어는 **형태소 분석 전에 정규식으로 제거** |
| `"40의 15%는?"` | `15/SN %/SW 늘/VV ᆫ/ETM` 으로 **오분석** | 숫자·수식·퍼센트는 **원문에서 정규식으로 먼저 추출**, kiwi에 맡기지 않음 |
| `"존냥이 냥체 꺼"` | `냥/NNB 체/NNG` 로 쪼개짐 | 도메인 어휘(존냥, 냥체, 이모지 등)는 `add_user_word`로 등록. 등록 후 `존냥/NNP 아/JKV`로 정상 분리 확인 |
| `"볼륨 올리지 마"` | `올리/VV 지/EC 말/VX 어/EF` | 부정 = `-지(EC) + 말(VX)` 패턴으로 탐지 가능 |
| `"타이머 말고 알람 맞춰"` | `타이머/NNP 말/VV 고/EC 알람/NNG 맞추/VV` | "X 말고 Y"는 **부정이 아니라 대체**. 아래 1-③ 참고 |
| `"타이멀 3분"` | kiwi가 `타이머 + ᆯ/JKO`로 알아서 복원 | 흔한 받침 오타는 kiwi 단계에서 일부 흡수됨 |
| rapidfuzz + 자모 분해 | `ratio("볼룸","볼륨")` 50 → NFD 자모 분해 후 83.3, `"메모쟝"/"메모장"` 66.7 → 85.7 | 퍼지 매칭은 **`unicodedata.normalize("NFD")`로 자모 분해 후** 비교 (추가 라이브러리 불필요) |
| rapidfuzz 3.x | 기본 전처리 없음(소문자화 X). `extractOne` → `(choice, score, index)` | 영문 앱 이름은 `processor=utils.default_process` 명시 |
| pycaw 버전별 API | 20240210: `GetSpeakers()`가 raw `IMMDevice` 반환. 20251023: `AudioDevice` 래퍼 + `.EndpointVolume`. 20260927(최신): 여기에 `.volume_percent`(0~100 setter)까지 추가 | 인터넷 블로그의 `devices.Activate(IAudioEndpointVolume._iid_, ...)` + `cast` 예제는 **구버전(20240210 이하) 방식**이라 최신에서 안 맞음 → 버전 고정 |
| pycaw 요구사항 | `Requires-Python >=3.10`, `comtypes>=1.4.8` | Python 3.10 이상 필수 |
| comtypes | import 시점에 **import한 스레드에서만** `CoInitializeEx()` 호출 | 볼륨 조작은 메인 스레드에서만, 다른 스레드면 `comtypes.CoInitialize()` 필요 |
| psutil | `cpu_percent(interval=None)` 첫 호출은 의미 없는 0.0, `sensors_battery()`는 배터리 없으면 `None` | 시작 시 cpu_percent 1회 예열, 데스크톱은 "배터리 없음" 응답 |
| Send2Trash 2.1.0 | 리스트 입력 지원, 실패 시 `OSError` | 2단계(files)에서 사용 |

---

## 1. 모듈 구조 검토와 수정 제안

### 기존 구조에서 문제 되는 부분

1. **스케줄러가 없음.** 타이머·알람·리마인더가 각자 스레드를 돌리면 꼬인다. 게다가 콘솔 `input()`이 블로킹이라 백그라운드에서 울리는 알림이 입력 줄과 섞인다. → `core/scheduler.py`(단일 스레드 + heapq)와 `core/console.py`(출력 락, 프롬프트 다시 그리기)를 추가.
2. **`aliases.yaml`을 "편집용"과 "별칭 등록 명령"이 동시에 쓴다.** 프로그램이 YAML을 다시 쓰면 사용자가 단 주석이 날아간다. → `config/aliases.yaml`은 사람이 편집하는 기본값(읽기 전용), 명령으로 등록한 별칭은 `data/`(SQLite)에 저장하고 로드할 때 합친다(사용자 등록이 우선).
3. **`skills/system.py`가 볼륨, 앱 실행, 시스템 상태를 한 파일에 몰아넣음 + Windows API를 직접 호출.** 그러면 Linux CI나 테스트에서 import부터 터진다. → 스킬은 `volume.py / apps.py / sysinfo.py`로 나누고, OS 호출은 `platform/` 어댑터 뒤로 숨긴다(`windows.py` 실제 구현, `fake.py` 테스트용).
4. **NLU 파이프라인에 전처리·부정 처리 자리가 없음.** 위 검증대로 호출어 제거, 원문 정규식 슬롯 추출이 형태소 분석보다 **먼저** 돌아야 한다. → `nlu/preprocess.py`, `nlu/negation.py`, `nlu/numbers.py`(한글 수사) 추가.
5. **도움말/되돌리기/별칭 등록/말투 설정을 담당할 스킬이 없음.** → `skills/meta.py`.
6. **되묻기·확인 대기 상태 관리가 dispatcher에 섞여 있음.** "응/아니" 답을 기다리는 동안 들어온 입력을 어떻게 처리할지 명시해야 한다. → `core/dialog.py`(대기 상태 머신)로 분리.
7. **저장소 형식이 "JSON/SQLite"로 미정.** → 표준 라이브러리 `sqlite3` 하나로 통일(목록, 리마인더, 알람, 별칭, history, 말투 설정). 원자적 쓰기, 동시 접근 걱정 없음. `data/`는 `.gitignore`, 경로는 환경변수 `JONNYANG_DATA_DIR`로 바꿀 수 있게 해서 테스트에서 tmp 사용.
8. **CLAUDE.md "말고 감지 시 실행 안 함" 규칙이 실제 한국어와 충돌.** "타이머 말고 알람 맞춰"는 알람을 맞추라는 뜻이다. → 규칙을 아래처럼 고치자고 제안:
   - `-지 마`, `-지 말아`, `안/못 + 동사`, `하지 마` → **부정: 실행하지 않음**
   - `X 말고 (Y)` → **제외: X를 후보에서 빼고 Y로 진행**, Y가 없으면 되묻기

### 수정 제안 구조

```
jonnyang/
├── CLAUDE.md
├── pyproject.toml
├── data/                       # .gitignore. jonnyang.db (SQLite)
├── config/
│   ├── persona.yaml            # 말투 프로필·템플릿
│   ├── aliases.yaml            # 기본 앱/폴더 별칭 (사람이 편집, 프로그램은 읽기만)
│   └── lexicon.yaml            # 동의어 사전(켜/틀/실행/열 → OPEN 등), 사용자 단어
├── src/jonnyang/
│   ├── __main__.py             # python -m jonnyang
│   ├── main.py                 # 입력 루프
│   ├── nlu/
│   │   ├── preprocess.py       # NFKC, 호출어 제거, 공백 정리
│   │   ├── numbers.py          # 한글 수사(삼십, 스물, 3만 2천) → 숫자
│   │   ├── slots.py            # 원문 정규식 슬롯: 숫자/퍼센트/수식/따옴표/경로
│   │   ├── timeparse.py        # 한국어 시간 표현 파서 (now 주입 가능)
│   │   ├── normalize.py        # kiwipiepy → 어근 리스트
│   │   ├── negation.py         # 부정/제외 탐지
│   │   └── matcher.py          # 키워드 점수 + 자모 퍼지 보정
│   ├── skills/
│   │   ├── base.py             # Skill, Intent, Result(data, undo, confirm 필요 여부)
│   │   ├── timer.py, reminder.py, lists.py
│   │   ├── calc.py, units.py
│   │   ├── volume.py, apps.py, sysinfo.py
│   │   ├── meta.py             # 도움말, undo, 별칭 등록, 말투 설정
│   │   ├── files.py            # (2단계)
│   │   └── online/             # (2단계)
│   ├── platform/
│   │   ├── base.py             # VolumeCtl, Launcher, SysInfo 프로토콜
│   │   ├── windows.py          # pycaw, os.startfile, psutil, winsound
│   │   └── fake.py             # 테스트용 가짜 구현
│   ├── persona/cat.py          # Result → 템플릿 렌더링 (캐릭터는 여기만)
│   └── core/
│       ├── config.py           # YAML 로드 (encoding="utf-8" 강제)
│       ├── storage.py          # sqlite3 래퍼, 스키마 마이그레이션
│       ├── scheduler.py        # 단일 스레드 heapq 스케줄러
│       ├── console.py          # 출력 락, 알림 출력 후 프롬프트 재표시
│       ├── dialog.py           # 되묻기/확인 대기 상태
│       ├── dispatcher.py       # intent → skill, 임계값, 확인, undo 기록
│       ├── history.py          # 실행 기록, 되돌리기 로그
│       └── network.py          # (2단계)
├── tools/eval_nlu.py           # 데이터셋 정확도 리포트, 임계값 스윕
└── tests/
    ├── data/intents/*.yaml     # 명령 예시 데이터셋 (핵심)
    ├── data/time_cases.yaml
    ├── test_intents.py, test_timeparse.py, test_persona.py ...
    └── conftest.py             # kiwi session fixture, fake platform, tmp DB
```

---

## 2. 의도 매칭 알고리즘

```
입력 ─▶ ① 전처리 ─▶ ② 원문 슬롯 추출 ─▶ ③ 형태소 정규화 ─▶ ④ 부정/제외 탐지
     ─▶ ⑤ 키워드 점수 ─▶ ⑥ 퍼지 보정 ─▶ ⑦ 슬롯 적합도 ─▶ ⑧ 임계값 판정
```

**① 전처리** – `unicodedata.normalize("NFKC")`, 앞뒤 공백·문장부호 정리. 호출어 정규식 `^\s*존냥(아|이|님)?[\s,!~]*`. 호출어 필수 여부는 설정 옵션(기본: 선택).

**② 원문 슬롯 추출(형태소 분석 전)** – 정규식으로 span과 값을 뽑는다.
- 시간/기간: `timeparse` 호출 (3장)
- 숫자: 아라비아 숫자, 한글 수사(`삼십`, `스물다섯`, `세`), 단위 조합(`3만 2천`)
- 수식/퍼센트: `40의 15%`, `3+4*2`, `1/3`
- 따옴표 문자열: 목록 항목·리마인더 내용 보존용 (`"우유" 추가해`)
- 추출한 span은 ③에서 형태소 매칭 대상에서 빼서 숫자가 키워드로 오인되지 않게 한다.

**③ 형태소 정규화** – `kiwi.tokenize()` 결과에서
- 남김: 체언(NNG/NNP/NNB/NR), 용언 어근(VV/VA/VX, `XSV` 앞 명사는 `추가하다`처럼 결합), XR, SL(영문), 일부 부사(MAG: 다/전부/좀/더/조금)
- 버림: 조사(J*), 어미(E*), 기호
- `lexicon.yaml` 동의어로 대표형 치환: `켜/틀/실행/열 → OPEN`, `끄/닫/종료 → CLOSE`, `올리/키우/높이 → UP` 등
- 시작 시 `add_user_word`로 도메인 어휘 등록(존냥, 냥체, 이모지, 앱 별칭명)

**④ 부정/제외 탐지** (`negation.py`)
- 부정: `지/EC + 말/VX`, `안/MAG|못/MAG + 용언`, `하/VV + 지/EC + 말/VX` → 결과 `NEGATED` → 실행 안 하고 "알았다냥, 안 할게" 류 응답
- 제외: `명사 + 말/VV + 고/EC` → 해당 명사를 키워드 후보에서 제거 후 계속 진행

**⑤ 키워드 점수** – 각 intent가 선언하는 규칙:
```python
Intent(
  name="timer.set",
  nouns={"타이머": 1.0, "알람": 0.3},     # 핵심 명사 (가중치)
  verbs={"SET": 0.6, "OPEN": 0.3},        # 대표형 동사
  required_slots=["duration"],            # 없으면 되묻기
  optional_slots=[],
  negative_nouns={"취소", "삭제"},          # 있으면 감점 (timer.cancel과 구분)
)
```
점수 = (명사 적중 가중치 합 + 동사 적중 가중치 합 + 슬롯 보너스 − 감점) / 해당 intent 최대 점수 → 0~1 정규화.

**⑥ 퍼지 보정** – ⑤에서 안 맞은 토큰만 대상. 키워드 사전 전체를 NFD 자모 분해해서 `rapidfuzz.process.extractOne(token, vocab, scorer=fuzz.ratio, score_cutoff=80)`. 적중하면 `가중치 × score/100`만 반영(정확 적중보다 항상 낮게). 앱 별칭 매칭도 같은 방식.

**⑦ 슬롯 적합도** – 필수 슬롯이 있으면 +보너스, 없으면 실행 대신 해당 슬롯만 되묻기("몇 분짜리 타이머냥?").

**⑧ 임계값 판정** (초기값, `tools/eval_nlu.py`로 튜닝)
| 조건 | 동작 |
|---|---|
| 1위 ≥ 0.70 이고 (1위 − 2위) ≥ 0.15 | 실행 (파괴적 작업이면 확인 먼저) |
| 1위 ≥ 0.40 이지만 위 조건 불만족 | 되묻기: 상위 2개 제시 ("타이머 맞출까, 알람 맞출까냥?") |
| 1위 < 0.40 | 이해 못함 + 예시 3개 |

**대화 상태(`dialog.py`)** – 되묻기/확인 대기 중 입력은 먼저 "응/어/ㅇㅇ/그래/1번" 또는 "아니/ㄴㄴ/취소"로 해석하고, 둘 다 아니면 대기를 취소한 뒤 새 명령으로 처리한다. 대기는 60초 지나면 만료.

---

## 3. 한국어 시간 표현 파서

순수 함수 `parse(text, now) -> list[TimeMatch]`. `TimeMatch = {span, kind(duration|datetime), value, assumed: list[str]}`. `assumed`는 "오전/오후 추정" 같은 가정 목록이라 persona가 **해석 결과를 절대시각으로 되읽어 준다**: `"내일 3시" → "10/21(수) 오후 3:00으로 맞췄다냥 (오후로 추정)"`. 시간대는 시스템 로컬 시간, 표준 라이브러리 `datetime`만 사용.

### 지원 범위
| 분류 | 예시 |
|---|---|
| 상대 기간 | `10초/5분/2시간/3일/1주 뒤·후·있다가`, `1시간 30분 뒤`, `한 시간 반`, `반 시간`, `삼십 분`, `스무 분` |
| 날짜 상대어 | `오늘, 내일, 모레, 글피, 어제(조회용)` |
| 하루 중 구간 | `오전/오후/아침/점심/저녁/밤/새벽/낮`, `정오`, `자정` |
| 시각 | `3시`, `3시 반`, `3시 15분`, `15:30`, `세 시` |
| 요일 | `화요일`, `이번주 금요일`, `다음주 화요일`, `다다음주 월요일`, `주말` |
| 날짜 | `10월 25일`, `25일`, `다음달 5일` |

### 해석 규칙 (애매한 경우)
- **오전/오후 미지정 `3시`**: 지금 이후 가장 가까운 3:00 또는 15:00. 단 `아침/새벽`이면 오전, `저녁/밤`이면 오후(`밤 12시` = 자정).
- **이미 지난 시각**: 날짜 미지정이면 다음 날로 넘김. `오늘`을 명시했는데 지났으면 되묻기.
- **요일만 `화요일`**: 오늘 이후 다음 화요일(오늘이 화요일이고 시각이 지났으면 다음 주).
- **`이번주/다음주`**: 월요일 시작 달력 주 기준. 오늘(2026-10-20, 화) 기준 `다음주 화요일` = 10/27. `이번주 월요일`처럼 이미 지난 날은 되묻기.
- **`25일`**: 이번 달 25일이 지났으면 다음 달.
- 날짜만 있고 시각이 없는 리마인더: 기본 시각(설정값, 기본 오전 9시) + `assumed`에 표시.

### 지원 안 함 (1단계 한계, 명확히 거절하거나 되묻기)
- 반복(`매일`, `평일마다`, `매주 월요일`) → 2단계
- 범위(`3시부터 5시까지`), 음력, 명절·공휴일 이름(`추석`), `월말`, `이따가/조만간/나중에` 같은 모호어 → "정확한 시간을 말해달라냥"
- 한 문장 안에 시각이 2개 이상 → 되묻기
- 시간대 변환, 과거 시각 예약

---

## 4. 테스트 전략

### 데이터셋 포맷 (`tests/data/intents/timer.yaml` 예)
```yaml
# now: 테스트 기준 시각 (전 파일 공통 기본값 2026-10-20T14:00 화요일)
- text: "존냥아 3분 타이머 맞춰줘"
  intent: timer.set
  slots: {duration_sec: 180}
  tags: [정상, 호출어]
- text: "타이멀 3분"
  intent: timer.set
  slots: {duration_sec: 180}
  tags: [오타]
- text: "삼 분 타이머 좀 맞춰 줄래?"
  intent: timer.set
  tags: [어미변형, 한글수사]
- text: "타이머 맞추지 마"
  expect: negated
  tags: [부정]
- text: "타이머 말고 내일 7시 알람"
  intent: alarm.set
  slots: {at: "2026-10-21T07:00"}
  tags: [제외]
- text: "타이머"
  expect: clarify            # 필수 슬롯(duration) 없음
  tags: [슬롯누락]
- text: "배고프다"
  expect: fallback
  tags: [무관]
```
- `expect` 기본값은 `execute`. `slots`는 부분 일치(명시한 키만 비교).
- 기능마다 최소: 정상 5, 오타 2, 어미 변형 3, 부정 2, 제외 1, 무관 1.

### 테스트 종류
1. **intent 데이터셋 테스트** – YAML 전체를 `pytest.mark.parametrize`로 로드. kiwi는 session fixture로 1회만 생성.
2. **timeparse 단위 테스트** – `time_cases.yaml`, `now`를 고정(2026-10-20 14:00 화 + 경계값: 23:59, 일요일, 월말, 연말).
3. **스킬 단위 테스트** – `platform/fake.py` 주입, DB는 `tmp_path`. 실제 볼륨/앱 실행은 하지 않음.
4. **persona 테스트** – 모든 프로필 × 모든 템플릿 키에 대해 "Result 데이터의 숫자·시각·경로 문자열이 렌더링 결과에 그대로 들어있는지" 검사. 템플릿 placeholder 누락도 여기서 잡음.
5. **대화 흐름 테스트** – dispatcher에 입력 시퀀스를 넣고 출력 확인 (`"타이머 전부 지워" → 확인 → "응" → 삭제됨`).
6. **Windows 스모크 테스트** – `@pytest.mark.windows`, Windows에서만 실행(볼륨 읽기만, 앱 실행 없음).
7. **정확도 리포트** – `python tools/eval_nlu.py`: 태그별 정확도, 혼동 쌍 top-N, 임계값 스윕. 잘못 알아들은 실사용 문장은 무조건 데이터셋에 추가(회귀 방지).

---

## 5. 구현 순서 (각 단계 끝 = 동작 확인 방법)

| # | 단계 | 확인 방법 |
|---|---|---|
| 1 | 스캐폴딩: pyproject(src 레이아웃), pytest, ruff, `python -m jonnyang` 에코 루프, `.gitignore` | `pytest` 통과, Windows에서 실행 시 배너 `=^.^=` 출력, 한글 입력 에코 |
| 2 | `core/config.py` + `persona/cat.py` + `persona.yaml`(기본 순한 냥체) | `안녕` → 인사 템플릿, persona 테스트 통과 |
| 3 | NLU 기초: preprocess, numbers, slots, normalize(kiwi + 사용자 단어), negation | 디버그 명령 `/nlu 문장` → 토큰·슬롯·부정 여부 출력 |
| 4 | matcher + dispatcher + dialog, 더미 intent(도움말, 인사) | 데이터셋 테스트 하네스 동작, `eval_nlu.py` 리포트 출력 |
| 5 | timeparse (가장 큰 단계, 테스트 먼저 대량 작성) | `time_cases.yaml` 전부 통과, `/time 다음주 화요일 3시` 디버그 출력 |
| 6 | scheduler + console + 타이머/알람 (설정·조회·취소·전체 삭제 확인) | `10초 타이머` → 입력 중에도 "삐용!" 출력 후 프롬프트 복구, `winsound` 비프 |
| 7 | storage(SQLite) + 목록 + 리마인더 (재시작 후 유지, 꺼져 있는 동안 놓친 것 알림) | 종료 후 재실행해도 목록·리마인더 남아있음 |
| 8 | 계산(ast 기반 안전 평가, `eval` 금지) + 단위 변환(자체 테이블, 온도는 오프셋 처리) | `40의 15%` → 6, `3만 2천원 4명이서 나눠` → 8,000원, `5평은 몇 제곱미터` |
| 9 | history/undo + 별칭 등록 | 목록 항목 삭제 → `되돌려` → 복구 |
| 10 | Windows 어댑터: 볼륨/음소거, 앱 실행(별칭 사전 + 퍼지), 시스템 상태 | 수동 체크리스트(볼륨 50%, 음소거 토글, 메모장 실행, CPU/메모리/디스크/배터리) |
| 11 | 말투 설정 명령(냥체 끄기, 이모지 끄기, 말투 순하게) + 호출어 옵션 | 설정 바꾸고 재시작해도 유지, 핵심 정보 그대로 |
| 12 | 임계값 튜닝, 데이터셋 보강 | 목표: 데이터셋 정확도 95%+, 부정문 오실행 0건 |

**undo 범위(1단계)**: 목록 추가/삭제, 리마인더·알람 생성/삭제, 별칭 등록, 볼륨 변경(이전 값 복원). 앱 실행과 타이머 만료는 되돌릴 수 없음을 안내.

**확인 필요 작업(1단계)**: 타이머/알람 전체 삭제, 목록 비우기, 리마인더 삭제. 확인 문구에는 대상 목록을 반드시 표시.

**앱 실행 보안**: 사용자 문장에서 명령어를 조립하지 않는다. 실행 대상은 별칭 사전(`aliases.yaml` + 등록 별칭)에 있는 경로·URI만. 실행은 `os.startfile()`(경로, `ms-settings:` 같은 URI) 또는 `subprocess.Popen([...], shell=False)`.

---

## 6. Windows 설치 시 막힐 만한 부분

1. **Python 버전/비트**: pycaw가 `>=3.10`을 요구하고, kiwipiepy는 Windows용으로 x86-64 abi3 wheel(cp39+)만 올라와 있다. → **64비트 Python 3.12 또는 3.13** 권장. 32비트 Python이나 Windows ARM64용 Python은 wheel이 없어서 CMake + C++17 컴파일러로 소스 빌드를 해야 한다(README 기준 `cmake<4` 권장).
2. **kiwipiepy + 한글 사용자명 경로**: Kiwi 엔진 v0.23.2 릴리스 노트에 "Windows에서 모델 파일 경로에 유니코드 문자가 있으면 로딩 실패하던 버그 수정"이 있다. 사용자 폴더명이 한글이면 이 버그에 해당했다. → `kiwipiepy>=0.24.0`으로 고정하고, 1단계 3번 작업 때 한글 경로에서 실제로 로드되는지 확인한다. 그래도 실패하면 모델을 `C:\kiwi_model`처럼 영문 경로에 두고 `Kiwi(model_path=...)`로 지정.
3. **kiwipiepy 용량·로딩**: 모델 패키지만 약 105MB, 로딩 약 3초(검증 환경 기준). 설치가 느려도 정상.
4. **pycaw API 변경**: 20251023부터 `GetSpeakers()`가 래퍼 객체를 돌려줘서 구버전 예제(`Activate` + `cast(POINTER(IAudioEndpointVolume))`)가 그대로 안 돌아간다. `volume_percent`는 최신(20260927)에만 있다. → `pycaw>=20251023`으로 두고 `device.EndpointVolume.GetMasterVolumeLevelScalar()` / `SetMasterVolumeLevelScalar(x, None)` / `GetMute()` / `SetMute(b, None)`만 쓴다(두 버전 공통).
5. **COM 스레드**: comtypes는 import한 스레드에서만 COM을 초기화한다. 타이머 스레드에서 볼륨을 만지면 오류 → 볼륨 조작은 메인 스레드에서만.
6. **pycaw README의 `visualcpp-build-tools` 안내**: pycaw/comtypes는 순수 파이썬이라 보통 필요 없다. 아주 최신 Python이라 psutil 등에 wheel이 없을 때만 Build Tools가 필요하다.
7. **인코딩**: Windows 기본 로케일(cp949) 때문에 `open()`에 인코딩을 안 주면 YAML의 한글이 깨지거나 예외가 난다. → 모든 파일 I/O에 `encoding="utf-8"` 명시, 실행 시 `PYTHONUTF8=1` 권장.
8. **콘솔**: 구형 conhost(cmd)는 이모지가 네모로 나온다. → Windows Terminal 권장, 이모지 옵션 끄기 제공.
9. **PowerShell 실행 정책**: `.venv\Scripts\Activate.ps1`이 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, 또는 활성화 없이 `.venv\Scripts\python.exe -m jonnyang`.
10. **`python` 명령이 Microsoft Store를 여는 문제**: 설정 → 앱 실행 별칭에서 python 별칭을 끄거나 `py -3.12` 런처 사용.
11. **WSL 금지**: pycaw는 Windows COM이 필요해서 WSL에서 안 된다(CLAUDE.md 규칙). 개발은 WSL에서 해도 테스트는 fake 어댑터로 돌고, 실제 실행은 Windows Python에서.

### 의존성 초안
```toml
[project]
requires-python = ">=3.10"
dependencies = [
  "kiwipiepy>=0.24.0",
  "rapidfuzz>=3.14",
  "psutil>=7.0",
  "pyyaml>=6.0",
  "pycaw>=20251023; sys_platform == 'win32'",
]
[project.optional-dependencies]
dev = ["pytest", "ruff"]
# 2단계: send2trash, feedparser
```
표준 라이브러리로 처리: `sqlite3`, `ast`(계산), `decimal`(금액), `winsound`(Windows 비프), `threading`/`heapq`(스케줄러), `unicodedata`(자모 분해).

---

## 승인된 결정 (2026-10-20, 4개 모두 제안대로)
1. "말고"는 제외 후 진행, 마지막 서술어에 걸린 "-지 마/안 ~"만 부정 → CLAUDE.md 반영
2. 명령으로 등록한 별칭은 SQLite, `config/aliases.yaml`은 읽기 전용
3. 저장소는 SQLite 하나 (`data/jonnyang.db`)
4. 리마인더·알람은 프로그램이 켜져 있을 때만, 놓친 것은 다음 시작 때 알림

## 구현 결과
- 1~11단계 구현. 12단계(튜닝)는 아래 측정까지 진행.
- 테스트 424개 통과 (+ Windows 전용 3개는 Linux에서 skip): 의도 데이터셋 245문장, 시간 파서 63케이스, 숫자 정규화, 대화 흐름(확인/되묻기/슬롯/undo/호출어), 스킬 단위, persona 무결성.
- 처음 보는 문장으로 측정(held-out): 1차 46문장 43개(93%) → 원인 고친 뒤 46/46. 2차 35문장 34개(97%), 실행되면 안 되는 문장 10개 중 오실행 0. 두 묶음 모두 이후 회귀 테스트로 편입(`tests/data/intents/heldout.yaml`).
- 계획에서 바뀐 점
  - 형태소 분석이 오타 단어를 엉뚱하게 쪼개는 경우("배터랴" → 배터/이/랴)가 있어서, 어절 단위 자모 퍼지 매칭을 추가했다. 대신 첫 음절이 다르면 더 높은 유사도를 요구하고, 다른 스킬이 아는 진짜 단어(단위·별칭)는 오타로 보지 않는다("파운드"가 "사운드"로 바뀌던 문제).
  - 관형형으로 꾸미는 동사("방금 맞춘 타이머", "등록된 알림")는 명령 동사에서 뺀다.
  - 반대 뜻 동사가 같이 나오면 나중 것이 이긴다("소리 너무 커 줄여" → 줄이기).
  - 단위 변환 결과 온도 표기는 °C/°F.
  - 볼륨/앱/시스템 상태 스킬은 파일을 셋으로 나누지 않고 `skills/system.py` 안의 클래스 3개로 뒀다(OS 호출은 계획대로 `platform/` 뒤에 있음). 리마인더와 알람은 같은 테이블을 써서 `skills/reminder.py`에 같이 있다.
  - `core/dialog.py`는 따로 만들지 않고 대기 상태(Pending)를 `core/dispatcher.py` 안에 뒀다.
## 1.5단계: 데스크톱 펫 GUI (2026-10-22)
- 요청: CLI 대신 Codex Pets처럼 바탕화면 위에 떠 있는 고양이 캐릭터. 말풍선에 진행 상태, 간단한 입력창.
- PySide6-Essentials 6.12(Qt 6, Windows 휠 cp310-abi3 x86-64 약 82MB). 테두리 없는 투명 창 + 항상 위 + 작업 표시줄에 안 뜨는 도구 창, `setMask`로 투명 부분 클릭 통과, 트레이 아이콘, `QLockFile` 단일 실행.
- 말풍선 상태는 Codex Pets의 상태(작업 중 / 입력 필요 / 완료 / 막힘)를 따르고 알림 상태를 추가했다.
- 백엔드 변경: `Dispatcher.respond()`가 `Reply`(문장, 키, 성공 여부, 대답 대기, 버튼, 알림)를 돌려준다. `handle()`은 CLI용으로 문장만. 스킬은 `status()`로 진행 중인 일을 알려준다.
- 테스트: offscreen GUI 테스트 9개(응답→상태 카운트다운, 확인 버튼, 되묻기 번호, 다른 스레드 알림, 졸기, 입력창 토글, 드래그 위치 저장, PlainText) + YAML 키 검사.
- 실제 Windows에서 확인 안 한 것: 투명 창 + `setMask` 클릭 통과, 항상 위 도구 창의 키보드 포커스, 컬러 이모지 표시, 트레이 알림, `jonnyang-pet.exe` 실행기.

## 배포: 다운로드해서 바로 실행하는 exe (2026-10-22)
- PyInstaller 6.22.3 폴더형 빌드. 한 파일 exe는 실행 때마다 200MB 넘게 임시 폴더에 풀어야 해서 느리고 백신 오탐이 잦아서 안 씀.
- 이 컨테이너(Linux)에서는 Windows exe를 만들 수 없다(PyInstaller는 크로스 빌드 안 됨). 그래서 GitHub Actions windows-latest에서 빌드한다. 같은 spec으로 Linux 빌드를 만들어 `--selftest`(kiwi 모델, 설정, Qt 플러그인, 고양이 그리기)가 통과하는 것까지 확인했다.
- Windows 러너 첫 결과(2026-10-22, 실행 #2): 테스트 440 통과 / 1 건너뜀(볼륨 읽기: 러너에 오디오 장치 없음), Windows 전용 시스템 정보·kiwi 로딩 테스트 통과, 빌드된 exe `--selftest` PASS, Artifact `Jonnyang-0.1.0-win64` 136MB. 실행 #1은 `.gitignore`의 `data/`가 `tests/data/`까지 숨겨서 데이터셋이 커밋 안 된 탓에 실패했다(`/data/`로 고침).
- 크기 줄이기: kiwipiepy 부가 모듈 때문에 딸려오던 numpy/scipy 제외(실행 중엔 안 불림을 확인), Qt 번역은 한국어만. Linux 빌드 기준 451MB → 376MB(zip 209MB → 184MB). 바닥은 kiwi 모델 105MB + kiwi 엔진 40MB.

- 아직 실제 Windows에서 돌려보지 않은 부분: pycaw 볼륨 조작, `os.startfile` 앱/폴더 실행, `winsound` 알림음, 한글 사용자 경로에서 kiwi 로딩. `pytest -m windows`로 확인한다.

## 2단계: 파일·온라인·반복 알림 + 캐릭터 교체 (2026-10-25)

요청: 말풍선 답변이 가끔 겹쳐 보이는 문제 수정, 컨셉 아트대로 캐릭터 수정, 2단계 구현, 완성본을 GitHub Artifact로.

### 말풍선 겹침
- 원인 후보를 모두 막았다. 이 컨테이너(offscreen)에서는 재현되지 않아서 Windows에서 확인이 필요하다.
  1. Windows 투명(레이어드) 창 + `setMask`(창 영역) 조합은 영역 밖으로 밀려난 옛 픽셀이 다시 드러날 수 있다. 레이어드 창은 알파 0 픽셀이 원래 클릭을 통과시키므로(Win32 레이어드 창 히트 테스트 규칙) Windows에서는 마스크를 안 쓴다.
  2. 말풍선의 `QGraphicsDropShadowEffect`(캐시된 픽스맵) 대신 그림자를 직접 그리고, 내용·위치가 바뀌면 창 전체를 다시 그린다.
  3. 옛 버튼은 `deleteLater` 전에 숨긴다.
  4. 타이밍: 알림이 연달아 오면 앞 알림을 덮어쓰지 않고 이어 붙인다. 확인 질문 중에 온 알림·인터넷 결과는 본 뒤 질문으로 돌아간다. 응답 표시 시간은 글 길이 비례(4~25초), 마우스를 올려 두면 유지 + 뗀 뒤 2초.
  5. 펫이 보이는 상태에서는 트레이 알림(Windows 토스트)을 안 띄운다. 기본 위치가 화면 오른쪽 아래라 토스트가 같은 글로 말풍선 위에 겹쳤다.

### 캐릭터
- 컨셉 아트·스프라이트 시트 기준으로 `gui/painter.py`를 새로 그렸다: 하얀 장모, 큰 파란 눈(그라데이션+하이라이트), 분홍 귀 안쪽, 금색 왕관(파란 보석), 남색 망토(금테, 브로치), 금빛 꼬리 끝, 볼 털.
- 표정 13개: 기존 8개 + search(노트북 두드리기, 인터넷 기다릴 때) / book(마법책, 위키·도움말) / files(폴더, 파일 작업) / sad(인터넷 실패) / love(쓰다듬기·고맙다는 말).

### 2단계 기능 (확인한 사실)
| 항목 | 확인 방법 / 결과 |
|---|---|
| Open-Meteo 예보·대기질·지오코딩 | 공식 웹사이트 저장소(open-meteo-website)의 문서 소스: `current=temperature_2m,...`, `daily=...precipitation_probability_max`, 대기질 `current=pm10,pm2_5`, 지오코딩 `name/count/language/countryCode`(2글자는 정확히 일치, 3글자 이상 앞부분 일치), WMO 코드표 |
| Frankfurter | 저장소(hakanensari/frankfurter) 테스트 코드: v1은 2026-05-18부터 deprecated, v2 `GET /v2/rates?base=USD&quotes=KRW` → `[{date, base, quote, rate}]` |
| 위키백과 | REST `page/summary` 대신 오래 유지된 Action API(`action=query&prop=extracts&exintro&explaintext&redirects`, 없으면 `generator=search`) |
| 미세먼지 등급 | 환경부 예보 기준: PM10 30/80/150, PM2.5 15/35/75 (2018-03-27 강화) |
| Known Folder GUID | Wine `knownfolders.h`로 6개(Desktop, Documents, Downloads, Music, Pictures, Videos) 교차 확인 |
| feedparser 6.0.14 / Send2Trash 2.1.0 | PyPI 최신. send2trash는 pywin32가 없으면 ctypes `SHFileOperation`(legacy)으로 휴지통 |
| 이 컨테이너 | 외부 API 접속이 정책으로 막혀 있어서(403) 실제 호출은 CI의 `tools/live_check.py`로 확인 |

- `core/network.py`: urllib, 타임아웃 6초, 메모리 캐시, 실패는 `NetworkError(offline|timeout|http|bad_data|disabled)`. "인터넷 기능 꺼/켜".
- 온라인 스킬: 날씨(오늘/내일/모레/요일/이번 주, 비 질문이면 강수 확률 위주 + 우산·추위·더위 팁), 미세먼지(등급), 기본 동네 설정(되돌리기 가능), 환율(1단위·100엔, 금액 환산, "5만원" 같은 말), 위키 요약(300자), 뉴스(주제별 피드·검색, 번호로 기사 열기, http(s)만).
- GUI에서 온라인 스킬은 작업 스레드로 돌리고 "알아보는 중" 말풍선 + 노트북 표정. CLI·테스트는 바로 실행.
- 파일: 찾기(종류·이름·오래된 것, 깊이 3, 최대 5000개 훑기), 번호로 열기, 정리(종류별 폴더, 받는 중인 파일·1분 안에 바뀐 파일 제외), 휴지통, 옮기기, 이름 바꾸기. 범위는 aliases.yaml 폴더 안쪽만.
- 반복 알림: 매일 / 평일 / 주말 / 매주 ○요일(여러 요일) / ○분·○시간마다. 오전·오후를 안 말하면 1~6시는 오후, 7~11시는 오전. 시각이 없으면 되묻는다. DB 스키마 2(reminders.repeat).
- "내일 비 안 와?"처럼 상태 서술어(오다·춥다 등)에 붙은 "안"은 부정 명령으로 보지 않는다.
- 테스트: 의도 데이터셋 308문장(온라인 42, 파일 16, 반복 7 추가), 시간 파서 79케이스, 온라인(가짜 네트워크) 19, 파일(임시 폴더) 15, 반복 6, GUI 14.

- Windows CI 실행 #4 (2026-10-25): 테스트 564 통과 / 1 건너뜀(오디오 장치 없음), exe `--selftest` PASS, Artifact `Jonnyang-0.2.0-win64`. `tools/live_check.py` 실제 서버 15개 명령 전부 성공(날씨·미세먼지·환율·위키·뉴스).
- 실측으로 고친 것: Open-Meteo 지오코딩은 짧은 한국어 이름에 같은 이름의 작은 마을을 먼저 줄 때가 있다("대구" → 북한 마을, "인천" → 전남 마을). 결과 10개 중 인구가 가장 많은 곳을 고른다. 내장 좌표표는 API가 제대로 찾은 도시들과 0~9km 차이로 맞았다.
- CI 실행 #6 실측: 인구 선택만으로는 부족했다. 지오코딩은 2글자 이름을 정확히 일치로만 찾아서 "수원"으로는 "수원시"가 아예 안 나온다(수원 → 전남 마을, 고양 → 충남 마을, 3글자 "의정부"는 앞부분 일치로 "의정부시"가 나와서 맞음). 2글자면 시·군·구를 붙인 이름도 한국 안에서 같이 찾고 인구 최대를 고르게 바꿨다(`weather.geocode`). 좌표표에 있는 지역은 원래 표를 쓰므로 영향 없었다.

## 그림(스프라이트) 고양이 (2026-10-25)

요청: 도형 고양이 대신 사용자가 준 이미지 느낌이 나게, 스프라이트로 애니메이션.

- 원본: `assets/source/` (애니메이션 시트 1536x1024 = 10줄 x 9프레임, 자세 시트, 컨셉 아트). 사용자 제공 그림.
- `tools/extract_sprites.py`(Pillow + numpy, 개발용)가 잘라서 `src/jonnyang/gui/sprites/`에 저장한다.
  - 애니메이션 시트: 칸 테두리 선 위치로 자르고, 칸 가장자리에서 배경색과 비슷한 픽셀을 채우기로 지운다(고양이 외곽선이 경계).
  - 자세 시트: 알파 채널이 흐릿한 매트라서 흰 배경에 합성한 뒤 같은 방법으로 지운다(빛 번짐 때문에 허용 차이를 더 크게).
  - 프레임 번호 글자(발밑에 떨어진 작은 덩어리)는 버린다. 가장자리는 1px 깎고 살짝 흐리게 + 투명 쪽 색을 고양이 색으로 채워서 흰 테두리·계단 모양이 안 보이게.
  - 같은 애니메이션은 첫 프레임과 가장 많이 겹치는 위치로 맞춰서 떨림을 줄이고, 발끝을 같은 높이에 둔다. 2배 크기 PNG.
  - 결과: 애니메이션 7개(대기·잠·기쁨·놀람·마법·노트북·혼란, 각 9프레임) + 한 장 자세 12개, 약 3.9MB.
- `gui/sprite.py`: 표정 → 애니메이션(persona.yaml `sprites`). 한 장 자세는 숨쉬기·둥실·깡총을 코드로 더하고, 물음표·생각 점·쓰다듬기 하트는 도형으로 겹쳐 그린다. 가만히 있으면 24초마다 윙크·하품·기지개·응원 중 하나. 끌고 다니는 동안 공중부양 자세.
- 그림 파일이 없거나 `sprites.enabled: false`면 기존 도형 고양이(`painter.py`). exe 옆에 `sprites/` 폴더를 두면 그 그림을 쓴다.
- 펫 영역 170x150 → 190x170. 트레이·exe 아이콘도 정면 자세 얼굴.
- 확인: 테스트 567 통과(그림 표정 전부·프레임 수·대체 경로·끌기 자세 추가), 로컬 PyInstaller 빌드 `--selftest`에서 sprites 19개 로드 PASS.

## 다운로드가 "위험"으로 막힘 (2026-10-25)
- 원인: 코드 서명이 없는 PyInstaller exe라서 브라우저 평판 검사(Edge SmartScreen, Chrome 세이프 브라우징)나 Defender ML 탐지(…!ml)에 걸린다.
- 조치: CI에서 PyInstaller 부트로더를 소스에서 직접 컴파일(`PYINSTALLER_COMPILE_BOOTLOADER=1`, `--no-binary=PyInstaller`, PyInstaller 문서 bootloader-building), exe에 버전 정보(제품 이름·버전·설명) 추가. README에 브라우저별 푸는 방법과 Python으로 실행하는 대안.
- 근본 해결은 코드 서명 인증서(유료)뿐. 사용자 결정 필요.
