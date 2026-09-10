# 사용·방법론 가이드

이 문서는 CSAT-benchmark를 설치한 뒤 공개 입력을 확인하고, 모델 실행·채점·Excel 수동 보정·공개 배포까지 진행하는 방법을 설명합니다. 처음 실행할 때는 저장소의 공개 예시를 사용하고, 실제 시험은 개인 문항·설정 영역에서 실행합니다.

## 1. 설치와 설정

Python 3.10 이상이 필요합니다.

```bash
git clone https://github.com/hehee9/CSAT-benchmark.git
cd CSAT-benchmark
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config.example.json config.json
```

macOS·Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cp config.example.json config.json
```

`config.example.json`은 모델별 `api_key_env`와 검증기 `verifier.api_key_env`로 키 이름을 참조합니다. 로컬 `.env`에는 해당 환경 변수의 실제 키를 입력하고, 설정 JSON에는 키 문자열을 기록하지 않습니다. 모델 설정의 `name`, `api_type`, `model_id`를 바꾸거나 모델 항목을 추가해 실행 대상을 정합니다. `knowledge_cutoff`는 모델 지식 컷오프 월을 `YYYY-MM` 형식으로 기록하며, 알 수 없으면 `null`로 둡니다. `plan_message_ko`와 `plan_message_en`은 대시보드에 표시할 한국어·영어 요금제 안내 문구입니다. 두 필드를 생략하면 기존 언어별 설명을 유지하고, 값을 빈 문자열로 지정하면 해당 언어 설명을 삭제합니다. `config.json`은 이 예시를 복사해 만드는 실제 설정 파일이며, 실행기와 배치 실행기의 기본 설정 경로는 저장소 루트 `config.json`입니다.

키 이름은 호출 서비스에 맞춥니다. OpenRouter 주소는 `OPENROUTER_API_KEY`, Upstage 주소는 `UPSTAGE_API_KEY`처럼 참조하며, 같은 서비스에서 여러 키를 쓰면 서로 다른 환경 변수 이름을 지정합니다.

공개 문항 예시와 설정으로 API 호출 없이 실행 조건을 확인할 수 있습니다.

```bash
python api_solver.py --exam example-text --config config.example.json --check
```

## 2. 시험 매니페스트와 문항 작성

시험 하나는 `benchmarks/<exam-id>.json` 매니페스트로 등록합니다. 매니페스트는 시험 ID·표시용 짧은 이름(`short_name`)·시험 시행 월(`exam_month`)·문항 루트·개인 실행 결과 루트(`results_dir`)·섹션·실행 모드를 정의합니다. `exam_month`는 `YYYY-MM` 형식 또는 `null`이고, 기존 사용자 매니페스트에서 생략한 `short_name`은 `title`, `exam_month`는 `null`로 해석합니다. `publish: true`인 시험만 공개 대시보드 카탈로그에 들어갑니다.

매니페스트의 기본 모드는 일반 모드이며 섹션 묶음 입력을 한 번 수행합니다. 쉬움 모드는 `--easy`로 선택하고 문항별 입력을 한 번 수행합니다.

매니페스트 예시는 [`benchmarks/example-text.json`](../benchmarks/example-text.json)을 참고하세요.

섹션의 `questions` 파일 예시는 [`examples/sample_data/questions.json`](../examples/sample_data/questions.json)에서 확인할 수 있습니다. 파일은 `data_dir` 아래에 두고 다음 필드를 사용합니다.

문항 본문은 `question_path`로 파일을 가리키거나 `question_text`에 직접 넣습니다. 이미지·PDF·음성·동영상은 각각 `image_paths`, `pdf_paths`, `audio_paths`, `video_paths`에 상대 경로 목록으로 선언합니다. `number`, `correct_answer`, `points`는 필수 정수이고, 문항 배점의 합은 섹션 `max_points`와 같아야 합니다.

일반 모드의 섹션 묶음 입력에서는 번호 범위가 있는 공통 지문·자료를 한 번만 포함하고, 공통 자료와 이미지 경로의 중복을 제거합니다.

즉시 실행기는 OpenAI 호환 Chat Completions·Responses, Anthropic, Google의 PDF 요청을 구성합니다. 이미지·PDF를 사용할 모델은 `supports_vision: true`로 설정하고 해당 접속 서비스의 파일 지원 여부를 확인합니다. DeepSeek의 PDF와 Google 이외 공급자의 음성·동영상 입력은 전송 전에 오류로 처리합니다. 배치 실행은 PDF·음성·동영상 입력을 지원하지 않으므로 해당 첨부가 있는 문항은 즉시 실행기로 처리해야 합니다.

탐구 과목을 추가할 때는 실제 과목명을 `subject`에 쓰고 `group`을 `탐구`로 지정합니다. 예를 들어 `탐구/지구과학1`, `탐구/지구과학2`처럼 target을 만들면 실행기와 대시보드가 해당 과목을 매니페스트에서 읽습니다. 새 과목 목록을 소스 코드에 추가할 필요가 없습니다.

문항 본문·미디어와 실행 결과는 `problems/` 아래 개인 영역에 둡니다. 공개 예시처럼 공개가 허용된 입력만 `examples/`에 넣고, 실제 문제 본문·원문 응답·배치 중간 파일은 공개 결과에 복사하지 않습니다.

## 3. 즉시 실행

시험 목록은 다음 명령으로 확인합니다.

```bash
python api_solver.py --list-exams
```

공개 예시의 실행 조건을 확인한 뒤 실제 모델을 실행합니다.

```bash
python api_solver.py --exam example-text --config config.example.json --check
python api_solver.py --exam example-text --config config.example.json
# 쉬움 모드를 제공하는 시험의 문항별 실행
python api_solver.py --exam EXAM --config CONFIG --easy
```

`--exam`은 실행·확인의 대상 시험을 지정하는 필수 인자입니다. 범위를 지정하지 않으면 매니페스트의 모든 target을 실행합니다. 필요한 범위만 실행할 때는 기존 선택자인 `--targets`, `--subject`와 `--section`, `--subjects`, `--models`를 사용합니다. `--benchmark-all`은 매니페스트 전체 실행을 명시하는 선택적 표현입니다. `--question-numbers`는 `--easy` 문항별 실행에서만 사용할 수 있습니다.

결과는 시험 매니페스트의 `results_dir`가 가리키는 루트 아래 모드별 정본으로 저장됩니다. 기본 실행은 일반 모드를 사용하고, `--easy`를 붙이면 쉬움 모드를 사용합니다.

```text
<results_dir이 가리키는 루트>/
└── default/
    ├── results.json                   # 실행 색인·모델별 파일 위치
    └── models/<모델별 폴더>/
        ├── results.json               # 해당 모델 원본 응답
        └── verified.json              # 해당 모델 검증 결과
