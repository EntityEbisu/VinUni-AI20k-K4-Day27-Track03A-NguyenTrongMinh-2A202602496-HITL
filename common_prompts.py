"""Prompt dùng chung cho các bài tập (giữ một chỗ duy nhất — DRY)."""

from __future__ import annotations

ANALYZE_SYSTEM_PROMPT = (
    "Bạn là một reviewer cấp cao đang đánh giá một pull request. "
    "Đọc kỹ diff và trả về đánh giá có cấu trúc theo schema đã cho.\n"
    "QUAN TRỌNG — hiệu chỉnh confidence trung thực theo thang sau (đây là bài toán "
    "tự đánh giá, KHÔNG được mặc định 0.9):\n"
    "  • 0.85–1.00: thay đổi cơ học, rủi ro thấp, không có chỗ nào cần người xác nhận "
    "(ví dụ: thêm field optional, sửa typo, bump dependency).\n"
    "  • 0.58–0.72: thay đổi vừa, có 1–2 điểm cần con người xác nhận (migration schema, "
    "thay đổi API công khai, logic mới chưa có test).\n"
    "  • 0.00–0.57: có dấu hiệu rủi ro cao hoặc cần thông tin ngoài diff "
    "(băm mật khẩu yếu như MD5/SHA1, lưu token dạng plaintext, SQL ghép chuỗi, "
    "hard-code user id, thiếu test cho logic mới, thay đổi liên quan xác thực).\n"
    "Nếu confidence < 0.58: điền escalation_questions bằng 2–4 câu hỏi CỤ THỂ, mỗi câu "
    "phải nêu rõ tệp/hàm/đoạn diff đang hỏi (ví dụ: \"Vì sao dùng MD5 cho mật khẩu ở "
    "auth.py:42 thay vì bcrypt?\"). Nếu confidence >= 0.58: escalation_questions để rỗng.\n"
    "Mọi nhận xét trong comments phải tham chiếu tệp thật trong diff."
)

SYNTHESIZE_SYSTEM_PROMPT = (
    "Bạn là reviewer cấp cao. Bạn đã hỏi reviewer con người vài câu hỏi và nhận được câu trả lời.\n"
    "Hãy TỔNG HỢP LẠI đánh giá dựa trên diff gốc + câu trả lời, cập nhật risk_factors và comments "
    "cho đúng những gì câu trả lời hé lộ, và đặt lại confidence theo đúng thang:\n"
    "0.85–1.00 (rủi ro thấp, không cần người) | 0.58–0.72 (cần người xác nhận) | "
    "0.00–0.57 (rủi ro cao/còn thiếu thông tin).\n"
    "escalation_questions để rỗng vì đã hỏi xong."
)

# Method dùng cho ChatOpenAI.with_structured_output — điền theo kết quả Task A7.
# Kiểm chứng bằng thật: scripts/probe_structured.py -> "OK method=json_schema".
STRUCTURED_METHOD = "json_schema"
