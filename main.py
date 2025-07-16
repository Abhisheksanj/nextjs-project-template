from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
import uuid
import os
from datetime import datetime

app = FastAPI()

OUTPUT_DIR = "generated_pdfs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"message": "Government PDF Conversion API. Use /upload and /generate endpoints."}


@app.post("/upload/")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Uploads a PDF, extracts text using pdfplumber, and returns it.
    """
    temp_filename = f"temp_{uuid.uuid4()}.pdf"
    with open(temp_filename, "wb") as f:
        f.write(await file.read())

    extracted_text = ""
    with pdfplumber.open(temp_filename) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"

    os.remove(temp_filename)

    return {"extracted_text": extracted_text.strip()}


@app.post("/generate/")
async def generate_fir(
    fir_no: str = Form(...),
    fir_date: str = Form(...),
    section: str = Form(...),
    victim_name: str = Form(...),
    fraud_amount: str = Form(...),
    complaint_text: str = Form(...)
):
    """
    Generates a FIR-style PDF from provided fields.
    """
    output_filename = f"{OUTPUT_DIR}/FIR_{uuid.uuid4()}.pdf"

    c = canvas.Canvas(output_filename, pagesize=A4)
    width, height = A4

    margin_left = 30 * mm
    margin_top = height - 30 * mm
    line_height = 14

    # Title and header info
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_left, margin_top, f"FIR no.: {fir_no} dated {fir_date}")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_left, margin_top - line_height * 1.5, f"Under Section: {section}")

    c.drawString(margin_left, margin_top - line_height * 3, f"Victim’s Name: {victim_name}")

    c.drawString(margin_left, margin_top - line_height * 4.5, f"Total Fraud Amount: {fraud_amount} /- INR")

    # Notes section with underlined lines
    notes_top = margin_top - line_height * 6.5
    notes_left = margin_left
    notes_width = width - 2 * margin_left
    notes_height = line_height * 8

    c.setFont("Helvetica", 11)
    c.drawString(notes_left, notes_top, "Notes:-")

    # Draw underlined lines for notes
    line_y = notes_top - 10
    line_spacing = 15
    for i in range(7):
        c.line(notes_left, line_y - i * line_spacing, notes_left + notes_width, line_y - i * line_spacing)

    # Flow Chart title centered and underlined
    flowchart_title_y = line_y - line_spacing * 8 - 10
    c.setFont("Helvetica-BoldOblique", 14)
    flowchart_title = "Flow Chart"
    text_width = c.stringWidth(flowchart_title, "Helvetica-BoldOblique", 14)
    c.drawString((width - text_width) / 2, flowchart_title_y, flowchart_title)
    c.line((width - text_width) / 2, flowchart_title_y - 2, (width + text_width) / 2, flowchart_title_y - 2)

    # Placeholder for flow chart box (since actual flow chart is complex)
    flowchart_box_top = flowchart_title_y - 20
    flowchart_box_left = margin_left
    flowchart_box_width = width - 2 * margin_left
    flowchart_box_height = 200

    c.setStrokeColor(colors.black)
    c.rect(flowchart_box_left, flowchart_box_top - flowchart_box_height, flowchart_box_width, flowchart_box_height, stroke=1, fill=0)

    # Add placeholder text inside flow chart box
    c.setFont("Helvetica", 10)
    placeholder_text = "Flow chart diagram goes here"
    text_width = c.stringWidth(placeholder_text, "Helvetica", 10)
    c.drawString((width - text_width) / 2, flowchart_box_top - flowchart_box_height / 2, placeholder_text)

    c.save()

    return {"download_link": f"/download/{os.path.basename(output_filename)}"}


@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/pdf')
    else:
        return {"error": "File not found"}
