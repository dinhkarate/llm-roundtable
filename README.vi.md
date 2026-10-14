<p align="center">
  <img src="assets/banner.svg" alt="llm-roundtable: hội đồng AI nhiều hãng tranh luận và bỏ phiếu thay bạn" width="100%">
</p>

<h1 align="center">llm-roundtable</h1>

<p align="center">
  <b>Hội đồng AI ra quyết định cho coding agent khi bạn vắng mặt.</b><br>
  Fable, Opus, GPT (Codex), Grok, Gemini (thêm một model free của OpenCode nếu bật) thu thập bằng chứng,
  chất vấn nhau ẩn danh rồi bỏ phiếu có trọng số.
</p>

<p align="center"><a href="README.md">English</a> · <a href="docs/research.vi.md">Nghiên cứu</a></p>

<p align="center"><a href="assets/demo.mp4"><img src="assets/demo.gif" alt="Demo llm-roundtable" width="100%"></a></p>

---

Agent chạy qua đêm (`/loop`, Orca worker, bot CI) hay bị kẹt ở câu *"chọn A hay B?"*, *"plan này ổn chưa?"*,
*"merge diff này được không?"*. Thay vì dừng lại chờ bạn, agent triệu tập hội đồng gồm model của **bốn hãng** (năm nếu bật ghế OpenCode),
làm theo phán quyết và để lại vết (PR, issue, commit) cho bạn đọc sau.

- **Dùng subscription sẵn có**: gọi CLI `claude`, `codex`, `grok`, `agy`, `opencode`. Không cần API key, không cần MCP.
- **Không có bằng chứng thì phiếu không được tính**: phải có ít nhất một `FACT`/`INFERENCE` có nguồn; các ghế khác chấm bằng chứng 0-2, điểm này nhân vào trọng số.
- **Chất vấn ẩn danh**: vòng 2 thấy lập trường dưới tên M1..Mn, xáo thứ tự, phiên mới, nên không model nào nhận ra câu của mình.
- **An toàn**: các ghế mặc định chỉ đọc (sandbox kernel, allowlist hoặc bản sao workspace), tắt tool đăng ra ngoài, mỗi ghế chỉ nhận credential của chính CLI mình, so workspace (cả file gitignored như `.env`, trừ node_modules/target/cache) sau mỗi vòng; ghế claude không nhận hook hay memory của bạn (`--restricted`, cần Claude Code ≥ 2.1.248). Ghế OpenCode **không có sandbox** (service nền của nó chạy được lệnh shell bất kỳ đâu) nên mặc định tắt; bật bằng `--seats full-open` hoặc preset `solo-*`, `--private` sẽ bỏ nó.
- **Khó bị dắt mũi**: file và câu trả lời của ghế khác chỉ là dữ liệu: lập trường vòng 2 nằm trong rào có nonce riêng mỗi prompt, ghế báo lại chỗ có prompt injection, và trích `file:line` không có trong repo thì không còn được tính là FACT.
- **Đo được**: mỗi lần chạy ghi số lần gọi CLI, thời gian và số token từng CLI dùng.
- **Không bao giờ treo**: fallback đúng một cấp rồi UNATTENDED; hoà thì Fable quyết; không quyết được thì lấy `--default` an toàn.
- **Chạy ở mọi nơi có shell**: Claude Code, Codex CLI, Grok CLI, Antigravity, OpenCode, pi. Python 3.9+ chỉ dùng stdlib.

## Cài

```bash
npx skills add dinhkarate/llm-roundtable --skill llm-roundtable   # skill cho mọi agent trên máy
npx llm-roundtable doctor --probe                                 # ghế nào ngồi được, model nào còn quota
# Chỉ dùng Claude Code: cài dạng plugin (chọn cách này hoặc npx skills, đừng cả hai)
#   /plugin marketplace add dinhkarate/llm-roundtable
#   /plugin install llm-roundtable@llm-roundtable
```

## Dùng

