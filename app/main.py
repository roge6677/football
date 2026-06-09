import os
from datetime import datetime
from urllib.parse import quote
from typing import List
from fastapi import FastAPI, Request, Depends, Form, Response, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from app.db import Base, engine, get_db
from app.models import User, Match, Ticket, TicketStatus, Order, OrderStatus
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user, get_current_admin, decode_token

app = FastAPI(title="Ticketing")
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

Base.metadata.create_all(bind=engine)


# Pydantic models for request bodies
class SeatReservation(BaseModel):
    sector: str
    row: int
    seat: int
    price: float


class ReserveMultipleRequest(BaseModel):
    seats: List[SeatReservation]


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    """Для 401 при переходе по страницам — редирект на вход с сообщением."""
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        msg = "Войдите или зарегистрируйтесь, чтобы выбрать места на матч"
        return RedirectResponse(
            url="/login?error=" + quote(msg),
            status_code=302,
        )
    raise exc


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    matches = db.query(Match).order_by(Match.date_time.asc()).all()
    user = None
    try:
        token = request.cookies.get("access_token")
        if token:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                user = db.query(User).filter(User.id == int(user_id)).first()
    except:
        pass
    return templates.TemplateResponse("index.html", {"request": request, "matches": matches, "user": user, "body_class": "page-home"})

@app.get("/register")
def register_page(request: Request, error: str = None):
    return templates.TemplateResponse("register.html", {"request": request, "error": error or request.query_params.get("error"), "body_class": "page-auth"})

@app.post("/register")
def register(response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if len(password) < 6:
        return RedirectResponse(url="/register?error=Пароль должен быть не менее 6 символов", status_code=302)
    
    exists = db.query(User).filter(User.email == email).first()
    if exists:
        return RedirectResponse(url="/register?error=Этот email уже зарегистрирован", status_code=302)
    
    try:
        # Only make admin if specifically admin email (disabled auto-admin)
        is_admin = email.lower() == "admin@tickets.local"
        user = User(email=email, hashed_password=get_password_hash(password), is_admin=is_admin)
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"sub": str(user.id)})
        response = Response(status_code=302, headers={"Location": "/"})
        response.set_cookie("access_token", token, path="/", httponly=True, samesite="Lax", max_age=86400*30)
        return response
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/register?error=Ошибка регистрации", status_code=302)

@app.get("/login")
def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error or request.query_params.get("error"), "body_class": "page-auth"})

