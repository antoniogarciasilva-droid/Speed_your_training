import os
import psycopg2
import streamlit as st

def conectar_db():
    # Puedes leer los datos de st.secrets o ponerlos directamente aquí para pruebas
    return psycopg2.connect(
        host=st.secrets["SUPABASE_HOST"],
        database=st.secrets["SUPABASE_DB"],
        user=st.secrets["SUPABASE_USER"],
        password=st.secrets["SUPABASE_PASSWORD"],
        port=st.secrets.get("SUPABASE_PORT", "6543")
    )

def inicializar_db_web():
    # Como ya creamos las tablas directamente en el SQL Editor de Supabase, 
    # esta función ya no necesita recrearlas, o puedes dejarla vacía (pass).
    pass