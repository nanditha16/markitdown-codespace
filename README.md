# MarkItDown Codespace

## Under the hood
This project uses Microsoft's MarkItDown:
https://github.com/microsoft/markitdown

Installed via:
pip install "markitdown[all]"

## A document ingestion micro-pipeline:
Step 1. Installed the official package: markitdown[all]
    - MarkItDown core engine (conversion)
    
Step 2. A thin orchestration layer over the official tool
    - Wrapped it with: 
        Reproducible environment (Docker)
        Isolation (safe processing)
        Automation (scripts)
            router:
                input/
                ├── pdf/   [pdfplumber → if weak → fallback to MarkItDown]
                ├── docx/  [MarkItDown directly]
                ├── html/  [MarkItDown directly]
                ├── image/ [tesseract OCR → output markdown/text]
                ├── other/ [MarkItDown directly]
            cleaning: 
                UTF-8 decoding + ligature corruption 
                character-level corruption
                symbols (Replace bullets and weird chars)
            NOTE: Using OCR approach (As PDF text extraction relies on embedded fonts (often broken))
                OCR: reads the visual PDF like an image
                enable OCR pipeline
                
            Agent-friendly usage:
                Chunking large Markdown files (LLM-friendly - by headings)
                Ask across all chunks
                Copy-to-prompt helper (paste-ready for Claude/Copilot)
                
    - workflow:
        PDF → Markdown 
        Markdown → LLM-friendly chunks 
        Prompt-ready output
        Copy-to-clipboard 
        
Step 3. Validation
    - PDF text → structured markdown 
    - Headings preserved
    
## 🚀
