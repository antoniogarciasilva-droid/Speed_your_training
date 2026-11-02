import os
import psycopg2
try:
    import streamlit as st
except ImportError:
    st = None

def conectar_db():
    # Intentar leer primero de las variables de entorno de Render (os.environ)
    # y si no están, recurrir a st.secrets o a los valores por defecto
    host = os.getenv("SUPABASE_HOST") or (st.secrets.get("SUPABASE_HOST") if st and "SUPABASE_HOST" in st.secrets else None)
    database = os.getenv("SUPABASE_DB") or (st.secrets.get("SUPABASE_DB") if st and "SUPABASE_DB" in st.secrets else "postgres")
    user = os.getenv("SUPABASE_USER") or (st.secrets.get("SUPABASE_USER") if st and "SUPABASE_USER" in st.secrets else None)
    password = os.getenv("SUPABASE_PASSWORD") or (st.secrets.get("SUPABASE_PASSWORD") if st and "SUPABASE_PASSWORD" in st.secrets else None)
    port = os.getenv("SUPABASE_PORT") or (st.secrets.get("SUPABASE_PORT") if st and "SUPABASE_PORT" in st.secrets else "5432")

    return psycopg2.connect(
        host=host,
        database=database,
        user=user,
        password=password,
        port=port
    )

def inicializar_db_web():
    pass