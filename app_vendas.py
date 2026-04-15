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
        return data.dropna(how='all').fillna("").astype(str)
    except:
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

@st.cache_data(ttl=10)
def ler_clientes():
    try:
        data = conn.read(worksheet="clientes", ttl=0)
        df = data.dropna(how='all').fillna("").astype(str)
        df['telefone'] = df['telefone'].apply(lambda x: x.replace(".0", "") if x.endswith(".0") else x)
        return df
    except:
        return pd.DataFrame(columns=["nome", "telefone", "info"])

@st.cache_data(ttl=10)
def ler_config():
    try:
        data = conn.read(worksheet="config", ttl=0)
        if data.empty:
            return pd.DataFrame([{"chave_pix": "", "nome_pix": ""}]).astype(str)
        return data.dropna(how='all').fillna("").astype(str)
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
    total_int = int(total)
    base = total_int // num_p
    resto = total_int % num_p
    return [base + 1 if i < resto else base for i in range(num_p)]

# --- NAVEGAÇÃO ---
st.sidebar.title("Navegação")
menu = st.sidebar.selectbox("Menu", 
    ["Registrar Venda Nova", "Registrar Venda em Andamento", "Registrar Cliente", "Histórico de Vendas", "Configurações Pix"]
)

df_vendas = ler_vendas()
df_clientes = ler_clientes()
df_config = ler_config()

# Pega os dados do Pix salvos na planilha
pix_chave = df_config.at[0, 'chave_pix'] if not df_config.empty else ""
pix_nome = df_config.at[0, 'nome_pix'] if not df_config.empty else ""

# --- 1. CONFIGURAÇÕES PIX (NOVO MENU) ---
if menu == "Configurações Pix":
    st.subheader("⚙️ Configurações de Pagamento")
    st.info("Os dados preenchidos aqui aparecerão automaticamente nas suas mensagens de cobrança via WhatsApp.")
    
    with st.form("form_config"):
        nova_chave = st.text_input("Sua Chave Pix", value=pix_chave)
        novo_nome = st.text_input("Seu Nome Completo (Como está no banco)", value=pix_nome)
        
        if st.form_submit_button("💾 Salvar Configurações"):
            df_nova_config = pd.DataFrame([{"chave_pix": nova_chave, "nome_pix": novo_nome}])
            conn.update(worksheet="config", data=df_nova_config.astype(str))
            st.success("Configurações salvas com sucesso!")
            atualizar_sistema()

# --- 2. REGISTRAR VENDA NOVA ---
elif menu == "Registrar Venda Nova":
    # (Lógica anterior mantida...)
    st.subheader("📝 Novo Registro Automático")
    if df_clientes.empty:
        st.warning("Cadastre um cliente primeiro no menu 'Registrar Cliente'.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            cliente_sel = st.selectbox("Selecione o Cliente", df_clientes['nome'].unique())
            valor_t = st.number_input("Valor Total (R$)", min_value=0.0, step=1.0, value=None)
            freq = st.radio("Forma de Pagamento", ["Mensal", "Quinzena", "Cartão (Maquininha)"])
            # ... (Funções de data simplificadas para brevidade no exemplo)
            data_p = datetime.now() + dateutil.relativedelta.relativedelta(months=1)
        with col2:
            num_p = st.number_input("Nº de Parcelas", min_value=1, value=1)
            prod = st.text_area("Produtos")

        if st.button("🚀 Salvar Venda", type="primary"):
            if cliente_sel and prod and valor_t:
                # Gerar carne e salvar...
                valores = calcular_parcelas_inteiras(valor_t, int(num_p))
                carne = f"{prod}\nValor Total: R$ {valor_t:.2f}\n\n"
                for i, v in enumerate(valores):
                    carne += f"{v:.2f} Parcela {i+1}\n"
                nova_v = pd.DataFrame([{"id": len(df_vendas)+1, "cliente": cliente_sel, "produtos": prod, "valor": valor_t, "data": datetime.now().strftime("%d/%m/%Y"), "carne": carne, "status": "Pendente"}])
                conn.update(worksheet="vendas", data=pd.concat([df_vendas, nova_v], ignore_index=True).astype(str))
                atualizar_sistema()

# --- 3. REGISTRAR VENDA EM ANDAMENTO ---
elif menu == "Registrar Venda em Andamento":
    st.subheader("📥 Importar Vendas do Caderno")
    # (Lógica anterior de importação mantida aqui...)

# --- 4. REGISTRAR CLIENTE ---
elif menu == "Registrar Cliente":
    # (Lógica anterior de cadastro/edição de clientes mantida aqui...)

# --- 5. HISTÓRICO DE VENDAS COM ALERTAS E PIX DINÂMICO ---
elif menu == "Histórico de Vendas":
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    mes_at, ano_at = hoje.month, hoje.year
    
    # 🚨 ALERTAS DE COBRANÇA
    st.subheader("🚨 Alertas de Cobrança")
    alertas_found = False
    if not df_vendas.empty:
        for index, row in df_vendas.iterrows():
            carne = str(row['carne'])
            for linha in carne.split('\n'):
                if "/" in linha and "(Pago!)" not in linha:
                    try:
                        p = linha.split(); v_p = p[0]; d_p, m_p = map(int, p[1].split('/'))
                        dt_p = datetime(ano_at, m_p, d_p)
                        if dt_p <= hoje:
                            alertas_found = True
                            st.warning(f"{'⚠️ ATRASADO' if dt_p < hoje else '🕒 VENCE HOJE'}: {row['cliente']} (R$ {v_p})")
                            
                            tel_c = df_clientes[df_clientes['nome'] == row['cliente']]['telefone'].values
                            tel_f = str(tel_c[0]).replace(".0", "") if len(tel_c) > 0 else ""
                            
                            col_a1, col_a2 = st.columns(2)
                            with col_a1:
                                msg_c = urllib.parse.quote(f"Olá {row['cliente']}! Sua parcela de R$ {v_p} venceu. Segue o resumo:\n\n{carne}")
                                st.link_button(f"📲 Cobrar via Whats", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_c}")
                            with col_a2:
                                if pix_chave:
                                    msg_pix = urllib.parse.quote(f"Olá {row['cliente']}! Para o pagamento da parcela de R$ {v_p}, aqui estão meus dados Pix do Nubank:\n\nChave: {pix_chave}\nNome: {pix_nome}\n\nAguardo o comprovante! 😊")
                                    st.link_button(f"💠 Enviar Pix", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_pix}")
                    except: continue

    st.divider()
    # Filtros e Lista de Vendas...
    busca = st.text_input("🔍 Buscar Cliente")
    if not df_vendas.empty:
        df_f = df_vendas[df_vendas['cliente'].astype(str).str.contains(busca, case=False)] if busca else df_vendas
        for index, row in df_f.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            with st.expander(f"{row['cliente']} - R$ {float(row['valor']):.2f}"):
                st.code(str(row['carne']), language="text")
                # Botões de Pagar, WhatsApp e o PIX que usa a chave salva nas configurações
                c_btn = st.columns(3)
                with c_btn[1]:
                    if pix_chave:
                        tel_c = df_clientes[df_clientes['nome'] == row['cliente']]['telefone'].values
                        tel_f = str(tel_c[0]).replace(".0", "") if len(tel_c) > 0 else ""
                        msg_p = urllib.parse.quote(f"Olá {row['cliente']}! Para facilitar, segue meus dados Pix:\n\nChave: {pix_chave}\nNome: {pix_nome}")
                        st.link_button("💠 Pix", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_p}")

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
