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

@st.cache_data(ttl=600) # Aumentado para 10 min para performance
def ler_vendas():
    try:
        data = conn.read(worksheet="vendas", ttl=0)
        if data is None or data.empty:
            return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])
        return data.dropna(how='all')
    except Exception as e:
        st.error(f"Erro ao carregar vendas: {e}")
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

@st.cache_data(ttl=600)
def ler_clientes():
    try:
        data = conn.read(worksheet="clientes", ttl=0)
        if data is None or data.empty:
            return pd.DataFrame(columns=["nome", "telefone", "info"])
        return data.dropna(how='all')
    except Exception as e:
        st.error(f"Erro ao carregar clientes: {e}")
        return pd.DataFrame(columns=["nome", "telefone", "info"])

@st.cache_data(ttl=10)
def ler_config():
    try:
        data = conn.read(worksheet="config", ttl=0)
        df = data.dropna(how='all').fillna("").astype(str)
        if df.empty:
            return pd.DataFrame([{"chave_pix": "", "nome_pix": ""}]).astype(str)
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x).replace(".0", "") if str(x).endswith(".0") else str(x))
        return df
    except:
        return pd.DataFrame([{"chave_pix": "", "nome_pix": ""}]).astype(str)

def atualizar_sistema():
    st.cache_data.clear()
    st.rerun()

# --- FUNÇÕES AUXILIARES ---
def formatar_telefone(num_texto):
    num_str = str(num_texto).replace(".0", "")
    apenas_numeros = re.sub(r'\D', '', num_str)
    if not apenas_numeros: return ""
    if len(apenas_numeros) <= 11 and not apenas_numeros.startswith("55"):
        apenas_numeros = "55" + apenas_numeros
    return apenas_numeros

def calcular_parcelas_inteiras(total, num_p):
    total_int = int(float(total))
    base = total_int // num_p
    resto = total_int % num_p
    return [base + 1 if i < resto else base for i in range(num_p)]

def gerar_pix_texto(chave, nome, valor):
    msg = (
        f"💠 *DADOS PARA PAGAMENTO PIX*\n\n"
        f"💰 *Valor:* R$ {float(valor):.2f}\n"
        f"👤 *Recebedor:* {nome.upper()}\n"
        f"🔑 *Chave:* {chave}\n\n"
        f"----------\n"
        f"Basta usar a chave acima no seu app do banco! 😊"
    )
    return msg

# --- NAVEGAÇÃO ---
st.sidebar.title("Navegação")
menu = st.sidebar.selectbox("Menu", 
    ["Registrar Venda Nova", "Registrar Venda em Andamento", "Registrar Cliente", "Histórico de Vendas", "Configurações Pix"]
)

df_vendas = ler_vendas()
df_clientes = ler_clientes()
df_config = ler_config()

pix_chave = str(df_config.at[0, 'chave_pix']) if not df_config.empty else ""
pix_nome = str(df_config.at[0, 'nome_pix']) if not df_config.empty else ""

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
            data_p = datetime.now() + dateutil.relativedelta.relativedelta(months=1)
        with col2:
            num_p = st.number_input("Nº de Parcelas", min_value=1, value=1)
            prod = st.text_area("Produtos")

        if st.button("🚀 Salvar Venda", type="primary"):
            if not cliente_sel:
                st.error("Selecione um cliente!")
            elif valor_t is None or valor_t <= 0:
                st.error("Insira um valor válido!")
            elif not prod:
                st.error("Descreva os produtos!")
            else:
                valores = calcular_parcelas_inteiras(valor_t, int(num_p))
                carne = f"{prod}\nValor Total: R$ {valor_t:.2f}\n\n"
                for i, v in enumerate(valores):
                    data_f = (data_p + dateutil.relativedelta.relativedelta(months=i)).strftime("%d/%m")
                    carne += f"{v:.2f} {data_f}\n"
                nova_v = pd.DataFrame([{"id": len(df_vendas)+1, "cliente": cliente_sel, "produtos": prod, "valor": valor_t, "data": datetime.now().strftime("%d/%m/%Y"), "carne": carne, "status": "Pendente"}])
                conn.update(worksheet="vendas", data=pd.concat([df_vendas, nova_v], ignore_index=True).astype(str))
                atualizar_sistema()