```

`default` 대신 `easy`를 사용하면 같은 구조가 `<results_dir이 가리키는 루트>/easy/` 아래에 만들어집니다.

기존 정본에서 누락되었거나 전송·공급자 오류로 완료되지 않은 결과만 다시 시도할 수 있습니다.

```bash
python api_solver.py --exam example-text --config config.example.json --retry-failed
```

`--retry-failed`는 누락·기술 실패만 대상으로 하며, 완료된 오답·`no_answer`·응답 거부는 그대로 유지합니다. 기존 결과에 선택 결과를 명시적으로 upsert하는 호환 옵션으로 `--merge`도 사용할 수 있습니다.

## 4. Batch API 실행

모델 설정에서 `batch_supported`가 `true`인 모델은 다음 수명주기를 사용합니다. 아래에서 `EXAM`과 `CONFIG`는 각각 시험 ID와 Batch 지원 모델이 담긴 설정 파일 경로입니다. 일반 모드가 기본이며, 쉬움 모드는 각 명령에 `--easy`를 추가합니다.

```bash
# 모델별 Batch 제출
python batch_solver.py submit --exam EXAM --config CONFIG

# 제출된 Batch 상태 조회
python batch_solver.py status --exam EXAM --config CONFIG

# 모든 Batch가 끝날 때까지 기다린 뒤 결과 다운로드
python batch_solver.py wait --exam EXAM --config CONFIG

