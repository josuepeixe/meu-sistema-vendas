import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import dateutil.relativedelta
import urllib.parse
import calendar
import re

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas Master", layout="wide", page_icon="🚀")

# --- CONEXÃO E CACHE ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def ler_vendas():
    try:
        data = conn.read(worksheet="vendas", ttl=0)
        if data.empty:
            return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])
        return data.dropna(how='all').fillna("").astype(str) # Força tudo como texto
    except:
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

@st.cache_data(ttl=10)
def ler_clientes():
    try:
        data = conn.read(worksheet="clientes", ttl=0)
        if data.empty or "nome" not in data.columns:
            return pd.DataFrame(columns=["nome", "telefone", "info"])
        
        # Limpeza crucial: transforma em texto e remove o ".0" fantasma
        df = data.dropna(how='all').fillna("").astype(str)
        df['telefone'] = df['telefone'].apply(lambda x: x.replace(".0", "") if x.endswith(".0") else x)
        return df
    except:
        return pd.DataFrame(columns=["nome", "telefone", "info"])

def atualizar_sistema():
    st.cache_data.clear()
    st.rerun()

# --- FUNÇÕES AUXILIARES ---
def formatar_telefone(num_texto):
    # Converte para string e remove ".0" se existir
    num_str = str(num_texto).replace(".0", "")
    # Remove tudo que não for número
    apenas_numeros = re.sub(r'\D', '', num_str)
    
    if not apenas_numeros: return ""
    
    # Adiciona o 55 se não tiver
    if len(apenas_numeros) <= 11 and not apenas_numeros.startswith("55"):
        apenas_numeros = "55" + apenas_numeros
    return apenas_numeros

def calcular_parcelas_inteiras(total, num_p):
    total_int = int(total)
    base = total_int // num_p
    resto = total_int % num_p
    return [base + 1 if i < resto else base for i in range(num_p)]