@app.post("/login")
def login(response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return RedirectResponse(url="/login?error=Неверные учетные данные", status_code=302)
    
    token = create_access_token({"sub": str(user.id)})
    response = Response(status_code=302, headers={"Location": "/"})
    response.set_cookie("access_token", token, path="/", httponly=True, samesite="Lax", max_age=86400*30)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token", path="/")
    return response

@app.get("/match/{match_id}")
def match_page(match_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)
    # Get all taken seats (both reserved and paid)
    taken = db.query(Ticket).filter(Ticket.match_id == match_id).all()
    taken_map = {(t.sector, t.row, t.seat): t.status.value for t in taken}
    return templates.TemplateResponse("match.html", {"request": request, "match": match, "taken_map": taken_map, "user": user, "body_class": "page-match"})


@app.post("/match/{match_id}/reserve-multiple")
def reserve_multiple(match_id: int, req: ReserveMultipleRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Резервирование нескольких мест одновременно."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Матч не найден")
    
    if not req.seats:
        raise HTTPException(status_code=400, detail="Нет выбранных мест")
    
    errors = []
    created_tickets = []
    
    for seat_info in req.seats:
        # Проверяем, занято ли место
        existing = db.query(Ticket).filter(
            Ticket.match_id == match_id,
            Ticket.sector == seat_info.sector,
            Ticket.row == seat_info.row,
            Ticket.seat == seat_info.seat
        ).first()
        
        if existing:
            errors.append(f"Место {seat_info.sector} ряд {seat_info.row} место {seat_info.seat} уже занято")
            continue
        
        # Создаем билет
        ticket = Ticket(
            match_id=match.id,
            user_id=user.id,
            sector=seat_info.sector,
            row=seat_info.row,
            seat=seat_info.seat,
            price=seat_info.price,
            status=TicketStatus.reserved
        )
        created_tickets.append(ticket)
    
    if errors:
        # Если есть ошибки и билеты не созданы, возвращаем ошибку
        if not created_tickets:
            raise HTTPException(status_code=400, detail="; ".join(errors))
    
    # Добавляем созданные билеты в БД
    for ticket in created_tickets:
        db.add(ticket)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при резервировании мест")
    
    # Возвращаем успешный ответ с редиректом на корзину
    return JSONResponse(
        status_code=200,
        content={"status": "success", "redirect": "/cart"}
    )


@app.post("/match/{match_id}/reserve")
def reserve(match_id: int, sector: str = Form(...), row: int = Form(...), seat: int = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)
    
    # Check if seat is already taken
    existing = db.query(Ticket).filter(
        Ticket.match_id == match_id,
        Ticket.sector == sector,
        Ticket.row == row,
        Ticket.seat == seat
    ).first()
    
    if existing:
        return RedirectResponse(url=f"/match/{match_id}?error=Это место уже занято", status_code=302)
    
    coef = 1.0
    if isinstance(match.layout, dict) and sector in match.layout:
        sec = match.layout[sector]
        coef = float(sec.get("price_coef", 1.0)) if isinstance(sec, dict) else 1.0
    price = float(match.base_price) * coef
    ticket = Ticket(match_id=match.id, user_id=user.id, sector=sector, row=row, seat=seat, price=price, status=TicketStatus.reserved)
    db.add(ticket)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return RedirectResponse(url=f"/match/{match_id}?error=Ошибка при резервировании", status_code=302)
    return Response(status_code=302, headers={"Location": "/cart"})

@app.get("/cart")
def cart(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tickets = db.query(Ticket).filter(Ticket.user_id == user.id, Ticket.status == TicketStatus.reserved).all()
    total = sum([float(t.price) for t in tickets])
    return templates.TemplateResponse("cart.html", {"request": request, "tickets": tickets, "total": total, "user": user, "body_class": "page-cart"})

@app.post("/cart/remove/{ticket_id}")
def remove_from_cart(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id, Ticket.status == TicketStatus.reserved).first()
    if t:
        db.delete(t)
        db.commit()
    return Response(status_code=302, headers={"Location": "/cart"})

@app.get("/checkout")
def checkout_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tickets = db.query(Ticket).filter(Ticket.user_id == user.id, Ticket.status == TicketStatus.reserved).all()
    if not tickets:
        return Response(status_code=302, headers={"Location": "/cart"})
    total = sum([float(t.price) for t in tickets])
    return templates.TemplateResponse("checkout.html", {"request": request, "tickets": tickets, "total": total, "user": user, "body_class": "page-cart"})

@app.post("/checkout")
def checkout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tickets = db.query(Ticket).filter(Ticket.user_id == user.id, Ticket.status == TicketStatus.reserved).all()
    if not tickets:
        raise HTTPException(status_code=400)
    total = sum([float(t.price) for t in tickets])
    order = Order(user_id=user.id, total_amount=total, status=OrderStatus.pending)
    db.add(order)
    db.commit()
    db.refresh(order)
    for t in tickets:
        t.order_id = order.id
    db.commit()
    return Response(status_code=302, headers={"Location": f"/payment/{order.id}"})

@app.get("/payment/{order_id}")
def payment_page(order_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("payment.html", {"request": request, "order": order, "user": user, "body_class": "page-cart"})

@app.post("/payment/{order_id}")
def pay(order_id: int, card_number: str = Form(...), exp: str = Form(...), cvv: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order or order.status != OrderStatus.pending:
        raise HTTPException(status_code=400)
    order.status = OrderStatus.paid
    db.commit()
    db.refresh(order)
    db.query(Ticket).filter(Ticket.order_id == order.id).update({Ticket.status: TicketStatus.paid})
    db.commit()
    return Response(status_code=302, headers={"Location": f"/orders/{order.id}"})

@app.get("/orders/{order_id}")
def order_page(order_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404)
    tickets = db.query(Ticket).filter(Ticket.order_id == order.id).all()
    return templates.TemplateResponse("order.html", {"request": request, "order": order, "tickets": tickets, "user": user, "body_class": "page-cart"})

@app.get("/my-tickets")
def my_tickets(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    reserved = db.query(Ticket).filter(Ticket.user_id == user.id, Ticket.status == TicketStatus.reserved).all()
    paid = db.query(Ticket).filter(Ticket.user_id == user.id, Ticket.status == TicketStatus.paid).all()
    return templates.TemplateResponse("my_tickets.html", {"request": request, "reserved": reserved, "paid": paid, "user": user, "body_class": "page-my-tickets"})

def _match_layout(vip_rows, vip_seats, std_rows, std_seats, fan_rows, fan_seats):
    return {"VIP": {"rows": int(vip_rows), "seats_per_row": int(vip_seats), "price_coef": 2.0},
            "STANDARD": {"rows": int(std_rows), "seats_per_row": int(std_seats), "price_coef": 1.0},
            "FAN": {"rows": int(fan_rows), "seats_per_row": int(fan_seats), "price_coef": 0.7}}

@app.get("/admin")
def admin_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    matches = db.query(Match).order_by(Match.date_time.asc()).all()
    ticket_counts = {m.id: db.query(Ticket).filter(Ticket.match_id == m.id).count() for m in matches}
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "matches": matches, "ticket_counts": ticket_counts, "body_class": "page-admin"})

@app.get("/admin/match/{match_id}/edit")
def admin_edit_match_page(match_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin_edit.html", {"request": request, "user": user, "match": match, "body_class": "page-admin"})

@app.post("/admin/match/{match_id}/edit")
def admin_edit_match(match_id: int, request: Request, home_team: str = Form(...), away_team: str = Form(...), date_time: str = Form(...), stadium_name: str = Form(...), vip_rows: int = Form(...), vip_seats: int = Form(...), std_rows: int = Form(...), std_seats: int = Form(...), fan_rows: int = Form(...), fan_seats: int = Form(...), base_price: float = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)
    dt = datetime.fromisoformat(date_time)
    match.home_team = home_team
    match.away_team = away_team
    match.date_time = dt
    match.stadium_name = stadium_name
    match.layout = _match_layout(vip_rows, vip_seats, std_rows, std_seats, fan_rows, fan_seats)
    match.base_price = base_price
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/admin/match/{match_id}/delete")
def admin_delete_match(match_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)
    tickets_count = db.query(Ticket).filter(Ticket.match_id == match_id).count()
    if tickets_count > 0:
        return RedirectResponse(url="/admin?error=" + quote("Нельзя удалить матч: на него уже есть билеты"), status_code=302)
    db.delete(match)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/admin/match")
def admin_add_match(request: Request, home_team: str = Form(...), away_team: str = Form(...), date_time: str = Form(...), stadium_name: str = Form(...), vip_rows: int = Form(...), vip_seats: int = Form(...), std_rows: int = Form(...), std_seats: int = Form(...), fan_rows: int = Form(...), fan_seats: int = Form(...), base_price: float = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    dt = datetime.fromisoformat(date_time)
    layout = _match_layout(vip_rows, vip_seats, std_rows, std_seats, fan_rows, fan_seats)
    m = Match(home_team=home_team, away_team=away_team, date_time=dt, stadium_name=stadium_name, layout=layout, base_price=base_price)
    db.add(m)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@app.get("/tickets/{ticket_id}.pdf")
def ticket_pdf(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse
    from app.utils.ticket_pdf import build_ticket_pdf
    t = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not t or t.user_id != user.id or t.status != TicketStatus.paid:
        raise HTTPException(status_code=404)
    pdf = build_ticket_pdf(t, db)
    return StreamingResponse(iter([pdf.getvalue()]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="ticket_{ticket_id}.pdf"'})
