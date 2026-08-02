import os
import re
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
    system_prompt = (
        "You are a professional software documentation translator. "
        "Translate the input Chinese GitHub Markdown documentation into accurate, clean English.\n"
        "Rules:\n"
        "1. Translate everything, including auto-generated changelog entries (e.g., '更新了 1 个模型文件' -> 'updated 1 model file').\n"
        "2. Keep all Markdown structure, Markdown tags, HTML elements, and URLs intact.\n"
        "3. Do NOT translate file paths (models/0000), file extensions (.ysm), author IDs (#0001), or repository links."
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

def process():
    if not os.path.isfile(ZH_README):
        print(f"Error: {ZH_README} not found.")
        exit(1)

    with open(ZH_README, "r", encoding="utf-8") as f:
        zh_content = f.read()

    en_authors_block = ""
    if os.path.isfile(EN_README):
        with open(EN_README, "r", encoding="utf-8") as f:
            en_content = f.read()
        if AUTHORS_START in en_content and AUTHORS_END in en_content:
            en_authors_block = AUTHORS_START + en_content.split(AUTHORS_START, 1)[1].split(AUTHORS_END, 1)[0] + AUTHORS_END

    trans_target = zh_content
    if AUTHORS_START in trans_target and AUTHORS_END in trans_target:
        trans_target = re.sub(
            f"{AUTHORS_START}.*?{AUTHORS_END}", 
            "__AUTHORS_LIST_PLACEHOLDER__", 
            trans_target, 
            flags=re.DOTALL
        )

    print("Translating full README (including changelogs) to English via LLM...")
    translated_text = call_llm_translate(trans_target)

    if "__AUTHORS_LIST_PLACEHOLDER__" in translated_text:
        translated_text = translated_text.replace("__AUTHORS_LIST_PLACEHOLDER__", en_authors_block)

    with open(EN_README, "w", encoding="utf-8") as f:
        f.write(translated_text)

    print("Translation complete.")

if __name__ == "__main__":
    process()