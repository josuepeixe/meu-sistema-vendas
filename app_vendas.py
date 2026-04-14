import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import dateutil.relativedelta
import urllib.parse
import calendar

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas", layout="wide", page_icon="🚀")

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
    except:
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

def atualizar_sistema():
    st.cache_data.clear()
    st.rerun()

# --- LÓGICA DE DATAS AUTOMÁTICAS ---
def calcular_opcoes_quinzena(data_referencia):
    data_minima = data_referencia + timedelta(days=7)
    data_minima = data_minima.replace(hour=0, minute=0, second=0, microsecond=0)
    if data_minima.day <= 1: opt1 = data_minima.replace(day=1)
    elif data_minima.day <= 15: opt1 = data_minima.replace(day=15)
    else: opt1 = (data_minima + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    
    if opt1.day == 1: opt2 = opt1.replace(day=15)
    else: opt2 = (opt1 + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    return opt1, opt2

def gerar_sequencia_datas(data_inicio, num_parcelas, frequencia):
    datas = []
    data_atual = data_inicio
    for i in range(num_parcelas):
        if i == 0:
            datas.append(data_atual.strftime("%d/%m"))
            continue
        if frequencia == "Mensal": data_atual = data_atual + dateutil.relativedelta.relativedelta(months=1)
        else:
            if data_atual.day == 1: data_atual = data_atual.replace(day=15)
            else: data_atual = (data_atual + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
        datas.append(data_atual.strftime("%d/%m"))
    return datas

# --- INTERFACE ---
st.title("🛍️ Gestão de Vendas")

menu = st.sidebar.selectbox("Menu", ["Registrar Venda Nova", "Importar Venda em Andamento", "Histórico de Vendas"])
df = ler_dados_cacheado()

# --- 1. REGISTRO DE VENDA NOVA (LÓGICA ANTERIOR) ---
if menu == "Registrar Venda Nova":
    st.subheader("📝 Novo Registro Automático")
    col1, col2 = st.columns(2)
    with col1:
        cliente = st.text_input("Nome do Cliente")
        valor_total = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01, value=None)
        frequencia = st.radio("Frequência de Pagamento", ["Mensal", "Quinzena"])
        if frequencia == "Quinzena":
            if "opcoes_q" not in st.session_state: st.session_state.opcoes_q = calcular_opcoes_quinzena(datetime.now())
            data_p = st.radio("Primeira parcela?", options=st.session_state.opcoes_q, format_func=lambda x: x.strftime("%d/%m/%Y"))
        else:
            data_p = (datetime.now() + dateutil.relativedelta.relativedelta(months=1))
    with col2:
        num_p = st.number_input("Nº de Parcelas", min_value=1, value=1)
        prod = st.text_area("Produtos")

    if st.button("🚀 Salvar Venda"):
        if cliente and prod and valor_total:
            datas = gerar_sequencia_datas(data_p, num_p, frequencia)
            v_parc = valor_total / num_p
            carne = f"{prod}\nValor Total: R$ {valor_total:.2f}\n\n"
            for d in datas: carne += f"{v_parc:.2f} {d}\n"
            
            nova = pd.DataFrame([{"id": len(df)+1, "cliente": cliente, "produtos": prod, "valor": valor_total, "data": datetime.now().strftime("%d/%m/%Y"), "carne": carne, "status": "Pendente"}])
            conn.update(data=pd.concat([df, nova], ignore_index=True))
            if "opcoes_q" in st.session_state: del st.session_state.opcoes_q
            atualizar_sistema()

# --- 2. IMPORTAR VENDA EM ANDAMENTO (NOVA FUNÇÃO PESADA) ---
elif menu == "Importar Venda em Andamento":
    st.subheader("📥 Importar Vendas do Caderno")
    st.info("Use esta função para cadastrar vendas que já começaram e definir datas manualmente.")
    
    col1, col2 = st.columns(2)
    with col1:
        c_nome = st.text_input("Nome do Cliente")
        c_valor = st.number_input("Valor Total da Venda (R$)", min_value=0.0, step=0.01)
        c_data_original = st.date_input("Data original da compra", datetime.now())
    with col2:
        c_total_p = st.number_input("Total de parcelas combinadas", min_value=1, value=1)
        c_pagas_p = st.number_input("Quantas parcelas ELA JÁ PAGOU?", min_value=0, max_value=int(c_total_p), value=0)
        c_prod = st.text_area("Produtos vendidos")

    st.write("---")
    st.write("📅 **Defina as datas de cada parcela (mesmo as que já foram pagas):**")
    
    # Criamos colunas dinâmicas para as datas das parcelas
    datas_manuais = []
    cols_datas = st.columns(3)
    for i in range(int(c_total_p)):
        with cols_datas[i % 3]:
            d = st.date_input(f"Data Parcela {i+1}", datetime.now() + timedelta(days=i*15), key=f"date_{i}")
            datas_manuais.append(d.strftime("%d/%m"))

    if st.button("📥 Importar para o Sistema", type="primary"):
        if c_nome and c_prod and c_valor > 0:
            v_parc = c_valor / c_total_p
            carne = f"{c_prod}\nValor Total: R$ {c_valor:.2f}\n\n"
            
            for i, d_str in enumerate(datas_manuais):
                pago_str = " (Pago!)" if i < c_pagas_p else ""
                carne += f"{v_parc:.2f} {d_str}{pago_str}\n"
            
            status = "Pago" if c_pagas_p == c_total_p else ("Pagamento Parcial" if c_pagas_p > 0 else "Pendente")
            
            nova = pd.DataFrame([{
                "id": len(df)+1, "cliente": c_nome, "produtos": c_prod, "valor": c_valor, 
                "data": c_data_original.strftime("%d/%m/%Y"), "carne": carne, "status": status
            }])
            
            conn.update(data=pd.concat([df, nova], ignore_index=True))
            st.success(f"Venda de {c_nome} importada com sucesso!")
            atualizar_sistema()

# --- 3. HISTÓRICO E DASHBOARD ---
elif menu == "Histórico de Vendas":
    # Lógica do Dashboard (mantida a anterior)
    hoje = datetime.now()
    mes_atual, ano_atual = hoje.month, hoje.year
    if hoje.day <= 15: inicio, fim = 1, 15
    else: inicio, fim = 16, calendar.monthrange(ano_atual, mes_atual)[1]

    st.subheader(f"📊 Resumo Quinzena ({inicio:02d} a {fim:02d}/{mes_atual:02d})")
    vol, rec = 0.0, 0.0
    if not df.empty:
        for _, row in df.iterrows():
            for linha in str(row['carne']).split('\n'):
                if "/" in linha:
                    try:
                        p = linha.split()
                        v = float(p[0].replace(',', '.'))
                        d, m = int(p[1].split('/')[0]), int(p[1].split('/')[1])
                        if m == mes_atual and inicio <= d <= fim:
                            vol += v
                            if "(Pago!)" in linha: rec += v
                    except: continue
        m1, m2, m3 = st.columns(3)
        m1.metric("Parcelas no Período", f"R$ {vol:.2f}")
        m2.metric("Recebido", f"R$ {rec:.2f}")
        m3.metric("A Receber", f"R$ {vol-rec:.2f}", delta_color="inverse")
    
    st.divider()
    busca = st.text_input("🔍 Buscar Cliente")
    if not df.empty:
        df_f = df[df['cliente'].astype(str).str.contains(busca, case=False)] if busca else df
        for index, row in df_f.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            status_cor = "🔴" if row['status'] == "Pendente" else ("🟢" if row['status'] == "Pago" else "🔵")
            with st.expander(f"{status_cor} {row['cliente']} - R$ {row['valor']:.2f}"):
                st.code(str(row['carne']), language="text")
                c_btn = st.columns([1, 1, 1, 2])
                with c_btn[0]:
                    if "(Pago!)" not in str(row['carne']) or row['status'] != "Pago":
                        if st.button("💰 Pagar", key=f"p_{index}"):
                            linhas = str(row['carne']).split('\n')
                            nova_c, alterou = [], False
                            for l in linhas:
                                if "/" in l and "(Pago!)" not in l and not alterou:
                                    l += " (Pago!)"; alterou = True
                                nova_c.append(l)
                            df.at[index, 'carne'] = "\n".join(nova_c)
                            df.at[index, 'status'] = "Pago" if not any("/" in l and "(Pago!)" not in l for l in nova_c) else "Pagamento Parcial"
                            conn.update(data=df); atualizar_sistema()
                with c_btn[1]:
                    msg = f"Olá {row['cliente']}! Segue o resumo:\n\n{row['carne']}"
                    st.link_button("🟢 WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
                with c_btn[2]:
                    if st.button("🗑️", key=f"d_{index}"):
                        conn.update(data=df.drop(index)); atualizar_sistema()
