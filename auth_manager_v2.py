import sqlite3
import bcrypt
import os
import db_web_v2 # Asegúrate de importar tu módulo de conexión

def conectar_db():
    # Usamos la misma ruta que tu nueva BBDD
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return sqlite3.connect(os.path.join(base_dir, 'web_analytics.db'))

import streamlit as st

def registrar_usuario(email, nombre, password, sexo):
    conn = db_web_v2.conectar_db()
    cursor = conn.cursor()
    try:
        sql = 'INSERT INTO public.usuarios (email, nombre, password_hash, sexo) VALUES (%s, %s, %s, %s)'
        cursor.execute(sql, (email, nombre, password, sexo))
        conn.commit()
        return True
    except Exception as e:
        # Esto imprimirá el error exacto en rojo directamente en tu pantalla
        st.error(f"ERROR DE SQL EXACTO: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def verificar_login(email, password):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, password_hash FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        user_id, hashed_password = user
        # Verificar hash
        if bcrypt.checkpw(password.encode('utf-8'), hashed_password):
            return user_id
    return None