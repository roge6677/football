from io import BytesIO
from reportlab.lib.pagesizes import A6, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import qrcode
from app.models import Ticket, Match
from sqlalchemy.orm import Session

def build_ticket_pdf(ticket: Ticket, db: Session) -> BytesIO:
    match = db.query(Match).filter(Match.id == ticket.match_id).first()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A6))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(10*mm, 70*mm, "Электронный билет")
    c.setFont("Helvetica", 10)
    c.drawString(10*mm, 60*mm, f"Заказ: {ticket.order_id}")
    c.drawString(10*mm, 54*mm, f"Матч: {match.home_team} vs {match.away_team}")
    c.drawString(10*mm, 48*mm, f"Дата: {match.date_time.strftime('%Y-%m-%d %H:%M')}")
    c.drawString(10*mm, 42*mm, f"Место: {ticket.sector} ряд {ticket.row} место {ticket.seat}")
    qr_data = f"TICKET:{ticket.id};ORDER:{ticket.order_id};MATCH:{ticket.match_id}"
    img = qrcode.make(qr_data)
    img_path = BytesIO()
    img.save(img_path, format="PNG")
    img_path.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(img_path), 100*mm, 30*mm, 35*mm, 35*mm, preserveAspectRatio=True, mask='auto')
    c.showPage()
    c.save()
    buf.seek(0)
    return buf