```bash
npx llm-roundtable run --brief brief.md --default C               # brief có mục "## Options" (- A: ..., - B: ...)
npx llm-roundtable run --brief plan.md --mode review --workspace . # duyệt: APPROVE / CHANGES / REJECT
npx llm-roundtable run --brief q.md --seats duo                   # chỉ Fable vs Opus
npx llm-roundtable run --brief brief.md --default C --dry-run     # kiểm tra trước: ghế, quorum, giới hạn số lần gọi/thời gian (JSON), không gọi model
npx llm-roundtable status                                         # tiến độ lần chạy mới nhất
npx llm-roundtable status --json <thư-mục-run>                     # trạng thái, phán quyết và các cờ dạng JSON cho agent
npx llm-roundtable run --brief brief.md --default C --early-stop  # vòng 1 nhất trí (≥3 phiếu hợp lệ, ≥2 hãng) thì bỏ vòng chất vấn
npx llm-roundtable outcome <thư-mục-run> right --note "..."      # ghi lại sau này: quyết định đó đúng/sai (right|wrong|mixed|unknown)
npx llm-roundtable ledger                                         # tổng hợp mọi lần chạy: kết quả, dữ liệu early-stop, token trung vị
```

Brief mẫu để chép: [`references/briefs/`](skills/llm-roundtable/references/briefs/) (chọn công nghệ, migration, nâng
dependency, ship hay hoãn, review PR).

Kết quả ở `~/.roundtable/runs/<thời gian>-<slug>/decision.md` (+ `result.json`, transcript từng vòng).
Dòng cuối luôn là `VERDICT: <option|NONE> (council|tiebreak|default|none|workspace_changed)`.

Trong agent bạn không cần gõ lệnh: skill [`SKILL.md`](skills/llm-roundtable/SKILL.md) hướng dẫn agent tự viết brief,
chạy nền, theo dõi và làm theo phán quyết. Gọi tay bằng `/llm-roundtable`, "hội bàn tròn", "hội đồng".

## Luật

- Fallback xuống đúng một cấp cùng họ (fable 5, opus 5, gpt-6-sol, grok-4.6, gemini 3.7 flash, model free kế tiếp); hết cách thì ghế đó **UNATTENDED**.
- Trọng số = weight × (0.5 + 0.5 × điểm bằng chứng trung bình do các ghế khác chấm, 0-2). Điểm tự chấm bị bỏ.
- Hoà → theo phiếu của Fable; Fable không nằm trong nhóm hoà → TIE. Dưới 2 phiếu hợp lệ → NO QUORUM. TIE/NO QUORUM → lấy `--default`.
- `--min-margin 2/3` (tuỳ chọn): phương án thắng chiếm dưới tỉ lệ đó của tổng trọng số hợp lệ thì coi như hoà và lấy `--default`; lựa chọn của hội đồng vẫn được ghi ở `council_verdict`. `0.67` loại kết quả 4-2 trên sáu ghế, `2/3` thì giữ.
- `UNKNOWN` là câu hỏi còn bỏ ngỏ, không bao giờ được tính là bằng chứng; `decision.md` liệt kê chúng ở "Unresolved questions", cùng "Kill criteria" (dấu hiệu cần xem lại quyết định) của phía thắng.
- Vòng 1 mỗi ghế nhắc lại câu hỏi và có thể nêu một phương án bị bỏ sót; từ max(2, nửa số ghế hợp lệ) trở lên thì có cảnh báo "framing concern", chỉ để tham khảo, không đổi phiếu.
- `decision.md` có mục "Usage": số lần gọi CLI, nudge, fallback, thời gian từng vòng và token từng ghế (theo số CLI tự báo). `--deadline` giới hạn thời gian cả lần chạy.
- Giới hạn cấp tài khoản (Claude hết session/weekly limit, tài khoản bị khoá) thì không fallback: cùng tài khoản thì model khác cũng hỏng y vậy.
- `--early-stop` (tuỳ chọn, mặc định tắt): vòng 1 nhất trí, đủ ≥ max(quorum, 3) phiếu hợp lệ từ ≥ 2 CLI khác hãng, không có framing concern hay báo injection thì bỏ vòng 2. Không bao giờ áp dụng cho chế độ review.
- Hội đồng chỉ chọn giữa các việc agent đã được phép làm; không bao giờ cấp quyền push, deploy, xoá dữ liệu hay tiêu tiền.

Chi tiết: [`protocol.md`](skills/llm-roundtable/references/protocol.md), [`hosts.md`](skills/llm-roundtable/references/hosts.md),
[nghiên cứu](docs/research.vi.md).

## Test

```bash
python3 -m unittest discover -s tests -v   # CLI giả, không tốn quota
```

[MIT](LICENSE) © dinhkarate. Thấy hữu ích thì cho repo một ⭐ nhé.
