#!/usr/bin/env python3
"""Создать или восстановить админ-пользователя (admin@tickets.local / admin123)."""
import os
from dotenv import load_dotenv
from app.db import engine, Base, SessionLocal
from app.models import User
from app.auth import get_password_hash

load_dotenv()

ADMIN_EMAIL = "admin@tickets.local"
ADMIN_PASSWORD = "admin123"

def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            print(f"✓ Админ уже есть: {admin.email}")
            return

        user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if user:
            user.is_admin = True
            user.hashed_password = get_password_hash(ADMIN_PASSWORD)
            db.commit()
            print(f"✓ Пользователь {ADMIN_EMAIL} назначен админом, пароль сброшен на: {ADMIN_PASSWORD}")
            return

        admin_user = User(
            email=ADMIN_EMAIL,
            hashed_password=get_password_hash(ADMIN_PASSWORD),
            is_admin=True
        )
        db.add(admin_user)
        db.commit()
        print(f"✓ Создан админ: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
