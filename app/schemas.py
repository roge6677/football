from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class MatchBase(BaseModel):
    home_team: str
    away_team: str
    date_time: datetime
    stadium_name: str
    layout: Dict[str, Any]
    base_price: Decimal

class MatchOut(MatchBase):
    id: int
    class Config:
        orm_mode = True

class TicketOut(BaseModel):
    id: int
    match_id: int
    sector: str
    row: int
    seat: int
    price: Decimal
    status: str
    class Config:
        orm_mode = True

class OrderOut(BaseModel):
    id: int
    status: str
    total_amount: Decimal
    created_at: datetime
    class Config:
        orm_mode = True
