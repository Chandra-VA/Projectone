# 数学PDF全自动单元提取 Skill

## 功能概述
基于通义千问多模态大模型，直接解析**扫描版图片PDF**，无需依赖OCR文本。
全程**全自动无人工干预**，不用手动改章节、不用手动配置页码：

- 自动逐页遍历整本PDF
- AI 智能识别每页内容所属章节
- 自动按 Ch1 / Ch2 / Ch3 … 建立文件夹分类存放
- 自动提取标准数学单元：定义、定理、命题、引理、推论、例题、备注
- 固定统一输出格式：结构化 Markdown + 标准 JSON 元数据
- 支持断点续传，中途关闭下次可继续运行
- 自动内容去重，避免重复生成单元
- 智能纠正数学符号、希腊字母、公式识别误差

## 工程结构
skill_pdf_math_extract/
```
├── README.md
├── config.py
├── auto_full_extractor.py
├── requirements.txt
└── .gitignore
```
## 运行方式
```bash
python auto_full_extractor.py