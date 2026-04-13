import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Vendas na Nuvem", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
# O Streamlit vai buscar o link da planilha nos "Secrets" que vamos configurar
conn = st.connection("gsheets", type=GSheetsConnection)

def ler_dados():
    return conn.read(ttl=0) # ttl=0 garante que ele pegue dados frescos, sem cache

# --- INTERFACE ---
st.title("🛍️ Sistema de Vendas (Google Sheets)")

menu = st.sidebar.selectbox("Menu", ["Registrar Venda", "Histórico de Vendas"])
df = ler_dados()

if menu == "Registrar Venda":
    st.subheader("📝 Novo Registro")
    with st.form("form_venda", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("Nome do Cliente")
            valor = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01)
        with col2:
            parcelas = st.number_input("Quantidade de Parcelas", min_value=1, max_value=12, value=1)
        
        produtos = st.text_area("Produtos")
        submit = st.form_submit_button("Salvar na Planilha")
        
        if submit and cliente:
            # Criar nova linha
            nova_venda = pd.DataFrame([{
                "id": len(df) + 1,
                "cliente": cliente,
                "produtos": produtos,
                "valor": valor,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "parcelas_total": int(parcelas),
                "parcelas_pagas": 0,
                "status": "Pendente"
            }])
            
            # Adicionar ao DataFrame existente e salvar
            df_atualizado = pd.concat([df, nova_venda], ignore_index=True)
            conn.update(data=df_atualizado)
            st.success("Venda salva com sucesso na sua Planilha!")
            st.rerun()

elif menu == "Histórico de Vendas":
    st.subheader("📊 Histórico Real")
    
    if not df.empty:
        for index, row in df.iterrows():
            with st.expander(f"{row['status']} | {row['cliente']} - R$ {row['valor']}"):
                st.write(f"**Produtos:** {row['produtos']}")
                st.write(f"**Parcelas:** {row['parcelas_pagas']} / {row['parcelas_total']}")
                
                # Botão de Pagamento
                if row['status'] != "Pago":
                    if st.button(f"Pagar Parcela", key=f"p_{index}"):
                        df.at[index, 'parcelas_pagas'] += 1
                        if df.at[index, 'parcelas_pagas'] >= df.at[index, 'parcelas_total']:
                            df.at[index, 'status'] = "Pago"
                        else:
                            df.at[index, 'status'] = "Pagamento Parcial"
                        
                        conn.update(data=df)
                        st.rerun()
                
                if st.button("🗑️ Excluir", key=f"d_{index}"):
                    df = df.drop(index)
                    conn.update(data=df)
                    st.rerun()
        
        st.metric("Total Acumulado", f"R$ {df['valor'].sum():.2f}")
    else:
        st.info("Planilha vazia.")
