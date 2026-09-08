# 2026 CSAT LLM Solving Records

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20this%20project-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/hehee9)

**Korean version: [readme.md](readme.md)**

<div align="center">

### [**Interactive Dashboard**](https://hehee9.github.io/CSAT-benchmark/)

[![Dashboard](https://img.shields.io/badge/Dashboard-Live-brightgreen?style=for-the-badge&logo=github)](https://hehee9.github.io/CSAT-benchmark/)

**Use the link above to view model scores, subject-level accuracy, and cost analysis in a readable dashboard.**

</div>

---

## Overview

This dataset records and summarizes the results of various LLM models solving the 2026 Korean CSAT.
The test covers all Korean and Math sections, English, Korean History, and
four inquiry subjects that were widely considered relatively difficult in this year's CSAT: Life Science I, Physics I, Chemistry I, and Society & Culture.

The README shows **only the scores of major models**, so please check the **full results on the [dashboard](https://hehee9.github.io/CSAT-benchmark/)**.

Section-bundled 2026 records are shown in the dashboard's **[Normal](https://hehee9.github.io/CSAT-benchmark/?exam=csat-2026&mode=default&scoreBasis=normalized)** mode, and question-by-question records are shown in **[Easy](https://hehee9.github.io/CSAT-benchmark/?exam=csat-2026&mode=easy&scoreBasis=normalized)** mode.

To run the benchmark directly, see the [usage guide](guides/usage.md).

**As of 2026-04-25, I found that the images for Physics I questions 16 and 17 had been attached in reverse order, so only those two questions were fully retried.**

---

## Overall Scores for Major Subjects

![Overall total score comparison](https://hehee9.github.io/CSAT-benchmark/images/전체.png)

> 📊 **Evaluated subjects**: Korean, Math, English, Korean History, Inquiry subjects (Physics I, Chemistry I, Life Science I, Society & Culture), for a total of 450 points.
>
> 📝 **Scoring method**:
> - Korean: common section + average of electives (Speech & Writing, Language & Media)
> - Math: common section + average of electives (Probability & Statistics, Calculus, Geometry)
> - English and Korean History: full score
> - Inquiry: converted as two selected subjects from four subjects (average of four subjects × 2)

![Best/worst total score combination comparison](https://hehee9.github.io/CSAT-benchmark/images/최고_최저.png)

> 📊 **Evaluated subjects**: Same as above, for a total of 450 points.
>
> 📝 **Scoring method**:
> - Korean: common section + best/worst score among electives (Speech & Writing, Language & Media)
> - Math: common section + best/worst score among electives (Probability & Statistics, Calculus, Geometry)
> - English and Korean History: full score
> - Inquiry: best/worst two-subject combination among four subjects (Physics I, Chemistry I, Life Science I, Society & Culture)

### Image-attached Questions vs Text-only Questions

![Score rate for questions with images](https://hehee9.github.io/CSAT-benchmark/images/이미지O.png)

![Score rate for questions without images](https://hehee9.github.io/CSAT-benchmark/images/이미지X.png)

> 📊 **Evaluation range**: All subjects (Korean, Math, English, Korean History, Inquiry)
>
> 📝 **Scoring method**:
> - Questions with images: score rate for questions with one or more attached images (actual score / maximum score × 100%)
> - Text-only questions: score rate for questions without images (actual score / maximum score × 100%)
> - Scores are calculated by combining all subjects and sections.

---

## Test Environment and Notes

**Important: Except for GPT-5.5 Pro, this test was conducted through each model's official API.**

> However, GPT-5.5 Pro was run in a tools-disabled web environment through [custom GPTs](https://chatgpt.com/g/g-69ecacbb8fac8191b0eb07e39c62496c-gpt-pro).

### Test Environment
- **Execution method**: Each model except GPT-5.5 Pro was tested through its official API.
- **Reasoning settings**: Maximum output tokens and reasoning budgets were set sufficiently high.
- **System prompt**: No separate system prompt was provided.
- **External tools**: No external tools such as search or calculators were **provided**.
- Temperature, Top P, and similar settings were kept at their **default values**. This means results may vary somewhat between runs.
- **Test method**: Problems were solved purely with the model's base capabilities.

### Differences from Ordinary User Environments
These test results may differ from ordinary official website/app usage environments:

1. **System prompt**: Official ChatGPT web/app environments provide models with a default system prompt along with tool usage instructions, user information, and other context. Therefore, web/app results can vary greatly depending on the user even for the same question.
1. **Reasoning budget limits**: Ordinary user environments may have limited reasoning budgets, so they may show lower performance than this test.
2. **Output token limits**: Ordinary user environments may have maximum output token limits, so answers may be cut off for problems requiring long reasoning.
3. **No tool usage**: Ordinary user environments may use web search and other tools when needed, but this test answered using only the model's own knowledge.

Therefore, **performance may differ from official website or app results.**

### Evaluation Method
- Each LLM model was given problem text and asked to choose an answer.
- For short-answer questions, the model was required to enter the exact number.
- The final answer provided by the model was compared against the correct answer for grading.

### Problem Presentation Method
- **Text extraction**: PDF files were converted into text using OCR and similar methods.
- **Image handling**: Only images included in the problem, such as graphs, tables, and figures, were separately captured and provided.
- **Original preservation**: The PDF file itself or full-page screenshots were not provided.
- This was done so that the models would use only text understanding and visual-material interpretation abilities.
- **Normal Mode**: Every question in a section is solved in one request.
- **Easy Mode**: Each question is solved once in its own request.

---

## Tested Models

- **OpenAI GPT series**
  - GPT-6 Astra (high / low)
  - GPT-5.6 Sol Pro (high)
  - GPT-5.6 Sol (max* / high / none)
  - GPT-5.6 Terra Pro (high)
  - GPT-5.6 Terra (max* / high / none)
  - GPT-5.6 Luna Pro (high)
  - GPT-5.6 Luna (max* / high / low / none)
  - GPT-5.5 Pro (xhigh, GPTs)
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

- **Google Gemini series**
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

- **Google Gemma series**
  - Gemma 4 31B (high / minimal)
  - Gemma 4 26B A4B (high / minimal)

- **Anthropic Claude series**
  - Claude Fable 5.1 (high)
  - Claude Fable 5 (high)
  - Claude Opus 5 (high / none)
  - Claude Sonnet 5 (high / none)
  - Claude Opus 4.8 (high / none)
  - Claude Opus 4.7 (max* / high / none)
  - Claude Sonnet 4.6 (high / none)
  - Claude Opus 4.5 (32K Thinking / Non-Thinking)
  - Claude Sonnet 4.5 (32K Thinking / Non-Thinking)
  - Claude Haiku 4.5 (32K Thinking / Non-Thinking)

- **xAI Grok series**
  - Grok 4.5 (high)
  - Grok 4.3 (Thinking / Non-Thinking)
  - Grok 4.1 Fast (Thinking / Non-Thinking)
  - Grok 4 Fast (Thinking)
  - Grok 4

- **Meta Muse Spark series**
  - Muse Spark 1.3 (minimal / high)
  - Muse Spark 1.2 (minimal / high)

- **Mistral series**
  - Mistral Small 4 (Thinking / Non-Thinking)

- **DeepSeek series**
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

- **Moonshot AI Kimi series**
  - Kimi K2.6 (Thinking / Non-Thinking)
  - Kimi K2.5 (Thinking / Non-Thinking)

- **MiniMax series**
  - MiniMax M3 (Thinking / Non-Thinking)

- **Z.ai GLM series**
  - GLM-5.3 Flash (high)
  - GLM-5.2 (Thinking / Non-Thinking)
  - GLM-5.1 (Thinking / Non-Thinking)
  - GLM-5 (Thinking / Non-Thinking)

- **Alibaba Cloud Qwen series**
  - Qwen3.8 Max (xhigh)
  - Qwen3.7 Max (Thinking / Non-Thinking)
  - Qwen3.6 Plus (Thinking / Non-Thinking)
  - Qwen3.6 27B (Thinking / Non-Thinking)
  - Qwen3.5 397B (Thinking / Non-Thinking)
  - Qwen3.5 35B A3B (Thinking / Non-Thinking)
  - Qwen3.5 27B (Thinking / Non-Thinking)
  - Qwen3.5 9B (Thinking / Non-Thinking)

- **LGAI EXAONE series**
  - K-EXAONE 2.0 (Thinking / Non-Thinking)
  - K-EXAONE (Thinking / Non-Thinking)

- **Kakao Kanana series**
  - Kanana-o 9.8B

- **Upstage Solar series**
  - Solar Pro 4 (none / max)
  - Solar Pro 3 0126 (high / low)
  - Solar Pro 3 (high / low)

- **Motif series**
  - Motif 3 (Thinking)
  - Motif 12.7B (Thinking)

※ * GPT-5.x (xhigh) and Claude Opus 4.7 (max) were retested only on problems they missed at high. This approach was used because the time and cost became too large relative to the performance gain.

※ Models that cannot recognize images were run with text only.

---

## Korean Section

### Easy Mode (100 points)
![Korean easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_국어.png)

### Normal Mode (100 points)
![Korean normal mode](https://hehee9.github.io/CSAT-benchmark/images/국어.png)

---

## Math Section

### Easy Mode (100 points)
![Math easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_수학.png)

### Normal Mode (100 points)
![Math normal mode](https://hehee9.github.io/CSAT-benchmark/images/수학.png)

---

## English Section

### Easy Mode (100 points)
![English easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_영어.png)

### Normal Mode (100 points)
![English normal mode](https://hehee9.github.io/CSAT-benchmark/images/영어.png)

---

## Korean History Section

### Easy Mode (50 points)
![Korean History easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_한국사.png)

### Normal Mode (50 points)
![Korean History normal mode](https://hehee9.github.io/CSAT-benchmark/images/한국사.png)

---

## Inquiry Section

### Physics I

![Physics I easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_물리1.png)
![Physics I normal mode](https://hehee9.github.io/CSAT-benchmark/images/물리1.png)

> ※ The average score is low because many wrong answers occurred on questions containing visual materials with many lines or arrows.

### Chemistry I

![Chemistry I easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_화학1.png)
![Chemistry I normal mode](https://hehee9.github.io/CSAT-benchmark/images/화학1.png)

### Life Science I

![Life Science I easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_생명1.png)
![Life Science I normal mode](https://hehee9.github.io/CSAT-benchmark/images/생명1.png)

### Society & Culture

![Society & Culture easy mode](https://hehee9.github.io/CSAT-benchmark/images/쉬움_사회문화.png)
![Society & Culture normal mode](https://hehee9.github.io/CSAT-benchmark/images/사회문화.png)

---

## Cost Efficiency

This section analyzes the correlation between API cost (token usage) and score.

### Cost vs Performance

![Cost efficiency](https://hehee9.github.io/CSAT-benchmark/images/비용_분석.png)

For models without an official provider, the measurement is based on OpenRouter's average pricing.

| Model | Input Cost | Output Cost |
| :--- | :--- | :--- |
| GPT-OSS 120B | 0.15 | 0.6 |
| Gemma 4 31B | 0.14 | 0.4 |
| Gemma 4 26B A4B | 0.1 | 0.4 |

※ Prices are in USD per 1,000,000 tokens.

※ For models that do not yet have a paid API, similar-scale paid open-model API pricing was used as the basis.

### Token Usage

![Token usage](https://hehee9.github.io/CSAT-benchmark/images/토큰_사용량.png)

---

## Support

Tests for models other than GPT-5.5 Pro were conducted through actual APIs, and token usage and costs are transparently disclosed.

Since every subject is tested each time a new model is released, significant API costs are incurred. If you'd like to help maintain this project, please consider supporting via Ko-fi!

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/hehee9)

---

## Evaluation Targets in Detail

### 2026 Korean CSAT

- Korean: 34 common questions (76 points); Speech & Writing and Language & Media electives: 11 questions each (24 points each); 100 points total
- Math: 22 common questions (74 points); Probability & Statistics, Calculus, and Geometry electives: 8 questions each (26 points each); 100 points total
- English: 45 questions; listening replaced with a transcript (100 points)
- Korean History: 20 questions (50 points; mandatory section)
- Inquiry: Physics I, Chemistry I, Life Science I, and Society & Culture: 20 questions each (50 points each)

### 2027 Korean CSAT preparation
- The exam manifest is being prepared for Korean, Math, English, Korean History, and 17 inquiry subjects.
- Social studies: Economics, East Asian History, Society & Culture, Ethics and Life, World History, World Geography, Ethics and Thought, Politics and Law, Korean Geography
- Science studies: Physics I, Physics II, Chemistry I, Chemistry II, Life Science I, Life Science II, Earth Science I, Earth Science II
- Question files are not included yet. Once they are ready, the manifest's default Normal mode will be used.

## Detailed Evaluation Method

The problems were first extracted into text using OCR, and incorrectly extracted parts were manually corrected.

In Easy Mode, each problem was entered individually into the prompt with only the minimum required information.
In Easy Mode, when one passage had multiple linked questions, each input was structured as passage + individual question.

Formulas were converted to LaTeX to prevent the model from misunderstanding the formulas themselves. Recognizing text from images is also a performance metric, but I judged that wrong answers caused by misrecognizing the problem text did not fit the direction of this project.

Retries were performed only when no response was received due to an error. Other forms of incorrect responses were all treated as wrong answers.

### Example Input Prompts

- Case with a passage (Korean odd-form question 3):
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

- Case with formulas (Math odd-form question 15):
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

- Case with an image (Korean History odd-form question 2):
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

## License and Copyright

### Project License
This project is distributed under the MIT License. See the [LICENSE](LICENSE.md) file for details.

### CSAT Problem Copyright
- The 2026 Korean CSAT problems are copyrighted works of the **Korea Institute for Curriculum and Evaluation (KICE)**.
- This repository does not include the original problems. It includes only **model answer results and analysis data**.
- The Excel file includes only question numbers and correct answers. Full problem text is not provided due to copyright.
- If you want to use the CSAT problems, please use official materials from KICE.

---

* Contact: gyugyum@gmail.com
