# Nghiên cứu: hội đồng AI ra quyết định (roundtable)

Ngày: 2026-10-13 · Người làm: Claude (Opus 5.5) trong phiên Orca Claude

## 1. Đã có ai làm chưa?

Có. Ý tưởng "nhiều model cùng trả lời, chấm nhau, rồi tổng hợp/bỏ phiếu" là chủ đề rất đông người làm.
Không dự án nào khớp cùng lúc mọi yêu cầu của mình: subscription CLI thay vì API key, đủ 5 hãng,
fallback đúng một cấp rồi báo unattended, phiếu có trọng số dựa trên bằng chứng, hoà thì Fable quyết,
và chạy được từ bất kỳ agent nào.

| Dự án | Cách gọi model | Cơ chế | Khác/thiếu so với mình |
|---|---|---|---|
| karpathy/llm-council | OpenRouter API | trả lời → chấm ẩn danh (Response A/B) → Chairman tổng hợp | web app, cần API key; Chairman tổng hợp chứ không bỏ phiếu |
| 0xNyk/council-of-high-intelligence (~2.8k★, CC0) | subagent Claude + `codex exec`, `gemini -p`, ollama, cursor-agent | 18 "nhân vật", 3 vòng (phân tích độc lập → chất vấn → lập trường cuối), nhãn FACT/INFERENCE/ASSUMPTION, đếm phiếu có trọng số (v1.1) | gần nhất; nặng về persona, không fallback theo họ model, không có Grok/agy/OpenCode free, khi lỗi thì quay về host |
| Max-aiutopia/llm-council (MIT, mới) | `codex`, `agy`, `grok` (subscription) | hỏi song song trong thư mục rỗng, privacy gate, Claude viết quyết định | không có vòng phản biện, không bỏ phiếu; Claude tự phán |
| BeehiveInnovations zen/PAL MCP | API nhiều provider; `clink` gọi CLI khác | tool `consensus`, hội thoại nhiều model | là MCP server (phải cài vào từng host), không có luật phiếu/hoà |
| hex claude-council, xrf9268 llm-council-plugin, sherifkozman/llm-council, polyclaude, design-council, maestro, gavel, frahlg/fusion, openfusion | API hoặc CLI | song song + tổng hợp / debate theo vai / judge + synthesizer | phần lớn chỉ cho Claude Code; tổng hợp bằng judge, không bỏ phiếu theo bằng chứng |

Kết luận: **không cần fork**. Mượn ba ý đã được kiểm chứng (vòng đầu độc lập, chấm ẩn danh, nhãn bằng chứng)
và tự viết phần riêng: fallback một cấp, unattended, trọng số theo điểm bằng chứng do các thành viên
khác chấm, Fable phá hoà, chạy được trên mọi host.

## 2. Nghiên cứu nói gì về debate/vote

1. **Debate or Vote** (Choi, Zhu, Li, NeurIPS 2025): phần lớn lợi ích của multi-agent debate đến từ
   *bỏ phiếu đa số*; debate thuần không làm tăng xác suất đúng kỳ vọng (quá trình niềm tin là martingale).
   Can thiệp có chủ đích, đẩy cập nhật niềm tin về phía sửa sai, thì có ích.
   → Giữ vòng 1 độc lập + bỏ phiếu; chỉ 1 vòng chất vấn mặc định, và vòng đó buộc dựa trên bằng chứng
   ("số phiếu không phải bằng chứng; chỉ đổi phiếu khi một bằng chứng cụ thể buộc phải đổi").
2. **When Identity Skews Debate** (ACL 2026): trong debate có sycophancy (chiều theo bạn) và self-bias
   (bênh mình); ẩn danh câu trả lời làm giảm cả hai. → Vòng chất vấn gọi bằng M1..Mn, xáo thứ tự,
   phiên mới mỗi vòng nên model thật sự không biết đâu là câu của mình; điểm tự chấm bị bỏ.
3. **Đội cùng họ model** (CAIS 2026): dễ chạy theo số đông (đến 85.5% chấp nhận đáp án đa số),
   sụp về đồng thuận, tốn token gấp 2-3 lần tự sửa. → Mặc định mỗi họ model một ghế; preset "solo-*"
   có cảnh báo và khuyên thêm OpenCode để có hãng khác.
4. Karpathy kể các model trong llm-council thường khen GPT và chê Claude, và đôi khi lệch với đánh giá
   của chính ông. → Không cho một "chairman" model tự tổng hợp/phán quyết; phán quyết là phép tính
   trên phiếu, host chỉ tường thuật.

## 3. Thiết kế đã chọn

- **Một script Python thuần (stdlib, 3.9+) + SKILL.md chuẩn Agent Skills.** Host nào có shell
  (Claude Code, Codex, Grok CLI, Antigravity, OpenCode, pi) đều chạy được; không cần MCP, không cần Orca.
  Cài qua `npx skills` như các skill khác.
