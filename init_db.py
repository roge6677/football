#!/usr/bin/env python3
"""Script to initialize database with test data"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app.db import engine, Base, SessionLocal
from app.models import Match, User
from app.auth import get_password_hash

load_dotenv()

def init_db():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("✓ Таблицы созданы")
    
    db = SessionLocal()
    
    # Check if data already exists
    if db.query(Match).count() > 0:
        print("! Матчи уже существуют в БД")
        db.close()
        return
    
    # Create sample matches
    matches = [
        Match(
            home_team="Спартак",
            away_team="ЦСКА",
            date_time=datetime.now() + timedelta(days=7),
            stadium_name="Открытие Арена",
            layout={"VIP": {"rows": 10, "seats_per_row": 20, "price_coef": 2.0},
                   "STANDARD": {"rows": 15, "seats_per_row": 30, "price_coef": 1.0},
                   "FAN": {"rows": 20, "seats_per_row": 40, "price_coef": 0.7}},
            base_price=1000
        ),
        Match(
            home_team="Динамо",
            away_team="Локомотив",
            date_time=datetime.now() + timedelta(days=14),
            stadium_name="РЖД-Арена",
            layout={"VIP": {"rows": 8, "seats_per_row": 18, "price_coef": 2.0},
                   "STANDARD": {"rows": 12, "seats_per_row": 28, "price_coef": 1.0},
                   "FAN": {"rows": 18, "seats_per_row": 38, "price_coef": 0.7}},
            base_price=900
        ),
        Match(
            home_team="Зенит",
            away_team="Ростов",
            date_time=datetime.now() + timedelta(days=21),
            stadium_name="Крестовский",
            layout={"VIP": {"rows": 12, "seats_per_row": 25, "price_coef": 2.0},
                   "STANDARD": {"rows": 18, "seats_per_row": 35, "price_coef": 1.0},
                   "FAN": {"rows": 25, "seats_per_row": 45, "price_coef": 0.7}},
            base_price=1200
        ),
    ]
    
    for match in matches:
        db.add(match)
    
    db.commit()
    print(f"✓ Добавлено {len(matches)} матчей")
    
    # Create admin user if needed
    admin = db.query(User).filter(User.is_admin == True).first()
    if not admin:
        admin_user = User(
            email="admin@tickets.local",
            hashed_password=get_password_hash("admin123"),
            is_admin=True
        )
        db.add(admin_user)
        db.commit()
        print("✓ Создан админ-аккаунт: admin@tickets.local / admin123")
    
    db.close()
    print("\n✓ База данных инициализирована!")

if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"✗ Ошибка инициализации: {e}")
