import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import dateutil.relativedelta
import urllib.parse
import calendar

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas - Fluxo Quinzenal", layout="wide", page_icon="💰")

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
        else:
            st.error("Preencha todos os campos.")

# --- HISTÓRICO E DASHBOARD QUINZENAL ---
elif menu == "Histórico de Vendas":
    # 📊 LÓGICA DO DASHBOARD QUINZENAL
    hoje = datetime.now()
    mes_atual = hoje.month
    ano_atual = hoje.year
    
    if hoje.day <= 15:
        inicio_periodo = 1
        fim_periodo = 15
        texto_periodo = f"01/{mes_atual:02d} a 15/{mes_atual:02d}"
    else:
        inicio_periodo = 16
        fim_periodo = calendar.monthrange(ano_atual, mes_atual)[1]
        texto_periodo = f"16/{mes_atual:02d} a {fim_periodo}/{mes_atual:02d}"

    st.subheader(f"📊 Resumo Financeiro da Quinzena ({texto_periodo})")
    
    vol_periodo = 0.0
    rec_periodo = 0.0
    
    if not df.empty:
        for _, row in df.iterrows():
            carne = str(row['carne'])
            linhas = carne.split('\n')
            for linha in linhas:
                if "/" in linha: # Identifica que é uma linha de parcela
                    try:
                        partes = linha.split()
                        valor_parc = float(partes[0].replace(',', '.'))
                        data_parc_str = partes[1] # Formato DD/MM
                        dia_parc = int(data_parc_str.split('/')[0])
                        mes_parc = int(data_parc_str.split('/')[1])
                        
                        # Verifica se a parcela pertence ao mês e quinzena atual
                        if mes_parc == mes_atual and inicio_periodo <= dia_parc <= fim_periodo:
                            vol_periodo += valor_parc
                            if "(Pago!)" in linha:
                                rec_periodo += valor_parc
                    except:
                        continue
        
        pend_periodo = vol_periodo - rec_periodo
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Parcelas na Quinzena", f"R$ {vol_periodo:.2f}")
        m2.metric("Recebido (Nesta Quinzena)", f"R$ {rec_periodo:.2f}")
        m3.metric("A Receber (Nesta Quinzena)", f"R$ {pend_periodo:.2f}", delta_color="inverse")
    
    st.divider()
    
    # 🔍 FILTROS E LISTA
    st.subheader("📂 Lista de Vendas")
    busca = st.text_input("🔍 Buscar Cliente")
    filtro_status = st.selectbox("Filtrar Status", ["Todos", "Pendentes", "Pagamento Parcial", "Pago"])

    if not df.empty:
        df_f = df.copy()
        if busca:
            df_f = df_f[df_f['cliente'].astype(str).str.contains(busca, case=False)]
        if filtro_status != "Todos":
            df_f = df_f[df_f['status'] == filtro_status]

        for index, row in df_f.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            status_cor = "🔴" if row['status'] == "Pendente" else "🟢"
            if row['status'] == "Pagamento Parcial": status_cor = "🔵"
            
            with st.expander(f"{status_cor} {row['cliente']} - R$ {row['valor']:.2f}"):
                st.code(str(row['carne']), language="text")
                
                col_btn = st.columns([1, 1, 1, 2])
                with col_btn[0]:
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
                
                with col_btn[1]:
                    msg = f"Olá {row['cliente']}! Segue o resumo da sua compra:\n\n{row['carne']}"
                    st.link_button("🟢 WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")

                with col_btn[2]:
                    if st.button("🗑️", key=f"d_{index}"):
                        df_novo = df.drop(index)
                        conn.update(data=df_novo)
                        atualizar_sistema()
