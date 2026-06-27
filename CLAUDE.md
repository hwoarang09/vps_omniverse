# vps_omniverse — 프로젝트 컨텍스트 & 에이전트 로스터

VPS(AMHS 시뮬레이터)의 맵을 **OpenUSD**로 변환하고 Omniverse(Kit)에서 시각화/실시간 렌더하는 프로젝트.
OpenUSD 학습 + 자격증(NCP-OUSD) 대비를 겸한다.

## 1. 구조 한눈에
- `converter/` — **빌드타임** 맵→USD 변환기 (순수 `usd-core`/pxr, Omniverse 불필요).
  - 흐름: `mapio.py`(파싱) → `geometry.py`(기하·hide 계산) → `usd_build.py`(USD prim) →
    `build_base.py`(raw 2줄 → `out/base.usda`) + `build_line_cut.py`(invisibleIds 오버라이드 → `out/line_cut.usda`).
  - 합성: 정적 `out/composed.usda` (subLayers=[line_cut, base]) — **여는 건 이거**.
- `exts/` — **런타임** Kit 확장(`omni.*`, 실시간 MQTT 차량 등). 변환기와 분리.
- `input/fab_map/` — 입력 맵, 확장자 전부 `.map`.
- `out/` — 생성물(gitignore). 단 `out/composed.usda`만 추적.
- `docs/` — 문서. `docs/HTML_TEMPLATE/template.html`(문서 템플릿), `docs/html/`(생성된 HTML 문서).

핵심 개념: 레일 겹침 정리를 **USD 레이어 합성(LIVRPS)**으로. base엔 raw 2줄 전부, line_cut이
`over /World/Rails { invisibleIds }`로 **비파괴 오버라이드**. base/line_cut 인덱스는
`geo.dual_rail_segments_tagged` 단일 함수 공유로 1:1 정렬.

## 2. 실행
변환 파이썬: `/home/vosui/vosui/omniverse_test/.venv/bin/python` (pxr 설치됨). **`converter/` 안에서** 실행.
```bash
cd converter
<venv> build_base.py     ../input/fab_map ../out/base.usda
<venv> build_line_cut.py ../input/fab_map ../out
# 보기: usdview ../out/composed.usda   (raw만: ../out/base.usda)
```

## 3. 에이전트 로스터 (프로젝트 전용 — `.claude/agents/`)
이 에이전트들은 **vps_omniverse 폴더에서 Claude 를 켤 때만** 로드된다(프로젝트 격리).
다른 데서 켜면 안 보임. 호출: "doc 에이전트 돌려" 처럼 이름으로 부르거나, 작업을 시키면 Claude가 매칭.

| 에이전트 | 언제 | 하는 일 |
|---|---|---|
| **doc-agent** | "문서 만들어줘 / 문서화" | 개발 내용을 `docs/HTML_TEMPLATE/template.html` 기반 HTML 문서로 생성·갱신(`docs/html/`). 번호 접이식 목차+검색+버전. |
| **dev-agent** | "구현 / 수정 / 버그" | converter·exts 일반 개발. 변경 후 실제 실행·USD 수치 검증까지. |
| **code-quality-agent** | "린트 / 품질 / 정리" | 파이썬 품질 점검(ruff 중심, 선택 mypy/vulture). 설정 없으면 ruff 부트스트랩. sonar/knip은 JS용이라 안 씀. |

각 정의: `.claude/agents/<이름>.md`. 새 에이전트 추가 = 거기에 `.md` 하나 더.

## 4. 공통 규칙
- 커밋/푸시는 **사용자가 명시할 때만**. 기존 미커밋 변경(예: `exts/.../extension.py`)은 건드리지 말 것.
- 문서/주석 한국어. 정확성 > 분량. 추측 금지(코드/커밋 근거 + `파일:라인` 인용).
- 변환기는 순수 usd-core, 런타임(exts)만 Omniverse API.
