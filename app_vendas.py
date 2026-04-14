import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import dateutil.relativedelta
import urllib.parse  # Para formatar a mensagem do WhatsApp

# Configuração da página
st.set_page_config(page_title="Vendas Pro + Dashboard", layout="wide", page_icon="📈")

# --- CONEXÃO E CACHE ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def ler_dados_cacheado():
    try:
        data = conn.read(ttl=0)
        if data is not None:
            data = data.dropna(how='all')
            return data.fillna("")
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])
    except Exception as e:
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

def atualizar_sistema():
    st.cache_data.clear()
    st.rerun()

# --- LÓGICA DE DATAS ---
def calcular_opcoes_quinzena(data_referencia):
    data_minima = data_referencia + timedelta(days=7)
    data_minima = data_minima.replace(hour=0, minute=0, second=0, microsecond=0)
    if data_minima.day <= 1:
        opt1 = data_minima.replace(day=1)
    elif data_minima.day <= 15:
        opt1 = data_minima.replace(day=15)
    else:
        opt1 = (data_minima + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    
    if opt1.day == 1:
        opt2 = opt1.replace(day=15)
    else:
        opt2 = (opt1 + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    return opt1, opt2

def gerar_sequencia_datas(data_inicio, num_parcelas, frequencia):
    datas = []
    data_atual = data_inicio
    for i in range(num_parcelas):
        if i == 0:
            datas.append(data_atual.strftime("%d/%m"))
            continue
        if frequencia == "Mensal":
            data_atual = data_atual + dateutil.relativedelta.relativedelta(months=1)
        else:
            if data_atual.day == 1:
                data_atual = data_atual.replace(day=15)
            else:
                data_atual = (data_atual + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
        datas.append(data_atual.strftime("%d/%m"))
    return datas

# --- INTERFACE ---
st.title("🛍️ Gestão de Vendas")

if st.sidebar.button("🔄 Atualizar Dados"):
    atualizar_sistema()

menu = st.sidebar.selectbox("Menu", ["Registrar Venda", "Histórico de Vendas"])
df = ler_dados_cacheado()

# --- REGISTRO DE VENDA ---
if menu == "Registrar Venda":
    st.subheader("📝 Novo Registro")
    col1, col2 = st.columns(2)
    with col1:
        cliente = st.text_input("Nome do Cliente", key="c_field")
        valor_total = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01, key="v_field", value=None)
        frequencia = st.radio("Frequência de Pagamento", ["Mensal", "Quinzena"], key="freq_field")
        
        if frequencia == "Quinzena":
            if "opcoes_q" not in st.session_state:
                st.session_state.opcoes_q = calcular_opcoes_quinzena(datetime.now())
            data_primeira_parcela = st.radio("Primeira parcela?", options=st.session_state.opcoes_q, format_func=lambda x: x.strftime("%d/%m/%Y"), key="q_radio")
        else:
            data_primeira_parcela = (datetime.now() + dateutil.relativedelta.relativedelta(months=1))

    with col2:
        num_parcelas = st.number_input("Nº de Parcelas", min_value=1, max_value=24, value=1)
        produtos = st.text_area("Produtos e Detalhes")

    if st.button("🚀 Salvar Venda", type="primary"):
        if cliente and produtos and valor_total:
            lista_datas = gerar_sequencia_datas(data_primeira_parcela, num_parcelas, frequencia)
            valor_p = valor_total / num_parcelas
            carne_texto = f"{produtos}\nValor Total: R$ {valor_total:.2f}\n\n"
            for d in lista_datas:
                carne_texto += f"{valor_p:.2f} {d}\n"
            
            nova_venda = pd.DataFrame([{"id": len(df)+1, "cliente": cliente, "produtos": produtos, "valor": valor_total, "data": datetime.now().strftime("%d/%m/%Y"), "carne": carne_texto, "status": "Pendente"}])
            conn.update(data=pd.concat([df, nova_venda], ignore_index=True))
            st.success("Venda salva!")
            if "opcoes_q" in st.session_state: del st.session_state.opcoes_q
            atualizar_sistema()

# --- HISTÓRICO E DASHBOARD ---
elif menu == "Histórico de Vendas":
    # 📊 DASHBOARD (Resumo Financeiro)
    st.subheader("📊 Resumo Financeiro")
    if not df.empty:
        total_bruto = df['valor'].sum()
        
        # Lógica para calcular o que já foi pago baseado no texto do carnê
        pago_acumulado = 0
        for _, row in df.iterrows():
            carne = str(row['carne'])
            parcelas = [l for l in carne.split('\n') if '/' in l]
            num_pagas = sum(1 for p in parcelas if '(Pago!)' in p)
            if len(parcelas) > 0:
                pago_acumulado += (row['valor'] / len(parcelas)) * num_pagas
        
        pendente_acumulado = total_bruto - pago_acumulado
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Volume Total Vendido", f"R$ {total_bruto:.2f}")
        m2.metric("Total Recebido", f"R$ {pago_acumulado:.2f}", delta_color="normal")
        m3.metric("Total a Receber", f"R$ {pendente_acumulado:.2f}", delta="- Pendente", delta_color="inverse")
    
    st.divider()
    
    # 🔍 FILTROS
    st.subheader("📂 Lista de Vendas")
    c_busca, c_filtro = st.columns([2, 1])
    with c_busca:
        busca = st.text_input("🔍 Buscar Cliente")
    with c_filtro:
        filtro_status = st.selectbox("Filtrar Status", ["Todos", "Pendentes", "Pagamento Parcial", "Pago"])

    if not df.empty:
        df_f = df.copy()
        if busca:
            df_f = df_f[df_f['cliente'].astype(str).str.contains(busca, case=False)]
        if filtro_status != "Todos":
            # Filtra "Pendentes" mostrando tanto Pendentes quanto Parciais se desejar, 
            # aqui filtramos exatamente pelo texto do status
            df_f = df_f[df_f['status'] == filtro_status]

        for index, row in df_f.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            status_cor = "🔴" if row['status'] == "Pendente" else "🟢"
            if row['status'] == "Pagamento Parcial": status_cor = "🔵"
            
            with st.expander(f"{status_cor} {row['cliente']} - R$ {row['valor']:.2f}"):
                st.code(str(row['carne']), language="text")
                
                col_btn = st.columns([1, 1, 1, 2])
                
                with col_btn[0]: # BOTÃO PAGAR
                    if "(Pago!)" not in str(row['carne']) or row['status'] != "Pago":
                        if st.button("💰 Pagar", key=f"p_{index}"):
                            linhas = str(row['carne']).split('\n')
                            novo_carne = []
                            alterou = False
                            for l in linhas:
                                if "/" in l and "(Pago!)" not in l and not alterou:
                                    l += " (Pago!)"
                                    alterou = True
                                novo_carne.append(l)
                            df.at[index, 'carne'] = "\n".join(novo_carne)
                            tem_p = any("/" in l and "(Pago!)" not in l for l in novo_carne)
                            df.at[index, 'status'] = "Pago" if not tem_p else "Pagamento Parcial"
                            conn.update(data=df)
                            atualizar_sistema()
                
                with col_btn[1]: # BOTÃO WHATSAPP
                    # Prepara a mensagem para o WhatsApp
                    msg = f"Olá {row['cliente']}! Segue o resumo da sua compra:\n\n{row['carne']}"
                    msg_url = urllib.parse.quote(msg)
                    # Cria o link (sem número específico para você escolher o contato na hora)
                    st.link_button("🟢 WhatsApp", f"https://wa.me/?text={msg_url}")

                with col_btn[2]: # BOTÃO EXCLUIR
                    if st.button("🗑️", key=f"d_{index}"):
                        df = df.drop(index)
                        conn.update(data=df)
                        atualizar_sistema()
    else:
        st.info("Nenhuma venda encontrada.")