# --- 2. REGISTRAR VENDA EM ANDAMENTO ---
elif menu == "Registrar Venda em Andamento":
    st.subheader("📥 Importar do Caderno")
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
                    conn.update(worksheet="clientes", data=pd.concat([df_clientes, novo_c], ignore_index=True).astype(str))
                    atualizar_sistema()
    with tab2:
        if not df_clientes.empty:
            cliente_edit = st.selectbox("Selecione o cliente para editar", df_clientes['nome'].tolist())
            idx_c = df_clientes[df_clientes['nome'] == cliente_edit].index[0]
            with st.form("edit_cliente"):
                new_nome = st.text_input("Nome", value=df_clientes.at[idx_c, 'nome'])
                new_tel = st.text_input("WhatsApp", value=str(df_clientes.at[idx_c, 'telefone']))
                new_info = st.text_area("Informações", value=df_clientes.at[idx_c, 'info'])
                if st.form_submit_button("💾 Salvar"):
                    df_clientes.at[idx_c, 'nome'] = new_nome
                    df_clientes.at[idx_c, 'telefone'] = formatar_telefone(new_tel)
                    df_clientes.at[idx_c, 'info'] = new_info
                    conn.update(worksheet="clientes", data=df_clientes.astype(str)); atualizar_sistema()

