import sqlite3
import bcrypt
import os
import db_web_v2 # Asegúrate de importar tu módulo de conexión

def conectar_db():
    # Usamos la misma ruta que tu nueva BBDD
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return sqlite3.connect(os.path.join(base_dir, 'web_analytics.db'))

def registrar_usuario(email, nombre, password, sexo):
    # Generar salt y hash (Tu lógica actual, que es la correcta)
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    
    conn = db_web_v2.conectar_db()
    cursor = conn.cursor()
    try:
        # Añadimos 'sexo' en el INSERT y en los valores
        cursor.execute('''INSERT INTO usuarios (email, nombre, password_hash, sexo) 
                          VALUES (?, ?, ?, ?)''', (email, nombre, hashed_password, sexo))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # El email ya existe
    finally:
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