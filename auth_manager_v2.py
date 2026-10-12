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
    conn = db_web_v2.conectar_db()
    cursor = conn.cursor()
    try:
        # Usamos %s en lugar de ? para PostgreSQL y especificamos el esquema public
        cursor.execute("SELECT user_id, password_hash FROM public.usuarios WHERE email = %s", (email,))
        resultado = cursor.fetchone()
        
        if resultado:
            user_id, password_hash = resultado
            # Aquí compruebas tu hash de contraseña según lo tengas implementado
            # Por ejemplo: if verificar_password(password, password_hash): return user_id
            return user_id
        return None
    except Exception as e:
        print(f"Error en login: {e}")
        return None
    finally:
        cursor.close()
        conn.close()