# 끝난 결과만 다운로드
python batch_solver.py download --exam EXAM --config CONFIG

# 기존 결과를 유지하고 누락·기술 실패 슬롯만 다시 제출
python batch_solver.py retry --exam EXAM --config CONFIG
```

`submit`과 `retry`는 기본적으로 제출한 Batch가 끝날 때까지 기다린 뒤 결과를 다운로드합니다. 제출만 하고 다음 명령으로 상태를 확인하려면 두 명령에 `--no-wait`를 추가하세요. `wait` 명령은 완료 대기와 결과 다운로드를 항상 수행합니다.

`--models`, `--targets`, `--subject`와 `--section`, `--subjects`로 제출 범위를 좁힐 수 있습니다. `--benchmark-all`은 시험 전체 제출을 명시하고, `--question-numbers`는 `--easy` 문항별 제출에서만 사용할 수 있습니다. 공급자 Batch ID는 실행 상태에 저장되므로 상태 조회·대기·다운로드·재시도 명령에서 별도로 입력하지 않습니다. 같은 시험·모드·모델에 활성 Batch가 있으면 새 제출을 시작하지 않습니다.

배치 입력과 다운로드 원본은 해당 모드의 `models/<모델별 폴더>/`에 함께 저장됩니다.

## 5. 답안 추출과 채점

실행이 끝나면 다음 명령으로 비공개 `verified.json`을 생성합니다.

```bash
python verify_answers.py \
  --exam example-text \
  --config config.example.json

# 쉬움 모드에서 특정 모델만 채점
python verify_answers.py \
  --exam EXAM \
  --easy \
  --models "GPT-5.6 Sol (low)" \
  --config config.example.json
```

일반 모드는 섹션 묶음 응답을, 쉬움 모드는 문항별 응답을 채점합니다. 모델 생성은 각 입력마다 한 번이며, 답 추출기는 응답마다 두 번 확인하고 결과가 다를 때만 세 번째 확인을 추가합니다. 이 확인 횟수는 모델 생성 횟수가 아닙니다.
채점 범위는 `--targets`, `--subject`와 `--section`, `--subjects`, `--models`로 좁힐 수 있습니다. `--benchmark-all`은 매니페스트 전체 채점을 명시하며, `--question-numbers`는 쉬움 모드에서만 사용할 수 있습니다.

기본 실행은 미채점만 처리합니다. `--models`로 명시한 범위가 전부 기채점이면 자동 재채점하며, 그 외에 재채점하려면 `--update`를 붙입니다.

```bash
python verify_answers.py --exam EXAM --models "모델명" --update
```

정답이면 배점만큼 부여하고, 완료된 오답·`no_answer`·응답 거부는 그대로 오답으로 기록합니다. 전송·공급자 기술 오류로 응답이 완료되지 않은 결과만 재시도 대상으로 남습니다.

검증기 설정은 모델 설정의 `verifier.model_id`와 `verifier.api_key_env`를 사용합니다. 검증기 호출도 API 요청이므로 실행과 별도의 비용이 발생할 수 있습니다.

## 6. JSON과 Excel 왕복

시험 실행 결과의 동기화 명령은 다음과 같습니다.

`verified.json`은 검증 결과의 기준 파일이며, Excel은 사람이 답안을 검토·수정하는 표입니다.

| 명령 | 입력 | 출력 | 용도 |
| --- | --- | --- | --- |
| `sync_data.py import` | 비공개 `verified.json` | 모델별 답안 열이 있는 Excel | 검증 결과를 사람이 읽고 수정할 표 생성 |
| `sync_data.py export` | 수동 수정한 Excel | 비공개 `verified.json` | Excel 답안을 채점 결과에 반영 |

동기화 범위는 `--targets`, `--subject`와 `--section`, `--subjects`, `--models`, `--benchmark-all`로 지정할 수 있습니다. `--question-numbers`는 쉬움 모드에서만 사용할 수 있습니다.

```bash
# 일반 모드의 JSON -> Excel
python sync_data.py import --exam example-text --excel answers.xlsx

