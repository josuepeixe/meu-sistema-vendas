import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# Configuração da página (deve ser a primeira coisa)
st.set_page_config(page_title="Controle de Vendas", layout="wide")

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect("vendas_web.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            produtos TEXT,
            valor REAL,
            data TEXT,
            parcelas_total INTEGER,
            parcelas_pagas INTEGER,
            status TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# --- INTERFACE ---
st.title("🛍️ Controle de Vendas Revendedora")

# Sidebar para navegação
menu = st.sidebar.selectbox("Menu", ["Registrar Venda", "Histórico de Vendas"])

if menu == "Registrar Venda":
    st.subheader("📝 Novo Registro")
    
    with st.form("form_venda", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("Nome do Cliente")
            valor = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01, format="%.2f")
        with col2:
            parcelas = st.number_input("Quantidade de Parcelas", min_value=1, max_value=12, value=1)
            
        produtos = st.text_area("Produtos (detalhes)")
        
        submit = st.form_submit_button("Salvar Venda")
        
        if submit:
            if cliente and produtos and valor > 0:
                data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
                cursor = conn.cursor()
                cursor.execute("""INSERT INTO vendas 
                    (cliente, produtos, valor, data, parcelas_total, parcelas_pagas, status) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (cliente, produtos, valor, data_atual, parcelas, 0, "Pendente"))
                conn.commit()
                st.success(f"Venda para {cliente} registrada com sucesso!")
            else:
                st.error("Por favor, preencha todos os campos corretamente.")

elif menu == "Histórico de Vendas":
    st.subheader("📊 Todas as Vendas")
    
    # Filtros rápidos
    busca = st.text_input("🔍 Buscar por cliente ou produto")
    so_pendentes = st.checkbox("Mostrar apenas pendentes")
    
    query = "SELECT * FROM vendas"
    if so_pendentes:
        query += " WHERE status != 'Pago'"
    
    df = pd.read_sql_query(query, conn)
    
    if not df.empty:
        # Lógica de busca simples no DataFrame
        if busca:
            df = df[df['cliente'].str.contains(busca, case=False) | df['produtos'].str.contains(busca, case=False)]

        # Exibição das vendas em "Cards" (Melhor para celular)
        for index, row in df.iterrows():
            with st.expander(f"{row['status']} | {row['cliente']} - R$ {row['valor']:.2f}"):
                st.write(f"**Produtos:** {row['produtos']}")
                st.write(f"**Data:** {row['data']}")
                st.write(f"**Parcelas:** {row['parcelas_pagas']} de {row['parcelas_total']}")
                
                # Botão de Pagamento
                if row['status'] != "Pago":
                    if st.button(f"Pagar parcela ({row['parcelas_pagas'] + 1})", key=f"btn_{row['id']}"):
                        nova_p = row['parcelas_pagas'] + 1
                        novo_status = "Pago" if nova_p == row['parcelas_total'] else "Pagamento Parcial"
                        
                        cursor = conn.cursor()
                        cursor.execute("UPDATE vendas SET parcelas_pagas = ?, status = ? WHERE id = ?", 
                                       (nova_p, novo_status, row['id']))
                        conn.commit()
                        st.rerun()
                
                if st.button("🗑️ Excluir Venda", key=f"del_{row['id']}"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM vendas WHERE id = ?", (row['id'],))
                    conn.commit()
                    st.rerun()
        
        st.divider()
        st.metric("Volume Total de Vendas", f"R$ {df['valor'].sum():.2f}")
    else:
        st.info("Nenhuma venda encontrada.")