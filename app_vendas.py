import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import dateutil.relativedelta

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas Pro", layout="wide", page_icon="🛍️")

# --- CONEXÃO E CACHE ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def ler_dados_cacheado():
    try:
        data = conn.read(ttl=0)
        if data is not None:
            # Remove linhas totalmente vazias e trata erros de 'nan'
            data = data.dropna(how='all')
            return data.fillna("")
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])
    except Exception as e:
        if "429" in str(e):
            st.error("⚠️ Limite do Google atingido. Aguarde alguns segundos.")
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

def atualizar_sistema():
    """Limpa o cache e recarrega a página para mostrar dados novos"""
    st.cache_data.clear()
    st.rerun()

# --- FUNÇÕES DE LÓGICA DE DATAS ---
def calcular_opcoes_quinzena(hoje):
    """Calcula as duas próximas datas de quinzena (01 ou 15)"""
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
        else:
            if data_atual.day == 1:
                data_atual = data_atual.replace(day=15)
            else:
                data_atual = (data_atual + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
        datas.append(data_atual.strftime("%d/%m"))
    return datas

# --- INTERFACE PRINCIPAL ---
st.title("🛍️ Controle de Vendas - Revendedora")

# Sidebar
if st.sidebar.button("🔄 Atualizar Dados"):
    atualizar_sistema()

menu = st.sidebar.selectbox("Menu", ["Registrar Venda", "Histórico de Vendas"])
df = ler_dados_cacheado()

# --- FLUXO DE REGISTRO ---
if menu == "Registrar Venda":
    st.subheader("📝 Novo Registro de Venda")
    
    # Inicialização do estado dos campos
    if "c_in" not in st.session_state: st.session_state.c_in = ""
    if "p_in" not in st.session_state: st.session_state.p_in = ""
    if "v_in" not in st.session_state: st.session_state.v_in = 0.0

    col1, col2 = st.columns(2)
    with col1:
        cliente = st.text_input("Nome do Cliente", key="c_field")
        valor_total = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01, key="v_field", value=None)
        frequencia = st.radio("Frequência de Pagamento", ["Mensal", "Quinzena"], key="freq_field")
        
        data_primeira_parcela = None
        if frequencia == "Quinzena":
            # Uso de session_state para as opções de data não resetarem
            if "opcoes_q" not in st.session_state:
                st.session_state.opcoes_q = calcular_opcoes_quinzena(datetime.now())
            
            data_primeira_parcela = st.radio(
                "Quando será a primeira parcela?",
                options=st.session_state.opcoes_q,
                format_func=lambda x: x.strftime("%d/%m/%Y"),
                key="radio_quinzena_fixo"
            )
        else:
            if "opcoes_q" in st.session_state: del st.session_state.opcoes_q
            data_primeira_parcela = (datetime.now() + dateutil.relativedelta.relativedelta(months=1))

    with col2:
        num_parcelas = st.number_input("Nº de Parcelas", min_value=1, max_value=24, value=1, key="n_field")
        produtos = st.text_area("Produtos e Detalhes", key="p_field")

    if st.button("🚀 Registrar Venda e Gerar Carnê", type="primary"):
        if cliente and produtos and valor_total > 0:
            lista_datas = gerar_sequencia_datas(data_primeira_parcela, num_parcelas, frequencia)
            valor_p = valor_total / num_parcelas
            
            # Gerando o texto do carnê
            carne_texto = f"{produtos}\nValor Total: R$ {valor_total:.2f}\n\n"
            for d in lista_datas:
                carne_texto += f"{valor_p:.2f} {d}\n"
            
            nova_venda = pd.DataFrame([{
                "id": len(df) + 1,
                "cliente": cliente,
                "produtos": produtos,
                "valor": valor_total,
                "data": datetime.now().strftime("%d/%m/%Y"),
                "carne": carne_texto,
                "status": "Pendente"
            }])
            
            # Salvando
            df_final = pd.concat([df, nova_venda], ignore_index=True)
            conn.update(data=df_final)
            
            st.success("✅ Venda salva na planilha!")
            if "opcoes_q" in st.session_state: del st.session_state.opcoes_q
            atualizar_sistema()
        else:
            st.error("⚠️ Preencha todos os campos obrigatórios.")

# --- FLUXO DE HISTÓRICO ---
elif menu == "Histórico de Vendas":
    st.subheader("📊 Histórico e Baixas")
    busca = st.text_input("🔍 Buscar Cliente")
    
    if not df.empty:
        # Filtro de busca (seguro contra nulos)
        df_filtrado = df[df['cliente'].astype(str).str.contains(busca, case=False)] if busca else df
        
        for index, row in df_filtrado.iterrows():
            if not row['cliente'] or str(row['cliente']).lower() == "nan": continue
            
            status_cor = "🔴" if row['status'] == "Pendente" else "🟢"
            if row['status'] == "Pagamento Parcial": status_cor = "🔵"
            
            texto_carne = str(row['carne']) if row['carne'] else "Carnê vazio."

            with st.expander(f"{status_cor} {row['cliente']} - Criado em: {row['data']}"):
                st.code(texto_carne, language="text")
                
                c1, c2 = st.columns([1, 4])
                with c1:
                    # Só mostra botão de pagar se houver parcelas pendentes
                    if "(Pago!)" not in texto_carne or row['status'] != "Pago":
                        if st.button(f"Pagar Parcela", key=f"btn_p_{index}"):
                            linhas = texto_carne.split('\n')
                            novo_carne = []
                            alterou = False
                            for l in linhas:
                                if "/" in l and "(Pago!)" not in l and not alterou:
                                    l += " (Pago!)"
                                    alterou = True
                                novo_carne.append(l)
                            
                            texto_final = "\n".join(novo_carne)
                            pendente = any("/" in l and "(Pago!)" not in l for l in novo_carne)
                            
                            df.at[index, 'carne'] = texto_final
                            df.at[index, 'status'] = "Pago" if not pendente else "Pagamento Parcial"
                            conn.update(data=df)
                            atualizar_sistema()
                with c2:
                    if st.button("🗑️ Excluir Venda", key=f"btn_d_{index}"):
                        df_novo = df.drop(index)
                        conn.update(data=df_novo)
                        atualizar_sistema()
        
        st.divider()
        st.metric("Total Acumulado em Vendas", f"R$ {df['valor'].sum():.2f}")
    else:
        st.info("Nenhuma venda encontrada na planilha.")