# answers.xlsx에서 모델별 답안 열을 수정한 뒤 Excel -> JSON
python sync_data.py export --exam example-text --excel answers.xlsx

# 쉬움 모드
python sync_data.py import --exam EXAM --easy --excel easy_answers.xlsx
python sync_data.py export --exam EXAM --easy --excel easy_answers.xlsx
```

Excel에는 모델마다 답안 열 하나를 둡니다. `export`는 수동으로 수정한 답안을 `verified.json`에 반영합니다. 비워 둔 셀은 기존 값을 유지합니다. 숫자 답을 입력하고 `-1`은 미응답, `-2` 또는 `refusal`은 응답 거부로 기록합니다.

기존 2026 Excel 자료는 [2026 수능 LLM 풀이.xlsx](../2026%20%EC%88%98%EB%8A%A5%20LLM%20%ED%92%80%EC%9D%B4.xlsx)가 쉬움 기록이고 [2026 수능 LLM 풀이 hard.xlsx](../2026%20%EC%88%98%EB%8A%A5%20LLM%20%ED%92%80%EC%9D%B4%20hard.xlsx)가 일반 기록입니다. 기존 기록과의 호환을 위해 파일명은 유지합니다.

모델 설정의 공개 설명을 수정한 뒤에는 Excel이나 점수 파일을 읽지 않는 다음 명령으로 모델 공개 메타데이터를 동기화합니다. 인증 키가 없어도 실행되며, 출력 경로를 생략하면 설정 파일이 속한 프로젝트의 `web/model_metadata.json`에 저장합니다. `plan_message_ko` 또는 `plan_message_en`을 빈 문자열로 바꾸면 해당 언어 설명이 공개 메타데이터에서 삭제됩니다.

```bash
python sync_data.py metadata --config config.example.json
python sync_data.py metadata --config config.example.json --output temporary/model_metadata.json
```

## 7. 공개 산출물과 대시보드

검증과 수동 보정을 마친 뒤 완료된 섹션·모델을 공개 경로에 병합합니다.

```bash
python sync_data.py publish --exam example-text
# 쉬움 모드의 완료 결과 공개
python sync_data.py publish --exam EXAM --easy
# 실행 기록 대신 현재 설정의 선택 모델 메타데이터를 사용할 때
python sync_data.py publish --exam example-text --config CONFIG
```

기본 모드는 일반이며 `--easy`를 붙이면 쉬움 모드의 결과를 공개합니다. 기본 출력은 `published/<exam-id>/<mode>/results.json`, `token_usage.json`, `questions_metadata.json`입니다. 선택 모델의 기록된 메타데이터는 `web/model_metadata.json`에 병합하며, `--config`를 지정하면 해당 설정의 현재 메타데이터를 사용합니다. 공개 결과에는 채점과 집계에 필요한 값만 들어가며 모델 응답 원문은 포함되지 않습니다. `publish: true`인 매니페스트는 GitHub Pages 자료 동기화 대상이 됩니다.

`master`에 공개 산출물을 반영하면 저장소의 GitHub Actions가 `web/` 자료를 동기화하고 Pages 사이트를 갱신합니다. 대시보드는 [CSAT-benchmark](https://hehee9.github.io/CSAT-benchmark/)에서 시험을 선택해 볼 수 있습니다.

2026학년도 수능 대시보드는 **일반** 모드를 기본으로 제공하고 **쉬움** 모드도 함께 제공합니다. **정규화 점수 450점**과 매니페스트에서 계산한 **원점수 합계**를 선택할 수 있습니다. 탐구 정규화 점수는 매니페스트에 포함된 선택 과목의 평균 × 2로 계산하며, 값이 없는 선택 과목은 0점으로 포함합니다. 미래 매니페스트의 탐구 17과목 기준 원점수 합계는 1276점입니다. 시험 매니페스트에 따라 만점·과목 필터·모델 필터가 동적으로 바뀝니다.

공개 데이터는 기존 결과 JSON과 토큰 기록의 모든 모델 항목을 기준으로 유지하며, 원문 응답이 없는 과거 기록도 점수·집계에 남습니다. 없는 원문은 새로 만들지 않습니다.
