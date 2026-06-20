#!/bin/bash

set -e

PIPELINE_START=$(date +%s)

echo "🚀 Running full document pipeline..."
echo "   router → extract → clean → chunk → retrieve → ATS prompt"

# ✅ 1. Setup / ensure container is running
STAGE_START=$(date +%s)
./scripts/setup.sh
echo "⏱️  setup: $(($(date +%s) - STAGE_START))s"

# ✅ 2. Route + convert based on file type
#    pdf/  -> pdfplumber, fallback to MarkItDown if extraction is weak
#    docx/ -> MarkItDown
#    html/ -> MarkItDown
#    image/-> tesseract OCR
#    other/-> MarkItDown
STAGE_START=$(date +%s)
./scripts/router.sh
echo "⏱️  router: $(($(date +%s) - STAGE_START))s"

# ✅ 3. Clean extracted text (encoding, bullets, broken lines, headings)
STAGE_START=$(date +%s)
./scripts/clean.sh
echo "⏱️  clean: $(($(date +%s) - STAGE_START))s"

# ✅ 4. Smart chunking by heading (LLM-friendly chunks in chunks/)
STAGE_START=$(date +%s)
./scripts/smart_chunk.sh
echo "⏱️  smart_chunk: $(($(date +%s) - STAGE_START))s"

TOTAL=$(( $(date +%s) - PIPELINE_START ))
echo "✅ Pipeline complete! (total: ${TOTAL}s)"
echo ""
echo "👉 Next steps:"
echo "   General Q&A over the document:"
echo "     ./scripts/semantic_retrieve.sh \"your question\""
echo ""
echo "   ATS-style resume evaluation against a job description"
echo "   (scoring, gaps, recruiter verdict — facts-only, upload file to Claude.ai):"
echo "     ./scripts/ats_optimize.sh \"output/JD_filename.md\" \"output/YourResume.md\""
echo ""
echo "   Cover letter for a job description"
echo "   (facts-only, flags unaddressed JD requirements, upload file to Claude.ai):"
echo "     ./scripts/cover_letter.sh \"output/JD_filename.md\" \"output/YourResume.md\""
echo ""
echo "   Multiple resume variants? Use this workflow instead of ats_optimize.sh:"
echo "     1. ./scripts/variant_rank.sh \"<jd>\" \"output/resume\"   (fit gate + ranking)"
echo "     2. ./scripts/prepare_variant.sh \"output/resume/<chosen>.md\" \"output/<jd>.md\""
echo "     3. ./scripts/smart_chunk.sh"
echo "     4. rm -f chunks/<jd_basename>_part_*.md          # ← the manual step: drop JD chunks before Stage 2/3"
echo "     5. ./scripts/ats_optimize.sh \"<jd>\" \"output/<chosen>.md\""
echo "     6. ./scripts/ats_recommend.sh \"<jd>\" \"<variant_name>\""
echo "   NOTE: point these at output/*.md (post-clean), not input/*.txt —"
echo "   the input/ version hasn't had encoding/mojibake cleanup applied yet."
# ./scripts/cover_letter.sh "output/JD1.md" "output/Nanditha_Murthy_Resume.md"


echo "   Convert and md file to pdf"
#./scripts/md_to_pdf.sh "output/cover/JD1_cover.md"


#./scripts/variant_rank.sh  "output/JD1.md" "output/resume"


# computes cosine similarity between just two of your resumes and prints the raw value,
#
#docker exec markitdown python3 -c "
#from sentence_transformers import SentenceTransformer
#import numpy as np
#import re
#
#BOILERPLATE_HEADINGS = ['core competencies', 'technical stack', 'education', 'certifications', 'work authorization']
#HEADING_PATTERN = re.compile(r'^([A-Z][A-Z ]+)\$|^#{1,6}\s+(.+)\$')
#
#def extract_role_specific_sections(text):
#    lines = text.split('\n')
#    sections = []
#    current_heading = None
#    current_body = []
#    for line in lines:
#        stripped = line.strip()
#        match = HEADING_PATTERN.match(stripped) if stripped else None
#        if match:
#            if current_heading is not None:
#                sections.append((current_heading, current_body))
#            current_heading = (match.group(1) or match.group(2)).strip()
#            current_body = []
#        else:
#            current_body.append(line)
#    if current_heading is not None:
#        sections.append((current_heading, current_body))
#    if not sections:
#        return text
#    kept = []
#    for heading, body in sections:
#        if not any(b in heading.lower() for b in BOILERPLATE_HEADINGS):
#            kept.append(heading)
#            kept.extend(body)
#    result = '\n'.join(kept).strip()
#    return result if result else text
#
#model = SentenceTransformer('all-MiniLM-L6-v2')
#
#jd = open('/app/output/JD1.md', encoding='utf-8').read()
#r1_full = open('/app/output/resume/Nanditha_Murthy_Resume_PM_Oakville_RBC.md', encoding='utf-8').read()
#r2_full = open('/app/output/resume/Nanditha_Murthy_Resume_TPM_grow_therapy.md', encoding='utf-8').read()
#
#r1 = extract_role_specific_sections(r1_full)
#r2 = extract_role_specific_sections(r2_full)
#
#print('RBC: original', len(r1_full), 'chars -> filtered', len(r1), 'chars')
#print('Grow Therapy: original', len(r2_full), 'chars -> filtered', len(r2), 'chars')
#print()
#
#emb = model.encode([jd, r1, r2], normalize_embeddings=True)
#print('JD vs RBC (filtered):', np.dot(emb[0], emb[1]))
#print('JD vs Grow Therapy (filtered):', np.dot(emb[0], emb[2]))
#print('RBC vs Grow Therapy (filtered, resume-to-resume):', np.dot(emb[1], emb[2]))
#"
