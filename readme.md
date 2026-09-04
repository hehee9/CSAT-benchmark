# 2026 수능 LLM 풀이 기록

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20this%20project-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/hehee9)

**English version: [README_en.md](README_en.md)**

<div align="center">

### [**Interactive Dashboard**](https://hehee9.github.io/2026-CSAT/)

[![Dashboard](https://img.shields.io/badge/Dashboard-Live-brightgreen?style=for-the-badge&logo=github)](https://hehee9.github.io/2026-CSAT/)

**위 링크를 통해 모델별 점수, 과목별 정답률, 비용 분석을 보기 좋게 확인하실 수 있습니다**

</div>

---

## 개요

다양한 LLM 모델의 2026학년도 수능 문제 풀이 결과를 기록하고 통계를 정리한 데이터입니다.
국어/수학 전과목, 영어, 한국사 영역과 더불어
올해 수능 중 비교적 어렵다는 평이 많은 탐구 과목 4개(생명1/물리1/화학1 및 사회문화)를 대상으로 테스트를 진행했습니다.

Readme에는 **주요 모델의 성적만**을 표기하고 있으니, **전체 성적은 [대시보드](https://hehee9.github.io/2026-CSAT/)에서 확인**해주세요.

2026.06.28 이후 추가된 **고난도 모드**의 경우는 대시보드의 **[고난도](https://hehee9.github.io/2026-CSAT/?mode=hard)** 버튼을 활성화해주세요.

**2026.04.25 기준 물리1 16/17번의 문제 이미지를 서로 반대로 첨부하고 있던 것을 확인해, 해당 두 문항만 전수 재시도 처리했습니다**

---

## 주요 과목 종합 성적

![주요 과목 총점 합 비교](https://hehee9.github.io/2026-CSAT/images/전체.png)

> 📊 **평가 과목**: 국어, 수학, 영어, 한국사, 탐구(물리1, 화학1, 생명과학1, 사회문화) (총 450점 만점)
>
> 📝 **계산 방식**:
> - 국어: 공통 + 선택과목(화법과 작문, 언어와 매체) 평균
> - 수학: 공통 + 선택과목(확률과 통계, 미적분, 기하) 평균
> - 영어, 한국사: 전체 점수
> - 탐구: 4과목을 2과목 선택으로 환산 (4과목 평균 × 2)

![총점 최고/최저 조합 비교](https://hehee9.github.io/2026-CSAT/images/최고_최저.png)

> 📊 **평가 과목**: 위와 동일 (총 450점 만점)
>
> 📝 **계산 방식**:
> - 국어: 공통 + 선택과목(화법과 작문, 언어와 매체) 중 최고/최저점 택1
> - 수학: 공통 + 선택과목(확률과 통계, 미적분, 기하) 중 최고/최저점 택1
> - 영어, 한국사: 전체 점수
> - 탐구: 4과목(물리1, 화학1, 생명과학1, 사회문화) 중 최고/최저점 택2

### 이미지 첨부 문제 vs 텍스트 문제 비교

![이미지 있는 문제 득점률](https://hehee9.github.io/2026-CSAT/images/이미지O.png)

![이미지 없는 문제 득점률](https://hehee9.github.io/2026-CSAT/images/이미지X.png)

> 📊 **평가 범위**: 전체 과목 (국어, 수학, 영어, 한국사, 탐구)
>
> 📝 **계산 방식**:
> - 이미지 첨부 문제: 1개 이상의 이미지가 첨부된 문제들의 득점률 (실제 점수 / 만점 × 100%)
> - 텍스트 문제: 이미지가 없는 문제들의 득점률 (실제 점수 / 만점 × 100%)
> - 모든 과목과 영역의 점수를 통합하여 계산

---

## 테스트 환경 및 주의사항

**중요: 본 테스트는 API를 통한 환경에서 수행되었습니다.**

> 단, GPT-5.5 Pro는 [커스텀 GPTs](https://chatgpt.com/g/g-69ecacbb8fac8191b0eb07e39c62496c-gpt-pro)를 통해 도구를 차단한 웹 환경에서 진행했습니다.

### 테스트 환경
- **실행 방식**: 각 모델의 공식 API를 통해 진행
- **추론 설정**: 최대 출력 토큰 및 추론 예산을 충분히 높게 설정
- **시스템 프롬프트**: 별도의 시스템 프롬프트 제공하지 않음
- **외부 도구**: 검색, 계산기 등 외부 도구를 **제공하지 않음**
- 온도, Top P 등의 설정은 **기본값**으로 유지함. 즉, 측정할 때마다 다소 편차가 있을 수 있음
- **테스트 방법**: 순수하게 모델의 기본 능력만으로 문제 해결

### 일반 사용자 환경과의 차이
본 테스트 결과는 일반적인 공식 홈페이지/앱 사용 환경과 다를 수 있습니다:

1. **시스템 프롬프트**: ChatGPT 공식 웹/앱에서는 모델에게 기본적인 시스템 프롬프트와 더불어 도구 사용법, 사용자 정보 등이 추가로 제공됩니다. 따라서 웹/앱에서 진행하면 같은 질문을 해도 사용자에 따라 결과가 크게 달라질 수 있습니다.
1. **추론 예산 제한**: 일반 사용자 환경에서는 추론 예산이 제한되어 있어, 본 테스트보다 낮은 성능을 보일 수 있습니다.
2. **출력 토큰 제한**: 일반 사용자 환경에서는 최대 출력 토큰이 제한되어 있어, 긴 추론 과정이 필요한 문제에서 답변이 잘릴 수 있습니다.
3. **도구 미사용**: 일반 사용자 환경에서는 필요에 따라 웹 페이지 검색 등을 수행할 수 있으나, 본 테스트는 순수 모델의 지식만으로 답변했습니다.

따라서 **공식 홈페이지나 앱에서와 성능에 차이가 있을 수 있습니다.**

### 평가 방식
- 각 LLM 모델에 문제 텍스트를 제시하고 답안 선택
- 단답형 문항의 경우 정확한 숫자 입력 요구
- 모델이 제시한 최종 답안을 정답과 비교하여 채점

### 문제 제공 방식
- **텍스트 추출**: PDF 파일을 OCR 등을 이용하여 텍스트로 변환하여 제공
- **이미지 처리**: 문제에 포함된 이미지(그래프, 도표, 그림 등)만 별도로 캡처하여 제공
- **원본 유지**: PDF 파일 자체나 전체 페이지 캡처는 제공하지 않음
- 이는 모델이 순수하게 텍스트 이해 능력과 시각 자료 해석 능력을 활용하도록 하기 위함
- **고난도 모드**: 각 섹션(과목)별로 모든 문제를 한 번에 풀게 함

---

## 테스트 모델

### 기본

- **OpenAI GPT 시리즈**
  - GPT-6 Astra (high)
  - GPT-5.6 Sol (max* / high / none)
  - GPT-5.6 Terra (max* / high / none)
  - GPT-5.6 Luna (max* / high / low / none)
  - GPT-5.5 (xhigh* / high / none)
  - GPT-5.5 Instant
  - GPT-5.4 (xhigh* / high / none)
  - GPT-5.4 mini (xhigh / none)
  - GPT-5.4 nano (xhigh / none)
  - GPT-5.2 (xhigh / Instant)
  - GPT-5.1 (high)
  - GPT-5.1 Codex (high)
  - GPT-5.1 Chat
  - GPT-5 mini (high)
  - GPT-5 nano (high)
  - o1 / o3 (high)
  - o3-mini / o4-mini (high)
  - GPT-4.1
  - GPT-4.1 mini
  - GPT-4.1 nano
  - GPT-4o (2024-11-20)
  - GPT-4o mini
  - GPT-OSS 120B (high) (via Fireworks AI)

- **Google Gemini 시리즈**
  - Gemini 3.8 Flash (high / low)
  - Gemini 3.7 Flash (high / low)
  - Gemini 3.6 Flash (high / minimal)
  - Gemini 3.5 Flash (high / minimal)
  - Gemini 3.5 Flash-Lite (high / minimal)
  - Gemini 3.1 Pro (high / low)
  - Gemini 3.1 Flash-Lite (high / minimal)
  - Gemini 3 Pro (high / low)
  - Gemini 3 Flash (high / minimal)
  - Gemini 2.5 Pro (32K Thinking)
  - Gemini 2.5 Flash (2025-09 Preview, 24K Thinking / Non-Thinking)
  - Gemini 2.5 Flash-Lite (2025-09 Preview, 24K Thinking / Non-Thinking)
  - Gemini 2.0 Flash
  - Gemini 2.0 Flash-Lite

- **Google Gemma 시리즈**
  - Gemma 4 31B (high / minimal)
  - Gemma 4 26B A4B (high / minimal)

- **Anthropic Claude 시리즈**
  - Claude Fable 5.1 (high)
  - Claude Fable 5 (high)
  - Claude Opus 4.7 (max* / high / none)
  - Claude Opus 4.5 (32K Thinking / Non-Thinking)
  - Claude Sonnet 4.5 (32K Thinking / Non-Thinking)
  - Claude Haiku 4.5 (32K Thinking / Non-Thinking)

- **xAI Grok 시리즈**
  - Grok 4.5 (high)
  - Grok 4.3
  - Grok 4.1 Fast (Thinking / Non-Thinking)
  - Grok 4 Fast (Thinking)
  - Grok 4

- **Meta Muse Spark 시리즈**
  - Muse Spark 1.3 (minimal / high)
  - Muse Spark 1.2 (minimal / high)

- **Mistral 시리즈**
  - Mistral Small 4 (Thinking / Non-Thinking)

- **DeepSeek 시리즈**
  - DeepSeek V4 Flash Vision Exp (None / Max)
  - DeepSeek V4 Flash 0731 (None / Max)
  - DeepSeek V4 Flash (None / Max)
  - DeepSeek V4 Pro 0813 (Max / None)
  - DeepSeek V4 Pro (None / Max)
  - DeepSeek V3.2 Speciale
  - DeepSeek V3.2 (Thinking)
  - DeepSeek V3.2 (Non-Thinking)
  - DeepSeek V3.2 Exp (Thinking)
  - DeepSeek V3.2 Exp (Non-Thinking)

- **Moonshot AI Kimi 시리즈**
  - Kimi K2.6 (Thinking / Non-Thinking)
  - Kimi K2.5 (Thinking / Non-Thinking)

- **Z.ai GLM 시리즈**
  - GLM-5.3 Flash (high)
  - GLM-5.1 (Thinking / Non-Thinking)
  - GLM-5 (Thinking / Non-Thinking)

- **Alibaba Cloud Qwen 시리즈**
  - Qwen3.8 Max (xhigh)
  - Qwen3.7 Max (Thinking / Non-Thinking)
  - Qwen3.6 Plus (Thinking / Non-Thinking)
  - Qwen3.6 27B (Thinking / Non-Thinking)
  - Qwen3.5 397B (Thinking / Non-Thinking)
  - Qwen3.5 35B A3B (Thinking / Non-Thinking)
  - Qwen3.5 27B (Thinking / Non-Thinking)
  - Qwen3.5 9B (Thinking / Non-Thinking)

- **LGAI EXAONE 시리즈**
  - K-EXAONE 2.0 (Thinking / Non-Thinking)
  - K-EXAONE (Thinking / Non-Thinking)

- **Kakao Kanana 시리즈**
  - Kanana-o 9.8B

- **Upstage Solar 시리즈**
  - Solar Pro 4 (none / max)
  - Solar Pro 3 0126 (high / low)
  - Solar Pro 3 (high / low)

- **Motif 시리즈**
  - Motif 3 (Thinking)
  - Motif 12.7B (Thinking)

※ * GPT-5.x (xhigh), Claude Opus 4.7 (max)는 high에서 틀린 문제만 재측정한 것입니다. 성능 향상에 비해 들어가는 시간과 비용이 너무 커져 이 방식으로 처리한 점 양해 바랍니다.

### 고난도

- **OpenAI GPT 시리즈**
  - GPT-6 Astra (high)
  - GPT-5.6 Sol Pro (high)
  - GPT-5.6 Sol (high / none)
  - GPT-5.6 Terra Pro (high)
  - GPT-5.6 Terra (high / none)
  - GPT-5.6 Luna Pro (high)
  - GPT-5.6 Luna (high / low / none)
  - GPT-5.5 (high / none)
  - GPT-5.5 Pro (xhigh, GPTs)
  - GPT-5.4 mini (xhigh / none)
  - GPT-5.4 nano (xhigh / none)
  - o1 (high)
  - GPT-4.1
  - GPT-4o (2024-11-20)

- **Google Gemini 시리즈**
  - Gemini 3.8 Flash (high / low)
  - Gemini 3.7 Flash (high / low)
  - Gemini 3.6 Flash (high / minimal)
  - Gemini 3.5 Flash (high / minimal)
  - Gemini 3.5 Flash-Lite (high / minimal)
  - Gemini 3.5 Flash (high / minimal)
  - Gemini 3.1 Pro (high / low)
  - Gemini 3.1 Flash-Lite (high / minimal)
  - Gemini 3 Flash (high / minimal)
  - Gemini 2.5 Pro (32K Thinking)

- **Google Gemma 시리즈**
  - Gemma 4 31B (high / minimal)
  - Gemma 4 26B A4B (high / minimal)

- **Anthropic Claude 시리즈**
  - Claude Fable 5.1 (high)
  - Claude Fable 5 (high)
  - Claude Opus 5 (high / none)
  - Claude Sonnet 5 (high / none)
  - Claude Opus 4.8 (high / none)
  - Claude Sonnet 4.6 (high / none)
  - Claude Haiku 4.5 (32K Thinking / Non-Thinking)

- **xAI Grok 시리즈**
  - Grok 4.5 (high)
  - Grok 4.3 (Thinking / Non-Thinking)

- **Meta Muse Spark 시리즈**
  - Muse Spark 1.3 (minimal / high)
  - Muse Spark 1.2 (minimal / high)

- **DeepSeek 시리즈**
  - DeepSeek V4 Flash Vision Exp (None / Max)
  - DeepSeek V4 Flash 0731 (None / Max)
  - DeepSeek V4 Flash (Max / None)
  - DeepSeek V4 Pro 0813 (Max / None)
  - DeepSeek V4 Pro (Max / None)

- **Alibaba Cloud Qwen 시리즈**
  - Qwen3.8 Max (xhigh)
  - Qwen3.7 Max (Thinking / Non-Thinking)
  - Qwen3.6 27B (Thinking / Non-Thinking)

- **MiniMax 시리즈**
  - MiniMax M3 (Thinking / Non-Thinking)

- **Z.ai GLM 시리즈**
  - GLM-5.3 Flash (high)
  - GLM-5.2 (Thinking / Non-Thinking)

- **Moonshot AI Kimi 시리즈**
  - Kimi K2.6 (Thinking / Non-Thinking)

- **LGAI EXAONE 시리즈**
  - K-EXAONE 2.0 (Thinking / Non-Thinking)
  - K-EXAONE (Thinking / Non-Thinking)

- **Kakao Kanana 시리즈**
  - Kanana-o 9.8B

- **Upstage Solar 시리즈**
  - Solar Pro 4 (none / max)
  - Solar Pro 3 (high / low)

- **Motif 시리즈**
  - Motif 3 (Thinking)
  - Motif 12.7B (Thinking)

※ 이미지 인식이 불가능한 모델은 텍스트로만 진행했습니다.

---

## 국어 영역

### 모델별 성적 (100점 만점)
![국어 2](https://hehee9.github.io/2026-CSAT/images/국어.png)

### 고난도 모드
![국어 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_국어.png)

---

## 수학 영역

### 모델별 성적 (100점 만점)
![수학 2](https://hehee9.github.io/2026-CSAT/images/수학.png)

### 고난도 모드
![수학 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_수학.png)

---

## 영어 영역

### 모델별 성적 (100점 만점)
![영어 2](https://hehee9.github.io/2026-CSAT/images/영어.png)

### 고난도 모드
![영어 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_영어.png)

---

## 한국사 영역

### 모델별 성적 (50점 만점)
![한국사 2](https://hehee9.github.io/2026-CSAT/images/한국사.png)

### 고난도 모드
![한국사 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_한국사.png)

---

## 탐구 영역

### 물리1

![물리1 2](https://hehee9.github.io/2026-CSAT/images/물리1.png)
![물리1 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_물리1.png)

> ※ 선이나 화살표가 많은 시각 자료가 포함된 문제에서 오답이 많아 평균적으로 점수가 낮습니다.

### 화학1

![화학1 2](https://hehee9.github.io/2026-CSAT/images/화학1.png)
![화학1 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_화학1.png)

### 생명과학1

![생명1 2](https://hehee9.github.io/2026-CSAT/images/생명1.png)
![생명1 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_생명1.png)

### 사회문화

![사회문화 2](https://hehee9.github.io/2026-CSAT/images/사회문화.png)
![사회문화 고난도 모드](https://hehee9.github.io/2026-CSAT/images/고난도_사회문화.png)

---

## 비용 효율성

API 비용(토큰 사용량)과 점수 간의 상관관계를 분석한 결과입니다.

### 비용 vs 성능

![비용 효율성](https://hehee9.github.io/2026-CSAT/images/비용_분석.png)

공식 공급자가 없는 모델의 경우, OpenRouter의 평균적인 비용을 바탕으로 측정했습니다.

| 모델명 | 입력 비용 | 출력 비용 |
| :--- | :--- | :--- |
| GPT-OSS 120B | 0.15 | 0.6 |
| Gemma 4 31B | 0.14 | 0.4 |
| Gemma 4 26B A4B | 0.1 | 0.4 |
| Motif 12.7B (Thinking) | 0.1 | 0.2 |

※ 1,000,000토큰 당 달러 기준입니다.

※ 아직 유료 제공 API가 없는 경우는 비슷한 규모의 오픈 모델 유료 API 비용을 기준으로 삼았습니다.

### 토큰 사용량

![토큰 사용량](https://hehee9.github.io/2026-CSAT/images/토큰_사용량.png)

---

## 후원

이 프로젝트는 모든 테스트를 실제 API를 통해 진행하고 있으며, 토큰 사용량과 비용을 투명하게 공개하고 있습니다.

새로운 모델이 출시될 때마다 전 과목을 테스트하기 때문에 적지 않은 API 비용이 발생합니다. 프로젝트 유지에 도움을 주고 싶으시다면 Ko-fi를 통해 후원해 주세요!

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/hehee9)

---

## 평가 대상 상세

### 국어 영역
- **평가 대상**: 2026학년도 대학수학능력시험 국어 영역
  - 공통 문항: 34문항 (76점)
  - 선택 과목: 화법과 작문 (11문항, 24점) / 언어와 매체 (11문항, 24점)
- **총점**: 100점 만점 (공통 76점 + 선택과목 24점)

### 수학 영역
- **평가 대상**: 2026학년도 대학수학능력시험 수학 영역
  - 공통 문항: 22문항 (74점)
  - 선택 과목: 확률과 통계 (8문항, 26점) / 미적분 (8문항, 26점) / 기하 (8문항, 26점)
- **총점**: 100점 만점 (공통 74점 + 선택과목 26점)

### 영어 영역
- **평가 대상**: 2026학년도 대학수학능력시험 영어 영역
  - 전체 문항: 45문항
- **총점**: 100점 만점

### 한국사 영역
- **평가 대상**: 2026학년도 대학수학능력시험 한국사 영역
  - 전체 문항: 20문항
- **총점**: 50점 만점 (필수 영역)

### 탐구 영역 - 물리1
- **평가 대상**: 2026학년도 대학수학능력시험 물리1
  - 전체 문항: 20문항
- **총점**: 50점 만점

### 탐구 영역 - 화학1
- **평가 대상**: 2026학년도 대학수학능력시험 화학1
  - 전체 문항: 20문항
- **총점**: 50점 만점

### 탐구 영역 - 생명과학1
- **평가 대상**: 2026학년도 대학수학능력시험 생명과학1
  - 전체 문항: 20문항
- **총점**: 50점 만점

### 탐구 영역 - 사회문화
- **평가 대상**: 2026학년도 대학수학능력시험 사회문화
  - 전체 문항: 20문항
- **총점**: 50점 만점

## 평가 방법 상세

OCR을 이용해 우선 문제를 텍스트로 추출한 후, 잘못 옮겨진 부분은 수작업으로 수정했습니다.

모든 문제는 필요한 최소한의 정보만을 프롬프트로 각각 입력하였습니다.
지문 1개에 연계 문제가 있는 구조라면 지문+해당 문제 개별 출제와 같은 방식입니다.

수식은 LaTeX로 변환하여 입력해 식 자체를 잘못 이해하는 것을 방지했습니다. 이미지에서 텍스트를 인식하는 것 또한 성능 지표이긴 하지만, 문제를 잘못 인식해 틀리는 것은 본 프로젝트의 방향성에 맞지 않는다고 판단하였습니다.

오류로 인해 응답을 아예 받지 못한 경우에만 재시도 하였으며, 다른 형태의 잘못된 응답은 모두 오답 처리 했습니다.

### 입력 프롬프트 예시

- 지문이 있는 경우 (국어 홀수형 3번 문항):
````
[1～3] 다음 글을 읽고 물음에 답하시오.

```
 글을 읽고 그 의미를 이해하는 독해에는 글의 유형이나 독서 흥미 등의 다양한 요소가 영향을 미칠 수 있다. ...제공했다는 의의가 있다.
```

3. 윗글을 바탕으로 <보기>를 이해한 내용으로 적절하지 않은 것은? [3점]
```
<보기>
단순 관점을 지지하는 연구자 갑은 학생 A, B의 독해 능력을 분석하기 위한 활동을 진행하였다. ...
○ 소리 내어 단어 읽기: 학생 A는 활동 자료에 있는 단어를 빠르고 정확하게 ...
○ 중심 내용 파악하기: 학생 A는 활동 자료를 글로 읽을 때와 말로 들을 때 모두 ...
```

① 갑은 학생 A가 해독은 발달되었지만, ...
② 갑은 학생 A가 글자와 글자 소리에 대한 학습을 통해 ...
③ ...
④ ...
⑤ ...
````

- 수식이 있는 경우 (수학 홀수형 15번 문항):
````
15. 함수 $f(x)$가
$f(x) = \begin{cases} -x^2 & (x < 0) \\ x^2-x & (x \ge 0) \end{cases}$
이고, 양수 a에 대하여 함수 $g(x)$를 ... $k+h(3)$의 값은? [4점]

① $\frac{9}{2}$
② $\frac{11}{2}$
③ ...
④ ...
⑤ ...
````

- 이미지가 있는 경우 (한국사 홀수형 2번 문항):
````
2. 밑줄 친 '이 나라'에 대한 설명으로 옳은 것은?
```
[이미지: 02_01 (실제로 이미지를 첨부함)]
> **寶曆(보력) 慶雲(경운)**
유물은 고구려를 계승한 *이 나라* 제3대 왕 문왕의 배우자인 ... 고구려 후기 양식을 이어받은 것이다.
```

① 골품제를 실시하였다.
② 평양으로 천도하였다.
③ ...
④ ...
⑤ ...
````

---

## 라이선스 및 저작권

### 프로젝트 라이선스
본 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE.md) 파일을 참조하세요.

### 수능 문제 저작권
- 2026학년도 대학수학능력시험 문제는 **한국교육과정평가원**의 저작물입니다.
- 본 저장소는 문제 원본을 포함하지 않으며, 오직 **모델의 답변 결과 및 분석 데이터**만 포함합니다.
- 엑셀 파일은 문항 번호와 정답만 포함하며, 전체 문제 텍스트는 저작권 문제로 제공하지 않습니다.
- 수능 문제를 활용하시려면 한국교육과정평가원의 공식 자료를 이용하시기 바랍니다.

---

* 연락처: gyugyum@gmail.com