- **Mỗi ghế = một process CLI headless, read-only, phiên mới**, chạy trong thư mục rỗng (mặc định) hoặc
  đọc repo khi có `--workspace`. Adapter khai báo bằng JSON nên thêm CLI mới (qwen, cursor-agent, pi...)
  không phải sửa code.
- **Ghế mặc định**: fable `claude-fable-5-1`, opus `claude-opus-5-5`, codex `gpt-6.1-sol`, grok `grok-4.7`,
  gemini `gemini-3.8-flash-high` (qua agy), opencode = model free mới nhất khác họ với các ghế còn lại.
  6 ghế, số chẵn, nên luật "hoà thì Fable" có tác dụng thật.
- **Fallback một cấp**, rồi UNATTENDED (đúng yêu cầu). Fallback trùng primary của ghế khác bị bỏ.
- **Phiếu**: cần ít nhất một bằng chứng FACT/INFERENCE, nếu không thì phiếu không được tính.
  Trọng số = weight ghế × (0.5 + 0.5 × điểm bằng chứng trung bình do các ghế khác chấm, 0-2).
  Thắng = điểm có trọng số cao nhất; hoà → lựa chọn của Fable; Fable không nằm trong nhóm hoà → TIE, hỏi user.
  Dưới 2 phiếu hợp lệ → NO QUORUM. `decision_rule: "count"` để đổi sang đếm phiếu thuần.
- **An toàn**: chặn brief có dạng secret; `--private` bỏ ghế có thể train trên prompt (OpenCode free);
  `ROUNDTABLE_SEAT` chặn ghế tự mở hội đồng lồng nhau; host không được "sửa" kết quả.

## 4. Kiểm chứng trên máy này (2026-10-13)

`roundtable.py doctor --probe`:

| Ghế | Primary | Fallback |
|---|---|---|
| fable | claude-fable-5-1 ok | claude-fable-5 ok |
| opus | claude-opus-5-5 ok | claude-opus-5 ok |
| codex | gpt-6.1-sol ok | gpt-6-sol ok |
| grok | grok-4.7 ok | grok-4.6 ok |
| gemini (agy 1.3.4) | gemini-3.8-flash-high ok | gemini-3.7-flash-high **không có trong agy** → khi 3.8 hết quota, ghế này UNATTENDED |
| opencode | opencode/cat-jam-free ok (2026-10-12) | opencode/exo-free **đã deprecated** → đã tự ghi vào dead-models |

Ghi chú CLI rút ra khi thử:
- `opencode run` treo nếu stdin không đóng → script luôn đưa `/dev/null`.
- `agy --mode plan` ở chế độ print chờ duyệt plan rồi bị huỷ → dùng `--sandbox --disable-slash-commands`.
- `grok -p` bị lấy làm prompt nếu đứng trước cờ khác → dùng `--prompt-file`.
- models.dev trả 403 nếu không có User-Agent → script gửi UA và cache 1 ngày.
- grok-4.7 từ chối prompt kiểu "reply with exactly ..." → probe dùng câu hỏi thật.

## 5. Việc còn mở

- Orca transport: mỗi ghế là một terminal agent trong Orca (xem được TUI, chạy được ghế trên máy khác).
- Ghế remote (sanrokyu-chan, Windows) qua SSH: adapter `ssh host claude -p ...`.
- Thử luật `count` vs `weighted` trên một bộ câu hỏi có đáp án để chọn mặc định bằng số liệu.

## Nguồn

- [karpathy/llm-council](https://github.com/karpathy/llm-council) · [giải thích (Analytics Vidhya)](https://www.analyticsvidhya.com/blog/2025/12/llm-council-by-andrej-karpathy/)
- [0xNyk/council-of-high-intelligence](https://github.com/0xNyk/council-of-high-intelligence) · [bài giới thiệu](https://explainx.ai/blog/council-of-high-intelligence-multi-llm-deliberation-claude-code-2026)
- [Max-aiutopia/llm-council](https://github.com/Max-aiutopia/llm-council)
- [So sánh các plugin council cho Claude Code](https://www.claudepluginhub.com/blog/claude-council-plugins-compared)
- [Zen/PAL MCP server](https://mcpservers.org/de/servers/BeehiveInnovations/zen-mcp-server)
- [Debate or Vote (arXiv 2508.17536)](https://arxiv.org/abs/2508.17536v1) · [NeurIPS 2025](https://neurips.cc/virtual/2025/poster/116557)
- [When Identity Skews Debate (arXiv 2510.07517)](https://arxiv.org/abs/2510.07517) · [ACL 2026](https://preview.aclanthology.org/ingest-acl/2026.acl-long.650/)
- [Decomposing sycophancy … homogeneous multi-agent (CAIS 2026)](https://caisconf.org/program/2026/papers/decomposing-sycophancy-fragility-consensus-collapse-and-cost-in-homogeneous-mult/)
- [Debate diversity collapse (blog)](https://tianpan.co/blog/2026/04/26/debate-diversity-collapse-multi-agent-ensemble)
- [models.dev](https://models.dev) (ngày phát hành model OpenCode)
