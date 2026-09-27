import re
import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def set_table_borders(table, color="D1D5DB", sz="4", val="single"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def add_styled_paragraph(doc, text, style='Normal', space_after=6, space_before=0, line_spacing=1.15):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.line_spacing = line_spacing
    
    # Process inline formatting: bold, italic, inline code
    # Regex splits by bold (**), code (`), italic (*)
    tokens = re.split(r'(\*\*.*?\*\*|`.*?`|\*.*?\*)', text)
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**'):
            run = p.add_run(token[2:-2])
            run.bold = True
            run.font.name = 'Calibri'
        elif token.startswith('`') and token.endswith('`'):
            run = p.add_run(token[1:-1])
            run.font.name = 'Consolas'
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(16, 75, 140)
        elif token.startswith('*') and token.endswith('*') and len(token) > 2:
            run = p.add_run(token[1:-1])
            run.italic = True
            run.font.name = 'Calibri'
        else:
            run = p.add_run(token)
            run.font.name = 'Calibri'
    return p

def create_callout_box(doc, text, title="NOTE"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.cell(0, 0)
    cell.width = Inches(6.5)
    
    set_cell_background(cell, "F0F4F8")
    set_cell_margins(cell, top=140, bottom=140, left=200, right=140)
    
    # Left border only (Navy thick)
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="1E3A8A"/>'
        f'<w:top w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run_title = p.add_run(f"📌 {title}: ")
    run_title.bold = True
    run_title.font.name = 'Calibri'
    run_title.font.color.rgb = RGBColor(30, 58, 138)
    
    # Add body text
    tokens = re.split(r'(\*\*.*?\*\*|`.*?`|\*.*?\*)', text)
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**'):
            r = p.add_run(token[2:-2])
            r.bold = True
        elif token.startswith('`') and token.endswith('`'):
            r = p.add_run(token[1:-1])
            r.font.name = 'Consolas'
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(16, 75, 140)
        else:
            p.add_run(token)
    
    # Space after table
    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(6)

def build_docx(md_path, docx_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    doc = Document()
    
    # Page setup: Standard Letter, 1 inch margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
        # Add page numbering in footer
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        frun = fp.add_run("Samsung Innovation Campus • SIC AI Capstone Project — Loop Gain")
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = RGBColor(128, 128, 128)

    i = 0
    n = len(lines)
    
    in_code_block = False
    code_lines = []
    
    in_table = False
    table_rows = []
    
    while i < n:
        raw_line = lines[i]
        line = raw_line.strip()
        
        # 1. Code blocks (```)
        if line.startswith('```'):
            if not in_code_block:
                in_code_block = True
                code_lines = []
            else:
                in_code_block = False
                # Emit code table
                tbl = doc.add_table(rows=1, cols=1)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                cell = tbl.cell(0, 0)
                cell.width = Inches(6.5)
                set_cell_background(cell, "F8FAFC")
                set_cell_margins(cell, top=120, bottom=120, left=160, right=160)
                
                # Light border
                tcPr = cell._tc.get_or_add_tcPr()
                borders = parse_xml(
                    f'<w:tcBorders {nsdecls("w")}>'
                    f'<w:left w:val="single" w:sz="12" w:space="0" w:color="6366F1"/>'
                    f'<w:top w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                    f'<w:right w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                    f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                    f'</w:tcBorders>'
                )
                tcPr.append(borders)
                
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.05
                run = p.add_run("\n".join(code_lines))
                run.font.name = 'Consolas'
                run.font.size = Pt(8.5)
                run.font.color.rgb = RGBColor(30, 41, 59)
                
                sp = doc.add_paragraph()
                sp.paragraph_format.space_after = Pt(6)
            i += 1
            continue
            
        if in_code_block:
            code_lines.append(raw_line.rstrip('\r\n'))
            i += 1
            continue
            
        # 2. Markdown Tables (| col1 | col2 |)
        if line.startswith('|') and '|' in line[1:]:
            # Check if separator row
            if re.match(r'^\|[\s\-:|]+\|$', line):
                i += 1
                continue
            
            # Collect row cells
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not in_table:
                in_table = True
                table_rows = [cells]
            else:
                table_rows.append(cells)
            i += 1
            continue
        else:
            if in_table:
                # Flush table to document
                in_table = False
                if table_rows:
                    ncols = max(len(r) for r in table_rows)
                    t = doc.add_table(rows=len(table_rows), cols=ncols)
                    t.alignment = WD_TABLE_ALIGNMENT.CENTER
                    set_table_borders(t, color="E2E8F0")
                    
                    for r_idx, row_data in enumerate(table_rows):
                        for c_idx, cell_text in enumerate(row_data):
                            if c_idx < ncols:
                                cell = t.cell(r_idx, c_idx)
                                set_cell_margins(cell, top=90, bottom=90, left=120, right=120)
                                p = cell.paragraphs[0]
                                p.paragraph_format.space_before = Pt(2)
                                p.paragraph_format.space_after = Pt(2)
                                p.paragraph_format.line_spacing = 1.05
                                
                                is_header = (r_idx == 0)
                                if is_header:
                                    set_cell_background(cell, "1E293B")
                                elif r_idx % 2 == 1:
                                    set_cell_background(cell, "F8FAFC")
                                else:
                                    set_cell_background(cell, "FFFFFF")
                                    
                                # Parse inline formatting in cells
                                tokens = re.split(r'(\*\*.*?\*\*|`.*?`|\*.*?\*)', cell_text)
                                for token in tokens:
                                    if not token:
                                        continue
                                    if token.startswith('**') and token.endswith('**'):
                                        r = p.add_run(token[2:-2])
                                        r.bold = True
                                    elif token.startswith('`') and token.endswith('`'):
                                        r = p.add_run(token[1:-1])
                                        r.font.name = 'Consolas'
                                        r.font.size = Pt(8.5)
                                    else:
                                        r = p.add_run(token)
                                    
                                    r.font.name = 'Calibri'
                                    r.font.size = Pt(9.0)
                                    if is_header:
                                        r.bold = True
                                        r.font.color.rgb = RGBColor(255, 255, 255)
                                    else:
                                        r.font.color.rgb = RGBColor(30, 41, 59)
                    
                    sp = doc.add_paragraph()
                    sp.paragraph_format.space_after = Pt(6)
                table_rows = []

        # 3. Blank line
        if not line:
            i += 1
            continue
            
        # 4. Horizontal Rule (---)
        if re.match(r'^---+$', line):
            i += 1
            continue
            
        # 5. Headings
        if line.startswith('# '):
            h_text = line[2:].strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(16)
            p.paragraph_format.space_after = Pt(8)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(h_text)
            run.font.name = 'Calibri'
            run.font.size = Pt(22)
            run.bold = True
            run.font.color.rgb = RGBColor(15, 23, 42)
            i += 1
            continue
            
        if line.startswith('## '):
            h_text = line[3:].strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(h_text)
            run.font.name = 'Calibri'
            run.font.size = Pt(16)
            run.bold = True
            run.font.color.rgb = RGBColor(30, 58, 138)
            i += 1
            continue

        if line.startswith('### '):
            h_text = line[4:].strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(h_text)
            run.font.name = 'Calibri'
            run.font.size = Pt(13)
            run.bold = True
            run.font.color.rgb = RGBColor(51, 65, 85)
            i += 1
            continue

        if line.startswith('#### '):
            h_text = line[5:].strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(h_text)
            run.font.name = 'Calibri'
            run.font.size = Pt(11)
            run.bold = True
            run.font.color.rgb = RGBColor(79, 70, 229)
            i += 1
            continue

        # 6. Blockquotes / Alerts (> ...)
        if line.startswith('> '):
            quote_text = line[2:].strip()
            create_callout_box(doc, quote_text, title="KEY FINDING / SPECIFICATION")
            i += 1
            continue

        # 7. Bullet Lists (* or -)
        if re.match(r'^[\*\-]\s+', line):
            bullet_text = re.sub(r'^[\*\-]\s+', '', line)
            p = add_styled_paragraph(doc, bullet_text, style='List Bullet', space_after=3, space_before=1)
            i += 1
            continue

        # 8. Numbered Lists (1. 2. etc.)
        if re.match(r'^\d+\.\s+', line):
            num_text = re.sub(r'^\d+\.\s+', '', line)
            p = add_styled_paragraph(doc, num_text, style='List Number', space_after=3, space_before=1)
            i += 1
            continue

        # 9. Math block ($$...$$)
        if line.startswith('$$') and line.endswith('$$') and len(line) > 4:
            math_expr = line[2:-2].strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(f"  [ Formula: {math_expr} ]  ")
            run.font.name = 'Consolas'
            run.font.size = Pt(10)
            run.italic = True
            run.font.color.rgb = RGBColor(67, 56, 202)
            i += 1
            continue

        # 10. Regular Paragraph
        add_styled_paragraph(doc, line, style='Normal', space_after=6, space_before=0)
        i += 1

    doc.save(docx_path)
    print(f"Successfully generated DOCX report at: {docx_path}")

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_md = os.path.join(base_dir, 'SIC_AI_Capstone_Project_Final_Report.md')
    default_docx = os.path.join(base_dir, 'SIC_AI_Capstone_Project_Final_Report.docx')
    md_file = sys.argv[1] if len(sys.argv) > 1 else default_md
    docx_file = sys.argv[2] if len(sys.argv) > 2 else default_docx
    build_docx(md_file, docx_file)
