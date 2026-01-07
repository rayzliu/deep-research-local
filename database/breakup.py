
import os
import pandas as pd
from openai import OpenAI

# ========= 配置 =========
CSV_PATH = "embed_errors.csv"
PASSAGES_DIR = "passages"
OUTPUT_DIR = "shortened_draft"

MODEL = "gpt-4.1-mini"
MAX_CHARS = 5600

os.makedirs(OUTPUT_DIR, exist_ok=True)

# client = OpenAI()


client = OpenAI(
	api_key=os.getenv("OPENAI_API_KEY"),
	base_url="https://api.chatanywhere.tech/v1"
)

def shorten_with_gpt_raw(text: str) -> str:
    """
    不做任何结构假设
    GPT 输出什么，就原样返回什么
    """

    system_prompt = f"""
你是一个专业的中文编辑与内容压缩专家。

任务要求（请严格遵守）：
1. 输入是一整篇文章，不要按自然段、句子等方式机械切割。
2. 尽量将全文压缩到 {MAX_CHARS} 字以内。
3. 如果在保证内容完整、逻辑紧凑的情况下无法压缩到 {MAX_CHARS} 字以内：
   - 请将文章拆分成多篇
   - 每一篇都必须是逻辑完整、内容紧凑的文章
   - 每一篇长度 ≤ {MAX_CHARS} 字
4. 如果拆分成多篇，请使用如下格式清晰标注：

=== ARTICLE 1 ===
文章内容……

=== ARTICLE 2 ===
文章内容……

5. 除文章内容和 ARTICLE 分隔标记外，不要输出任何解释性文字。
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()


def main():
    df = pd.read_csv(CSV_PATH)

    if "filename" not in df.columns:
        raise ValueError("CSV 中必须包含 filename 列")

    for filename in df["filename"]:
        input_path = os.path.join(PASSAGES_DIR, filename)

        if not os.path.exists(input_path):
            print(f"文件不存在，跳过: {filename}")
            continue

        with open(input_path, "r", encoding="utf-8") as f:
            original_text = f.read().strip()

        if not original_text:
            print(f"文件为空，跳过: {filename}")
            continue

        print(f"处理中: {filename}")

        result_text = shorten_with_gpt_raw(original_text)

        output_path = os.path.join(OUTPUT_DIR, filename)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result_text)

        print(f"已输出草稿: {output_path}")


if __name__ == "__main__":
    main()