# --- 4. HISTÓRICO DE VENDAS ---
elif menu == "Histórico de Vendas":
    hoje = datetime.now()
    hoje_check = hoje.replace(hour=0, minute=0, second=0, microsecond=0)
    mes_at, ano_at = hoje.month, hoje.year
    ini_q, fim_q = (1, 15) if hoje.day <= 15 else (16, calendar.monthrange(ano_at, mes_at)[1])
    
    # 🚨 ALERTAS
    st.subheader("🚨 Alertas de Cobrança")
    alertas_found = False
    if not df_vendas.empty:
        for idx_alerta, (index, row) in enumerate(df_vendas.iterrows()):
            carne = str(row['carne'])
            for linha in carne.split('\n'):
                if "/" in linha and "(Pago!)" not in linha:
                    try:
                        p = linha.split()
                        v_p = p[0]
                        d_p, m_p = map(int, p[1].split('/'))

                        # Lógica dinâmica: usa o ano atual (ano_at) que você já definiu no topo do menu
                        ano_referencia = ano_at 

                        # Segurança: Se a parcela for de Janeiro (1) e hoje for Dezembro (12), 
                        # o sistema entende que a parcela é do ano que vem.
                        if m_p < mes_at and mes_at == 12:
                            ano_referencia += 1

                        dt_p = datetime(ano_referencia, m_p, d_p)
                        if dt_p <= hoje_check:
                            alertas_found = True
                            st.warning(f"Atraso: {row['cliente']} (R$ {p[0]} em {p[1]})")
                            tel_c = df_clientes[df_clientes['nome'] == row['cliente']]['telefone'].values
                            tel_f = str(tel_c[0]) if len(tel_c) > 0 else ""
                            
                            c_alt1, c_alt2 = st.columns(2)
                            with c_alt1:
                                msg_c = urllib.parse.quote(f"Olá {row['cliente']}! Sua parcela de R$ {p[0]} venceu em {p[1]}. Segue o resumo:\n\n{carne}")
                                st.link_button(f"📲 Cobrar {row['cliente']}", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_c}")
                            with c_alt2:
                                if pix_chave:
                                    msg_pix = urllib.parse.quote(gerar_pix_texto(pix_chave, pix_nome, p[0]))
                                    st.link_button("💠 Enviar Pix", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_pix}")
                    except: continue
    if not alertas_found: st.success("✅ Tudo em dia!")

    st.divider()

    # 📊 RELATÓRIO
    st.subheader(f"📊 Resumo Financeiro da Quinzena ({ini_q:02d} a {fim_q:02d}/{mes_at:02d})")
    vol, rec = 0.0, 0.0
    if not df_vendas.empty:
        for _, row in df_vendas.iterrows():
            for linha in str(row['carne']).split('\n'):
                if "/" in linha:
                    try:
                        p = linha.split(); v = float(p[0]); d, m = map(int, p[1].split('/'))
                        if m == mes_at and ini_q <= d <= fim_q:
                            vol += v
                            if "(Pago!)" in linha: rec += v
                    except: continue
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Parcelas no Período", f"R$ {vol:.2f}")
        m2.metric("Recebido", f"R$ {rec:.2f}")
        m3.metric("A Receber", f"R$ {vol-rec:.2f}", delta_color="inverse")
    
    st.divider()
    busca = st.text_input("🔍 Buscar Cliente no Histórico")
    
    if not df_vendas.empty:
        df_f = df_vendas[df_vendas['cliente'].astype(str).str.contains(busca, case=False)] if busca else df_vendas
        
        for i, (index, row) in enumerate(df_f.iterrows()):
            edit_key = f"edit_mode_{row['id']}_{i}" 
            if edit_key not in st.session_state: st.session_state[edit_key] = False

            with st.expander(f"{row['cliente']} - R$ {row['valor']} (Venda em {row['data']})"):
                if st.session_state[edit_key]:
                    st.info("💡 Modo de edição ativo.")
                    novo_valor = st.number_input("Valor Total", value=float(row['valor']), key=f"v_edit_{row['id']}_{i}")
                    novo_carne = st.text_area("Detalhamento", value=row['carne'], height=200, key=f"c_edit_{row['id']}_{i}")
                    
                    col_save1, col_save2 = st.columns(2)
                    if col_save1.button("💾 Salvar", key=f"save_{row['id']}_{i}", type="primary"):
                        df_vendas.at[index, 'valor'] = str(novo_valor)
                        df_vendas.at[index, 'carne'] = novo_carne
                        conn.update(worksheet="vendas", data=df_vendas.astype(str))
                        st.session_state[edit_key] = False
                        atualizar_sistema()
                    if col_save2.button("❌ Cancelar", key=f"cancel_{row['id']}_{i}"):
                        st.session_state[edit_key] = False
                        st.rerun()
                else:
                    st.code(row['carne'])
                    
                    # ADICIONADO: Botão de excluir na 5ª coluna
                    c_h = st.columns([1, 1, 1, 1, 1]) 
                    with c_h[0]: # PAGAR
                        if st.button("💰", key=f"p_{row['id']}_{i}"):
                            linhas = str(row['carne']).split('\n')
                            nova_c, alt = [], False
                            for l in linhas:
                                if "/" in l and "(Pago!)" not in l and not alt:
                                    l += " (Pago!)"; alt = True
                                nova_c.append(l)
                            df_vendas.at[index, 'carne'] = "\n".join(nova_c)
                            df_vendas.at[index, 'status'] = "Pago" if not any("/" in l and "(Pago!)" not in l for l in nova_c) else "Pagamento Parcial"
                            conn.update(worksheet="vendas", data=df_vendas.astype(str)); atualizar_sistema()
                    with c_h[1]: # EDITAR
                        if st.button("✏️", key=f"btn_edit_{row['id']}_{i}"):
                            st.session_state[edit_key] = True
                            st.rerun()
                    with c_h[2]: # WHATSAPP
                        tel_c = df_clientes[df_clientes['nome'] == row['cliente']]['telefone'].values
                        tel_f = str(tel_c[0]) if len(tel_c) > 0 else ""
                        msg = urllib.parse.quote(f"Olá {row['cliente']}! Resumo da compra:\n\n{row['carne']}")
                        st.link_button("🟢", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg}")
                    with c_h[3]: # PIX
                        if pix_chave:
                            msg_pix = urllib.parse.quote(gerar_pix_texto(pix_chave, pix_nome, row['valor']))
                            st.link_button("💠", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_pix}")
                    with c_h[4]: # EXCLUIR (O botão que voltou!)
                        with st.popover("🗑️"):
                            st.warning("Excluir esta venda?")
                            if st.button("Sim, apagar", key=f"conf_del_{row['id']}_{i}", type="primary"):
                                df_vendas = df_vendas.drop(index)
                                conn.update(worksheet="vendas", data=df_vendas.astype(str))
                                st.success("Excluído!")
                                atualizar_sistema()

# --- 5. CONFIGURAÇÕES PIX ---
elif menu == "Configurações Pix":
    st.subheader("⚙️ Configurações Pix")
    with st.form("form_config"):
        nova_ch = st.text_input("Chave Pix", value=pix_chave)
        novo_no = st.text_input("Nome no Banco", value=pix_nome)
        if st.form_submit_button("💾 Salvar"):
            df_n = pd.DataFrame([{"chave_pix": str(nova_ch), "nome_pix": str(novo_no)}]).astype(str)
            conn.update(worksheet="config", data=df_n); atualizar_sistema()

# --- CRÉDITOS ---
st.sidebar.markdown("---")
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
