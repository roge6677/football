from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Numeric, JSON, Enum
from sqlalchemy.orm import relationship
from app.db import Base
import enum

class OrderStatus(enum.Enum):
    pending = "pending"
    paid = "paid"
    cancelled = "cancelled"

class TicketStatus(enum.Enum):
    reserved = "reserved"
    paid = "paid"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    orders = relationship("Order", back_populates="user")

class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    league = Column(String(100), nullable=True)
    home_team = Column(String(100), nullable=False)
    away_team = Column(String(100), nullable=False)
    date_time = Column(DateTime, nullable=False)
    stadium_name = Column(String(150), nullable=False)
    layout = Column(JSON, nullable=False)
    base_price = Column(Numeric(10,2), nullable=False, default=0)
    tickets = relationship("Ticket", back_populates="match")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending, nullable=False)
    total_amount = Column(Numeric(10,2), default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="orders")
    tickets = relationship("Ticket", back_populates="order")

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sector = Column(String(50), nullable=False)
    row = Column(Integer, nullable=False)
    seat = Column(Integer, nullable=False)
    price = Column(Numeric(10,2), nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.reserved, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    match = relationship("Match", back_populates="tickets")
    order = relationship("Order", back_populates="tickets")
    __table_args__ = (UniqueConstraint("match_id","sector","row","seat", name="uq_match_seat"),)
