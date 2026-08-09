import os
import re
import difflib
from openai import OpenAI

ZH_README = "README.md"
EN_README = "README-EN.md"

AUTHORS_START = "<!-- AUTHORS_LIST_START -->"
AUTHORS_END = "<!-- AUTHORS_LIST_END -->"

api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")

if not api_key:
    print("Warning: No API key provided. Skipping AI translation step.")
    exit(0)

client = OpenAI(api_key=api_key, base_url=base_url)

def call_llm_translate(text):
    """仅翻译有变动的中文段落"""
    system_prompt = (
        "You are a professional software documentation translator. "
        "Translate the input Chinese text into natural and clear English for a GitHub Markdown document.\n"
        "Rules:\n"
        "1. Keep all Markdown structure, HTML details elements, and URLs intact.\n"
        "2. Do NOT translate file paths (Models/0000), file extensions (.ysm), author IDs (#0001), or repository links.\n"
        "3. Translate commit/changelog descriptions naturally (e.g., '更新了 1 个模型文件' -> 'updated 1 model file')."
    )
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

def extract_non_header_body(content):
    """去除首行的语言跳转链接，只获取正文内容"""
    lines = content.splitlines()
    if lines and ("[中文]" in lines[0] or "[English]" in lines[0]):
        return "\n".join(lines[1:]).lstrip()
    return content

def process():
    if not os.path.isfile(ZH_README):
        print(f"Error: {ZH_README} not found.")
        exit(1)

    with open(ZH_README, "r", encoding="utf-8") as f:
        zh_full = f.read()

    en_full = ""
    if os.path.isfile(EN_README):
        with open(EN_README, "r", encoding="utf-8") as f:
            en_full = f.read()

    # 1. 提取英文版首行的语言切换链接（保护头部不被篡改）
    en_lines = en_full.splitlines()
    header_line = en_lines[0] if (en_lines and "[中文]" in en_lines[0]) else '[中文](https://github.com/nekohalawrence/YSM-Model-Author/blob/main/README.md), English'

    # 2. 提取并保留英文版的 AUTHORS_LIST 自动化区域
    en_authors_block = ""
    if AUTHORS_START in en_full and AUTHORS_END in en_full:
        en_authors_block = AUTHORS_START + en_full.split(AUTHORS_START, 1)[1].split(AUTHORS_END, 1)[0] + AUTHORS_END

    # 3. 对中文文档剔除 AUTHORS_LIST（替换为占位符），准备检测增量
    zh_body = extract_non_header_body(zh_full)
    
    if AUTHORS_START in zh_body and AUTHORS_END in zh_body:
        zh_body = re.sub(
            f"{AUTHORS_START}.*?{AUTHORS_END}", 
            "__AUTHORS_LIST_PLACEHOLDER__", 
            zh_body, 
            flags=re.DOTALL
        )

    # 4. 判断是否有需要增量翻译的内容
    # 获取英文正文（去除头部和 AUTHORS_LIST 占位符后）
    en_body_clean = extract_non_header_body(en_full)
    if AUTHORS_START in en_body_clean and AUTHORS_END in en_body_clean:
        en_body_clean = re.sub(
            f"{AUTHORS_START}.*?{AUTHORS_END}", 
            "__AUTHORS_LIST_PLACEHOLDER__", 
            en_body_clean, 
            flags=re.DOTALL
        )

    # 如果除开自动生成区域外，主体没有任何变化，则直接跳过翻译 API 调用
    if zh_body.strip() == en_body_clean.strip():
        print("No changes detected in README.md content. Skipping translation.")
        return

    print("Changes detected in README.md. Performing AI translation...")

    # 5. 调用 AI 对更新后的正文进行整体翻译
    translated_body = call_llm_translate(zh_body)

    # 6. 还原 AUTHORS_LIST 自动生成的英文表格数据
    if "__AUTHORS_LIST_PLACEHOLDER__" in translated_body:
        translated_body = translated_body.replace("__AUTHORS_LIST_PLACEHOLDER__", en_authors_block)

    # 7. 重新组装文档：保留头部跳转 + 翻译后的正文
    final_en_content = f"{header_line}\n\n{translated_body.strip()}\n"

    with open(EN_README, "w", encoding="utf-8") as f:
        f.write(final_en_content)

    print("README-EN.md successfully updated with translated changes.")

if __name__ == "__main__":
    process()