def calcular_opcoes_quinzena(data_ref):
    data_min = data_ref + timedelta(days=7)
    data_min = data_min.replace(hour=0, minute=0, second=0, microsecond=0)
    if data_min.day <= 1: opt1 = data_min.replace(day=1)
    elif data_min.day <= 15: opt1 = data_min.replace(day=15)
    else: opt1 = (data_min + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    opt2 = opt1.replace(day=15) if opt1.day == 1 else (opt1 + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    return opt1, opt2

def gerar_sequencia_datas(data_inicio, num_p, freq):
    datas = []
    data_at = data_inicio
    for i in range(num_p):
        if i > 0:
            if freq in ["Mensal", "Cartão (Maquininha)"]: data_at += dateutil.relativedelta.relativedelta(months=1)
            else:
                if data_at.day == 1: data_at = data_at.replace(day=15)
                else: data_at = (data_at + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
        datas.append(data_at.strftime("%d/%m"))
    return datas

# --- NAVEGAÇÃO ---
st.sidebar.title("Navegação")
menu = st.sidebar.selectbox("Menu", 
    ["Registrar Venda Nova", "Registrar Venda em Andamento", "Registrar Cliente", "Histórico de Vendas"]
)

df_vendas = ler_vendas()
df_clientes = ler_clientes()

# --- 1. REGISTRAR VENDA NOVA ---
if menu == "Registrar Venda Nova":
    st.subheader("📝 Novo Registro Automático")
    if df_clientes.empty:
        st.warning("Cadastre um cliente primeiro no menu 'Registrar Cliente'.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            cliente_sel = st.selectbox("Selecione o Cliente", df_clientes['nome'].unique())
            valor_t = st.number_input("Valor Total (R$)", min_value=0.0, step=1.0, value=None)
            freq = st.radio("Forma de Pagamento", ["Mensal", "Quinzena", "Cartão (Maquininha)"])
            if freq == "Quinzena":
                if "opcoes_q" not in st.session_state: st.session_state.opcoes_q = calcular_opcoes_quinzena(datetime.now())
                data_p = st.radio("Primeira parcela?", options=st.session_state.opcoes_q, format_func=lambda x: x.strftime("%d/%m/%Y"))
            else:
                data_p = datetime.now() + dateutil.relativedelta.relativedelta(months=1)
        with col2:
            num_p = st.number_input("Nº de Parcelas", min_value=1, value=1)
            prod = st.text_area("Produtos")

        if st.button("🚀 Salvar Venda", type="primary"):
            if cliente_sel and prod and valor_t:
                datas = gerar_sequencia_datas(data_p, int(num_p), freq)
                valores = calcular_parcelas_inteiras(valor_t, int(num_p))
                carne = f"{prod}\nValor Total: R$ {valor_t:.2f}\n\n"
                for v, d in zip(valores, datas):
                    status_p = " (Pago!)" if freq == "Cartão (Maquininha)" else ""
                    carne += f"{v:.2f} {d}{status_p}\n"
                status_v = "Pago" if freq == "Cartão (Maquininha)" else "Pendente"
                nova_v = pd.DataFrame([{"id": len(df_vendas)+1, "cliente": cliente_sel, "produtos": prod, "valor": valor_t, "data": datetime.now().strftime("%d/%m/%Y"), "carne": carne, "status": status_v}])
                conn.update(worksheet="vendas", data=pd.concat([df_vendas, nova_v], ignore_index=True).astype(str))
                if "opcoes_q" in st.session_state: del st.session_state.opcoes_q
                atualizar_sistema()

# --- 2. REGISTRAR VENDA EM ANDAMENTO ---
elif menu == "Registrar Venda em Andamento":
    st.subheader("📥 Importar Vendas do Caderno")
    if df_clientes.empty:
        st.warning("Cadastre um cliente primeiro!")
    else:
        col1, col2 = st.columns(2)
        with col1:
            cliente_sel = st.selectbox("Selecione o Cliente", df_clientes['nome'].unique())
            c_valor = st.number_input("Valor Total (R$)", min_value=0.0, step=1.0)
            c_data_orig = st.date_input("Data da compra", datetime.now())
        with col2:
            c_total_p = st.number_input("Total de parcelas", min_value=1, value=1)
            c_pagas_p = st.number_input("Quantas JÁ PAGOU?", min_value=0, max_value=int(c_total_p))
            c_prod = st.text_area("Produtos")

        st.write("---")
        datas_manuais = []
        for i in range(0, int(c_total_p), 3):
            cols = st.columns(3)
            for j in range(3):
                idx = i + j
                if idx < int(c_total_p):
                    with cols[j]:
                        d = st.date_input(f"Data P{idx+1}", datetime.now() + timedelta(days=idx*15), key=f"imp_{idx}")
                        datas_manuais.append(d.strftime("%d/%m"))

        if st.button("📥 Importar Venda", type="primary"):
            valores = calcular_parcelas_inteiras(c_valor, int(c_total_p))
            carne = f"{c_prod}\nValor Total: R$ {c_valor:.2f}\n\n"
            for i, (v, d_s) in enumerate(zip(valores, datas_manuais)):
                carne += f"{v:.2f} {d_s}{' (Pago!)' if i < c_pagas_p else ''}\n"
            status = "Pago" if c_pagas_p == c_total_p else ("Pagamento Parcial" if c_pagas_p > 0 else "Pendente")
            nova_v = pd.DataFrame([{"id": len(df_vendas)+1, "cliente": cliente_sel, "produtos": c_prod, "valor": c_valor, "data": c_data_orig.strftime("%d/%m/%Y"), "carne": carne, "status": status}])
            conn.update(worksheet="vendas", data=pd.concat([df_vendas, nova_v], ignore_index=True).astype(str))
            atualizar_sistema()

# --- 3. REGISTRAR CLIENTE ---
elif menu == "Registrar Cliente":
    tab1, tab2 = st.tabs(["➕ Cadastrar Novo", "👥 Ver e Editar"])
    
    with tab1:
        with st.form("form_cliente", clear_on_submit=True):
            nome = st.text_input("Nome Completo")
            tel_input = st.text_input("WhatsApp (DDD + Número)")
            info = st.text_area("Informações")
            if st.form_submit_button("Salvar Cliente"):
                if nome:
                    tel_limpo = formatar_telefone(tel_input)
                    novo_c = pd.DataFrame([{"nome": nome, "telefone": tel_limpo, "info": info}])
                    # Salva forçando tipo string
                    df_final = pd.concat([df_clientes, novo_c], ignore_index=True).astype(str)
                    conn.update(worksheet="clientes", data=df_final)
                    atualizar_sistema()
    
    with tab2:
        if not df_clientes.empty:
            cliente_edit = st.selectbox("Selecione o cliente", df_clientes['nome'].tolist())
            idx_c = df_clientes[df_clientes['nome'] == cliente_edit].index[0]
            with st.form("edit_cliente"):
                new_nome = st.text_input("Nome", value=df_clientes.at[idx_c, 'nome'])
                # Mostra o telefone limpo sem o .0
                tel_atual = str(df_clientes.at[idx_c, 'telefone']).replace(".0", "")
                new_tel = st.text_input("WhatsApp", value=tel_atual)
                new_info = st.text_area("Informações", value=df_clientes.at[idx_c, 'info'])
                
                c_e1, c_e2 = st.columns(2)
                if c_e1.form_submit_button("💾 Salvar"):
                    df_clientes.at[idx_c, 'nome'] = new_nome
                    df_clientes.at[idx_c, 'telefone'] = formatar_telefone(new_tel)
                    df_clientes.at[idx_c, 'info'] = new_info
                    conn.update(worksheet="clientes", data=df_clientes.astype(str))
                    atualizar_sistema()
                if c_e2.form_submit_button("🗑️ Excluir"):
                    conn.update(worksheet="clientes", data=df_clientes.drop(idx_c).astype(str))
                    atualizar_sistema()

# --- 4. HISTÓRICO DE VENDAS ---
elif menu == "Histórico de Vendas":
    hoje = datetime.now()
    mes_at, ano_at = hoje.month, hoje.year
    ini, fim = (1, 15) if hoje.day <= 15 else (16, calendar.monthrange(ano_at, mes_at)[1])
    
    st.subheader(f"📊 Resumo Financeiro ({ini:02d} a {fim:02d}/{mes_at:02d})")
    vol, rec = 0.0, 0.0
    if not df_vendas.empty:
        for _, row in df_vendas.iterrows():
            for linha in str(row['carne']).split('\n'):
                if "/" in linha:
                    try:
                        p = linha.split(); v = float(p[0]); d, m = int(p[1].split('/')[0]), int(p[1].split('/')[1])
                        if m == mes_at and ini <= d <= fim:
                            vol += v
                            if "(Pago!)" in linha: rec += v
                    except: continue
        m1, m2, m3 = st.columns(3)
        m1.metric("Parcelas na Quinzena", f"R$ {vol:.2f}")
        m2.metric("Recebido", f"R$ {rec:.2f}")
        m3.metric("A Receber", f"R$ {vol-rec:.2f}", delta_color="inverse")

    st.divider()
    busca = st.text_input("🔍 Buscar Cliente")
    status_f = st.selectbox("Status", ["Todos", "Pendentes", "Pagamento Parcial", "Pago"])
    
    if not df_vendas.empty:
        df_f = df_vendas[df_vendas['cliente'].astype(str).str.contains(busca, case=False)] if busca else df_vendas
        if status_f != "Todos": df_f = df_f[df_f['status'] == status_f]
            
        for index, row in df_f.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            status_cor = "🔴" if row['status'] == "Pendente" else ("🟢" if row['status'] == "Pago" else "🔵")
            with st.expander(f"{status_cor} {row['cliente']} - R$ {float(row['valor']):.2f}"):
                st.code(str(row['carne']), language="text")
                c_btn = st.columns([1, 1, 1, 2])
                with c_btn[0]:
                    if "(Pago!)" not in str(row['carne']) or row['status'] != "Pago":
                        if st.button("💰 Pagar", key=f"p_{index}"):
                            linhas = str(row['carne']).split('\n')
                            nova_c, alt = [], False
                            for l in linhas:
                                if "/" in l and "(Pago!)" not in l and not alt:
                                    l += " (Pago!)"; alt = True
                                nova_c.append(l)
                            df_vendas.at[index, 'carne'] = "\n".join(nova_c)
                            df_vendas.at[index, 'status'] = "Pago" if not any("/" in l and "(Pago!)" not in l for l in nova_c) else "Pagamento Parcial"
                            conn.update(worksheet="vendas", data=df_vendas.astype(str)); atualizar_sistema()
                
                with c_btn[1]:
                    tel_final = ""
                    if not df_clientes.empty:
                        filtro_tel = df_clientes[df_clientes['nome'] == row['cliente']]['telefone'].values
                        if len(filtro_tel) > 0: tel_final = str(filtro_tel[0]).replace(".0", "")
                    
                    msg_txt = urllib.parse.quote(f"Olá {row['cliente']}! Segue o resumo da sua compra:\n\n{row['carne']}")
                    url_wa = f"https://api.whatsapp.com/send?phone={tel_final}&text={msg_txt}"
                    st.link_button("🟢 WhatsApp", url_wa)

                with c_btn[2]:
                    if st.button("🗑️", key=f"d_{index}"):
                        conn.update(worksheet="vendas", data=df_vendas.drop(index).astype(str)); atualizar_sistema()

# --- CRÉDITOS NA BARRA LATERAL ---
st.sidebar.markdown("---") # Adiciona uma linha horizontal para separar dos filtros
st.sidebar.markdown(
    """
    <div style="text-align: center; padding-top: 10px; padding-bottom: 10px;">
        <p style="font-size: 13px; color: #888; margin-bottom: 5px;">Análise e Desenvolvimento:</p>
        <p style="font-size: 16px; font-weight: bold; margin-bottom: 5px;">Josué Peixe</p>
        <a href="https://www.linkedin.com/in/josu%C3%A9-peixe-94aba93a5/" target="_blank" style="text-decoration: none; color: #00A0DC; font-weight: bold;">
            🔗 Meu Perfil no LinkedIn
        </a>
    </div>
    """,
    unsafe_allow_html=True
)
