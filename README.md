# llm-roundtable

Hội đồng AI ra quyết định cho mọi agentic coding tool. Fable 5.1, Opus 5.5, GPT (Codex, gpt-6.1-sol),
Grok 4.7, Gemini 3.8 Flash (Antigravity) và model free mới nhất của OpenCode đều thu thập bằng chứng,
chất vấn nhau ẩn danh, rồi bỏ phiếu có trọng số. Phương án có điểm cao nhất thắng; hoà thì Fable quyết.

- Skill: [`skills/llm-roundtable/SKILL.md`](skills/llm-roundtable/SKILL.md) (chuẩn Agent Skills; chạy từ Claude Code, Codex, Grok CLI, Antigravity, OpenCode, pi)
- Script: `skills/llm-roundtable/scripts/roundtable.py` (Python 3.9+, chỉ stdlib) + `seats.json`
- Giao thức và toán: [`references/protocol.md`](skills/llm-roundtable/references/protocol.md)
- Host, preset dùng một tool, Orca, cấu hình: [`references/hosts.md`](skills/llm-roundtable/references/hosts.md)
- Nghiên cứu (dự án tương tự, paper, lý do thiết kế): [`docs/research.md`](docs/research.md)

## Cài

```bash
npx skills add dinhkarate/llm-roundtable --skill llm-roundtable        # mọi agent trên máy
# hoặc thêm vào manifest pi-skill:  dinhkarate/llm-roundtable<TAB>llm-roundtable
```

## Dùng

```bash
S=skills/llm-roundtable/scripts/roundtable.py
python3 $S doctor --probe                       # ghế nào ngồi được, model nào còn quota
python3 $S run --brief brief.md                 # brief có mục "## Options" (- A: ..., - B: ...)
python3 $S run --brief plan.md --mode review --workspace .   # duyệt: APPROVE / CHANGES / REJECT
python3 $S run --brief q.md --seats duo         # chỉ Fable vs Opus
python3 $S status                               # tiến độ của lần chạy mới nhất
```

Kết quả ở `~/.roundtable/runs/<thời gian>-<slug>/decision.md` (+ `result.json`, transcript từng vòng).

## Luật

- Fallback xuống đúng một cấp cùng họ (fable 5, opus 5, gpt-6-sol, grok-4.6, gemini 3.7 flash, model free kế tiếp);
  hết cách thì ghế đó **UNATTENDED**.
- Phiếu không có bằng chứng FACT/INFERENCE thì không được tính. Trọng số = weight × (0.5 + 0.5 × điểm bằng chứng do các ghế khác chấm).
- Hoà → theo phiếu của Fable; Fable không nằm trong nhóm hoà → TIE, hỏi người dùng. Dưới 2 phiếu hợp lệ → NO QUORUM.

## Test

```bash
python3 -m unittest discover -s tests -v       # CLI giả, không tốn quota
```
