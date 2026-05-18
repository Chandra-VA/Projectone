import os
import re
import json
import time
import base64
import requests
import fitz

# 加载固定配置
from config import *

PROGRESS_FILE = "auto_full_progress.json"

# ==================== 提示词：让模型同时输出【章节号+数学单元】 ====================
PROMPT = """
你是拓扑学数学专家，观察这张教材页面图片，完成：

1. 先判断：**当前页面内容属于全书第几章**，只给数字，例如 1、2、3……
2. 再提取页面中所有数学单元。

数学单元类型：
Definition / Theorem / Proposition / Lemma / Corollary / Example / Remark

输出严格为**单个JSON数组**，每条元素格式固定：
{
  "chapter": 章节数字(整数),
  "type": "单元类型",
  "number": "编号如1.1、2.3",
  "title": "标题，无则空字符串",
  "statement": "完整陈述",
  "proof": "完整证明，无则空字符串"
}

要求：
- 只输出纯JSON数组，不要任何解释、不要markdown代码块
- 识别准确数学符号、希腊字母、集合符号
- 没有单元输出空数组[]
"""

# ==================== 工具函数 ====================
def to_camel_case(s):
    if not s:
        return ""
    s = re.sub(r'[^a-zA-Z0-9\s]', '', s)
    words = s.split()
    return ''.join(w.capitalize() for w in words)

def generate_filename(unit):
    type_abbr = {
        'Definition':'Def','Theorem':'Thm','Proposition':'Prop',
        'Lemma':'Lem','Corollary':'Cor','Example':'Ex','Remark':'Rem'
    }
    abbr = type_abbr[unit["type"]]
    num = unit["number"].replace('.','_') if unit["number"] else ""
    title = to_camel_case(unit["title"])
    parts = [abbr]
    if num:
        parts.append(num)
    if title:
        parts.append(title)
    return '_'.join(parts)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_page": GLOBAL_START_PAGE, "units": []}

def save_progress(last_page, units):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_page": last_page, "units": units}, f, indent=2)

def pdf_page_to_base64(pdf_path, page_num):
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    pix = page.get_pixmap(matrix=fitz.Matrix(3,3))
    return base64.b64encode(pix.tobytes("png")).decode("utf-8")

def process_page(page_num):
    valid_types = {"Definition","Theorem","Proposition","Lemma","Corollary","Example","Remark"}
    for attempt in range(MAX_RETRIES):
        try:
            print(f"  转换第 {page_num+1} 页为图片...")
            img_b64 = pdf_page_to_base64(PDF_PATH, page_num)

            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": MODEL_NAME,
                "messages": [{
                    "role":"user",
                    "content":[
                        {"type":"image_url","image_url":{"url":f"data:image/png;base64,{img_b64}","detail":"high"}},
                        {"type":"text","text":PROMPT}
                    ]
                }],
                "temperature":0,
                "max_tokens":8192,
                "response_format":{"type":"json_object"}
            }

            resp = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers=headers, json=payload, timeout=300
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

            # 提取JSON数组
            try:
                data = json.loads(content)
                units = data if isinstance(data, list) else []
            except:
                l_idx = content.find('[')
                r_idx = content.rfind(']')+1
                units = json.loads(content[l_idx:r_idx]) if l_idx!=-1 else []

            # 过滤合法单元
            res = []
            for u in units:
                if not all(k in u for k in ["chapter","type","number","title","statement","proof"]):
                    continue
                if u["type"] not in valid_types:
                    continue
                if not isinstance(u["chapter"], int):
                    continue
                # 附加页码
                u["page_start"] = page_num + 1
                u["page_end"] = page_num + 1
                res.append(u)

            print(f"  ✅ 识别到 {len(res)} 个单元")
            return res

        except Exception as e:
            print(f"  第{attempt+1}次失败: {str(e)[:80]}")
            time.sleep(RETRY_DELAY)
    print("  ❌ 跳过本页")
    return []

def save_all_by_chapter(units):
    # 按章节分组
    chapter_groups = {}
    for u in units:
        ch = u["chapter"]
        if ch not in chapter_groups:
            chapter_groups[ch] = []
        chapter_groups[ch].append(u)

    # 逐章保存
    for ch_num, item_list in chapter_groups.items():
        ch_dir = os.path.join(OUTPUT_ROOT, "units", f"Ch{ch_num}")
        os.makedirs(ch_dir, exist_ok=True)

        # 按编号排序
        def sort_key(x):
            if x["number"] and "." in x["number"]:
                try:
                    a,b = x["number"].split(".")
                    return (int(a), int(b))
                except:
                    return (999,999)
            return (999,999)
        item_list.sort(key=sort_key)

        for unit in item_list:
            fname = generate_filename(unit)

            # 保存 MD
            md = f"# {unit['type']} {unit['number']}"
            if unit["title"]:
                md += f" ({unit['title']})"
            md += f"\n\n## Statement\n\n{unit['statement']}\n"
            if unit["proof"]:
                md += f"\n## Proof\n\n{unit['proof']}\n"
            with open(os.path.join(ch_dir, f"{fname}.md"), "w", encoding="utf-8") as f:
                f.write(md)

            # 保存 JSON
            json_data = {
                "id": f"{unit['type'][:3]}{unit['number']}" if unit["number"] else fname,
                "chapter": ch_num,
                "section": unit["number"],
                "type": unit["type"],
                "title": unit["title"],
                "page_start": unit["page_start"],
                "page_end": unit["page_end"],
                "depends_on_statement": [],
                "depends_on_proof": []
            }
            with open(os.path.join(ch_dir, f"{fname}.json"), "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

# ==================== 主程序 ====================
def main():
    print("="*60)
    print("  全书全自动提取器 · 无需手动改章节页码")
    print("="*60)
    print(f"PDF文件: {PDF_PATH}")
    print(f"从第 {GLOBAL_START_PAGE+1} 页自动跑到PDF最后一页")
    print(f"输出根目录: {OUTPUT_ROOT}/units/Ch1 Ch2 ...")
    print("="*60)

    # 加载进度
    progress = load_progress()
    last_page = progress["last_page"]
    all_units = progress["units"]
    print(f"\n✅ 已加载进度：上次停在第 {last_page+1} 页，累计 {len(all_units)} 个单元")

    # 打开PDF获取总页数
    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)
    print(f"\nPDF总页数: {total_pages}")

    # 逐页全自动往后跑
    for page_num in range(last_page, total_pages):
        print(f"\n处理第 {page_num+1}/{total_pages} 页...")
        units = process_page(page_num)
        all_units.extend(units)
        save_progress(page_num+1, all_units)
        print(f"  💾 进度已保存，累计单元数: {len(all_units)}")

    # 内容去重
    seen = set()
    unique = []
    for u in all_units:
        key = u["statement"][:120].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(u)
    print(f"\n✅ 去重后有效单元: {len(unique)} 个")

    # 自动按章节分目录保存
    save_all_by_chapter(unique)

    # 清理进度文件
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

    print("\n" + "="*60)
    print("🎉 全书全自动处理完成！")
    print("已自动按 Ch1 Ch2 Ch3 … 分文件夹存放")
    print("所有文件格式严格遵循你指定的标准")
    print("="*60)

if __name__ == "__main__":
    main()