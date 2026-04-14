import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import dateutil.relativedelta

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas - Carnê Pro", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def ler_dados():
    try:
        return conn.read(ttl=0)
    except:
        # Caso a planilha esteja vazia ou sem cabeçalho
        return pd.DataFrame(columns=["id", "cliente", "produtos", "valor", "data", "carne", "status"])

def calcular_opcoes_quinzena(hoje):
    """Calcula as duas próximas datas possíveis (01 ou 15)"""
    # Opção 1: Próxima quinzena imediata
    if hoje.day < 15:
        opt1 = hoje.replace(day=15)
    else:
        opt1 = (hoje + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
    
    # Opção 2: A quinzena depois da opt1
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

# --- INTERFACE ---
st.title("🛍️ Controle de Vendas - Revendedora")

menu = st.sidebar.selectbox("Menu", ["Registrar Venda", "Histórico de Vendas"])
df = ler_dados()

if menu == "Registrar Venda":
    st.subheader("📝 Novo Registro de Venda")
    
    # Inicializamos os campos no estado da sessão para podermos limpá-los manualmente
    if "cliente_input" not in st.session_state:
        st.session_state.cliente_input = ""
    if "valor_input" not in st.session_state:
        st.session_state.valor_input = 0.0
    if "produtos_input" not in st.session_state:
        st.session_state.produtos_input = ""

    # Campos de entrada
    col1, col2 = st.columns(2)
    with col1:
        cliente = st.text_input("Nome do Cliente", value=st.session_state.cliente_input, key="c_in")
        valor_total = st.number_input("Valor Total (R$)", min_value=0.0, step=0.01, value=st.session_state.valor_input, key="v_in")
        
        # O rádio de frequência agora reage INSTANTANEAMENTE
        frequencia = st.radio("Frequência de Pagamento", ["Mensal", "Quinzena"])
        
        data_primeira_parcela = None
        if frequencia == "Quinzena":
            opt1, opt2 = calcular_opcoes_quinzena(datetime.now())
            # Agora as opções aparecem assim que você clica em 'Quinzena'
            escolha_data = st.radio(
                "Quando será a primeira parcela?",
                options=[opt1, opt2],
                format_func=lambda x: x.strftime("%d/%m/%Y")
            )
            data_primeira_parcela = escolha_data
        else:
            data_primeira_parcela = datetime.now() + dateutil.relativedelta.relativedelta(months=1)

    with col2:
        num_parcelas = st.number_input("Nº de Parcelas", min_value=1, max_value=24, value=1)
        produtos = st.text_area("Produtos (ex: 1 kit essencial)", value=st.session_state.produtos_input, key="p_in")

    # Botão de salvar fora de um formulário
    if st.button("🚀 Registrar Venda e Gerar Carnê", type="primary"):
        if cliente and produtos and valor_total > 0:
            lista_datas = gerar_sequencia_datas(data_primeira_parcela, num_parcelas, frequencia)
            valor_p = valor_total / num_parcelas
            
            carne_texto = f"{produtos} {valor_total:.2f}\n\n"
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
            
            # Salvar no Google Sheets
            df_atualizado = pd.concat([df, nova_venda], ignore_index=True)
            conn.update(data=df_atualizado)
            
            st.success("✅ Venda registrada com sucesso!")
            
            # Limpamos os campos manualmente após o sucesso
            st.session_state.cliente_input = ""
            st.session_state.valor_input = 0.0
            st.session_state.produtos_input = ""
            
            # Força a atualização da tela para limpar os campos
            st.rerun()
        else:
            st.error("⚠️ Por favor, preencha o nome, produtos e valor antes de salvar.")

elif menu == "Histórico de Vendas":
    st.subheader("📊 Histórico e Baixas")
    busca = st.text_input("🔍 Buscar Cliente")
    
    if not df.empty:
        df_filtrado = df[df['cliente'].str.contains(busca, case=False)] if busca else df
        
        for index, row in df_filtrado.iterrows():
            status_cor = "🔴" if row['status'] == "Pendente" else "🟢"
            if row['status'] == "Pagamento Parcial": status_cor = "🔵"
            
            with st.expander(f"{status_cor} {row['cliente']} - Criado em: {row['data']}"):
                st.code(row['carne'], language="text")
                
                c1, c2 = st.columns([1, 4])
                with c1:
                    if "(Pago!)" not in row['carne'] or row['status'] != "Pago":
                        if st.button(f"Baixar Parcela", key=f"p_{index}"):
                            linhas = row['carne'].split('\n')
                            novo_carne = []
                            alterou = False
                            
                            for linha in linhas:
                                if "/" in linha and "(Pago!)" not in linha and not alterou:
                                    linha += " (Pago!)"
                                    alterou = True
                                novo_carne.append(linha)
                            
                            texto_final = "\n".join(novo_carne)
                            tem_pendente = any("/" in l and "(Pago!)" not in l for l in novo_carne)
                            
                            df.at[index, 'carne'] = texto_final
                            df.at[index, 'status'] = "Pago" if not tem_pendente else "Pagamento Parcial"
                            conn.update(data=df)
                            st.rerun()
                with c2:
                    if st.button("🗑️ Excluir", key=f"d_{index}"):
                        df = df.drop(index)
                        conn.update(data=df)
                        st.rerun()
