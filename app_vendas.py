import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import dateutil.relativedelta

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas - Automação", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# 1. Função de leitura com Cache (TTL)
@st.cache_data(ttl=10) # O Streamlit guarda os dados por 10 segundos
def ler_dados_cacheado():
    try:
        data = conn.read(ttl=0) # Aqui lemos o dado real
        if data is not None:
            data = data.dropna(how='all')
            return data.fillna("")
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])
    except Exception as e:
        if "429" in str(e):
            st.error("⚠️ Limite do Google atingido. Aguarde 15 segundos.")
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

def calcular_opcoes_quinzena(hoje):
    """Calcula as duas próximas datas possíveis (01 ou 15) ignorando as horas"""
    # Remove horas, minutos e segundos para a opção não "mudar" a cada segundo
    hoje = hoje.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if hoje.day < 15:
        opt1 = hoje.replace(day=15)
    else:
        opt1 = (hoje + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    
    if opt1.day == 15:
        opt2 = (opt1 + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    else:
        opt2 = opt1.replace(day=15)
        
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
        else: # Quinzena
            if data_atual.day == 1:
                data_atual = data_atual.replace(day=15)
            else:
                data_atual = (data_atual + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
        
        datas.append(data_atual.strftime("%d/%m"))
    return datas

def atualizar_sistema():
    st.cache_data.clear() # Limpa a memória temporária
    st.rerun() # Recarrega a página com dados novos

# --- INTERFACE ---
st.title("🛍️ Controle de Vendas")

menu = st.sidebar.selectbox("Menu", ["Registrar Venda", "Histórico de Vendas"])
df = ler_dados_cacheado()

if menu == "Registrar Venda":
    st.subheader("📝 Novo Registro")
    
    # (Mantenha os campos de input que já configuramos antes...)
    if "cliente_input" not in st.session_state: st.session_state.cliente_input = ""
    if "valor_input" not in st.session_state: st.session_state.valor_input = 0.0
    if "produtos_input" not in st.session_state: st.session_state.produtos_input = ""

    col1, col2 = st.columns(2)
    with col1:
        cliente = st.text_input("Nome do Cliente", value=st.session_state.cliente_input, key="c_in")
        valor_total = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01, value=st.session_state.valor_input, key="v_in")
        frequencia = st.radio("Frequência", ["Mensal", "Quinzena"])
        
        # Escolha da quinzena (conforme lógica anterior)
        # --- Lógica de Quinzena com "Memória" (Session State) ---
        data_primeira_parcela = None
        if frequencia == "Quinzena":
            # 1. Calculamos as opções apenas UMA VEZ e guardamos na memória
            if "opcoes_quinzena" not in st.session_state:
                hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                opt1, opt2 = calcular_opcoes_quinzena(hoje)
                st.session_state.opcoes_quinzena = [opt1, opt2]

            # 2. O rádio agora usa as opções que estão "congeladas" na memória
            # O 'key' é essencial para o Streamlit não resetar o componente
            escolha_data = st.radio(
                "Quando será a primeira parcela?",
                options=st.session_state.opcoes_quinzena,
                format_func=lambda x: x.strftime("%d/%m/%Y"),
                key="radio_quinzena_fixo" 
            )
            data_primeira_parcela = escolha_data
        else:
            # Se mudar para Mensal, limpamos as opções da memória para que sejam 
            # recalculadas caso você volte para Quinzena depois
            if "opcoes_quinzena" in st.session_state:
                del st.session_state.opcoes_quinzena
            data_primeira_parcela = (datetime.now() + dateutil.relativedelta.relativedelta(months=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    with col2:
        num_parcelas = st.number_input("Nº Parcelas", min_value=1, value=1)
        produtos = st.text_area("Produtos", value=st.session_state.produtos_input, key="p_in")

    if st.button("🚀 Salvar Venda", type="primary"):
        if cliente and produtos and valor_total > 0:
            # (Lógica de gerar carne_texto conforme antes...)
            valor_p = valor_total / num_parcelas
            carne_texto = f"{produtos} {valor_total:.2f}\n\n"
            # ... (seu código de gerar lista_datas) ...
            
            nova_venda = pd.DataFrame([{"id": len(df)+1, "cliente": cliente, "produtos": produtos, "valor": valor_total, "data": datetime.now().strftime("%d/%m/%Y"), "carne": carne_texto, "status": "Pendente"}])
            
            # SALVAR E ATUALIZAR AUTOMATICAMENTE
            conn.update(data=pd.concat([df, nova_venda], ignore_index=True))
            if "opcoes_quinzena" in st.session_state:
                del st.session_state.opcoes_quinzena
            
            st.success("✅ Venda registrada com sucesso!")
            atualizar_sistema()
            
            st.session_state.cliente_input = "" # Limpa campos
            st.session_state.produtos_input = ""
            st.success("Salvo!")
            atualizar_sistema() # <--- AQUI ESTÁ A MÁGICA
        else:
            st.error("Preencha tudo!")

elif menu == "Histórico de Vendas":
    st.subheader("📊 Histórico")
    busca = st.text_input("🔍 Buscar")
    
    if not df.empty:
        df_filtrado = df[df['cliente'].astype(str).str.contains(busca, case=False)] if busca else df
        
        for index, row in df_filtrado.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            
            with st.expander(f"{row['cliente']} - R$ {row['valor']}"):
                st.code(str(row['carne']), language="text")
                
                c1, c2 = st.columns([1, 4])
                with c1:
                    if "(Pago!)" not in str(row['carne']) or row['status'] != "Pago":
                        if st.button(f"Baixar Parcela", key=f"p_{index}"):
                            # ... (Lógica de atualizar o texto do carnê ...)
                            # Supondo que você gerou o 'novo_carne_texto' aqui:
                            # df.at[index, 'carne'] = novo_carne_texto
                            # df.at[index, 'status'] = "Pago" ou "Parcial"
                            
                            conn.update(data=df)
                            atualizar_sistema() # <--- ATUALIZA NA HORA
                with c2:
                    if st.button("🗑️ Excluir", key=f"d_{index}"):
                        df_novo = df.drop(index)
                        conn.update(data=df_novo)
                        atualizar_sistema() # <--- ATUALIZA NA HORA
