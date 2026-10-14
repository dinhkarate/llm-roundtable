<p align="center">
  <img src="assets/banner.svg" alt="llm-roundtable: hội đồng AI nhiều hãng tranh luận và bỏ phiếu thay bạn" width="100%">
</p>

<h1 align="center">llm-roundtable</h1>

<p align="center">
  <b>Hội đồng AI ra quyết định cho coding agent khi bạn vắng mặt.</b><br>
  Fable, Opus, GPT (Codex), Grok, Gemini và một model free của OpenCode thu thập bằng chứng,
  chất vấn nhau ẩn danh rồi bỏ phiếu có trọng số.
</p>

<p align="center"><a href="README.md">English</a> · <a href="docs/research.vi.md">Nghiên cứu</a></p>

---

Agent chạy qua đêm (`/loop`, Orca worker, bot CI) hay bị kẹt ở câu *"chọn A hay B?"*, *"plan này ổn chưa?"*,
*"merge diff này được không?"*. Thay vì dừng lại chờ bạn, agent triệu tập hội đồng gồm model của **năm hãng**,
làm theo phán quyết và để lại vết (PR, issue, commit) cho bạn đọc sau.

- **Dùng subscription sẵn có**: gọi CLI `claude`, `codex`, `grok`, `agy`, `opencode`. Không cần API key, không cần MCP.
- **Không có bằng chứng thì phiếu không được tính**: phải có ít nhất một `FACT`/`INFERENCE` có nguồn; các ghế khác chấm bằng chứng 0-2, điểm này nhân vào trọng số.
- **Chất vấn ẩn danh**: vòng 2 thấy lập trường dưới tên M1..Mn, xáo thứ tự, phiên mới, nên không model nào nhận ra câu của mình.
- **An toàn**: ghế chỉ đọc (sandbox kernel hoặc allowlist), tắt tool đăng ra ngoài, bỏ credential không liên quan, so workspace trước/sau.
- **Không bao giờ treo**: fallback đúng một cấp rồi UNATTENDED; hoà thì Fable quyết; không quyết được thì lấy `--default` an toàn.
- **Chạy ở mọi nơi có shell**: Claude Code, Codex CLI, Grok CLI, Antigravity, OpenCode, pi. Python 3.9+ chỉ dùng stdlib.

## Cài

```bash
npx skills add dinhkarate/llm-roundtable --skill llm-roundtable   # skill cho mọi agent trên máy
npx llm-roundtable doctor --probe                                 # ghế nào ngồi được, model nào còn quota
```

## Dùng

```bash
npx llm-roundtable run --brief brief.md --default C               # brief có mục "## Options" (- A: ..., - B: ...)
npx llm-roundtable run --brief plan.md --mode review --workspace . # duyệt: APPROVE / CHANGES / REJECT
npx llm-roundtable run --brief q.md --seats duo                   # chỉ Fable vs Opus
npx llm-roundtable status                                         # tiến độ lần chạy mới nhất
```

Kết quả ở `~/.roundtable/runs/<thời gian>-<slug>/decision.md` (+ `result.json`, transcript từng vòng).
Dòng cuối luôn là `VERDICT: <option|NONE> (council|tiebreak|default|none)`.

Trong agent bạn không cần gõ lệnh: skill [`SKILL.md`](skills/llm-roundtable/SKILL.md) hướng dẫn agent tự viết brief,
chạy nền, theo dõi và làm theo phán quyết. Gọi tay bằng `/llm-roundtable`, "hội bàn tròn", "hội đồng".

## Luật

- Fallback xuống đúng một cấp cùng họ (fable 5, opus 5, gpt-6-sol, grok-4.6, gemini 3.7 flash, model free kế tiếp); hết cách thì ghế đó **UNATTENDED**.
- Trọng số = weight × (0.5 + 0.5 × điểm bằng chứng trung bình do các ghế khác chấm, 0-2). Điểm tự chấm bị bỏ.
- Hoà → theo phiếu của Fable; Fable không nằm trong nhóm hoà → TIE. Dưới 2 phiếu hợp lệ → NO QUORUM. TIE/NO QUORUM → lấy `--default`.
- Hội đồng chỉ chọn giữa các việc agent đã được phép làm; không bao giờ cấp quyền push, deploy, xoá dữ liệu hay tiêu tiền.

Chi tiết: [`protocol.md`](skills/llm-roundtable/references/protocol.md), [`hosts.md`](skills/llm-roundtable/references/hosts.md),
[nghiên cứu](docs/research.vi.md).

## Test

```bash
python3 -m unittest discover -s tests -v   # CLI giả, không tốn quota
```

[MIT](LICENSE) © dinhkarate. Thấy hữu ích thì cho repo một ⭐ nhé.
