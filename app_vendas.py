import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import dateutil.relativedelta
import urllib.parse
import calendar
import re
import json

# Configuração da página
st.set_page_config(page_title="Gestão de Vendas Master", layout="wide", page_icon="🚀")

# --- CONEXÃO E CACHE ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=600) # Aumentado para 10 min para performance
def buscar_dados_brutos():
    """Busca os dados brutos do Sheets (Cache Global)."""
    v = conn.read(worksheet="vendas", ttl=0)
    c = conn.read(worksheet="clientes", ttl=0)
    cfg = conn.read(worksheet="config", ttl=0)
    return v, c, cfg

def limpar_dataframe(df):
    """Função única para limpeza (Sugestão 1 - DRY)."""
    if df is None or df.empty: 
        return pd.DataFrame()
    # Converte para string e remove o .0 de uma vez (Vetorizado)
    df = df.fillna("").astype(str)
    return df.apply(lambda x: x.str.replace(r'\.0$', '', regex=True))

# Inicialização do Estado da Sessão (Sugestão 3)
if 'df_vendas' not in st.session_state:
    v_raw, c_raw, cfg_raw = buscar_dados_brutos()
    st.session_state['df_vendas'] = limpar_dataframe(v_raw)
    st.session_state['df_clientes'] = limpar_dataframe(c_raw)
    st.session_state['df_config'] = limpar_dataframe(cfg_raw)
    
    # --- 4. MELHORIA DE COMPLEXIDADE DE BUSCA ---
    # Cria um dicionário {Nome: Telefone} para busca instantânea
    st.session_state['dict_telefones'] = dict(zip(
        st.session_state['df_clientes']['nome'], 
        st.session_state['df_clientes']['telefone']
    ))

# Atalhos para facilitar o uso no código
df_vendas = st.session_state['df_vendas']
df_clientes = st.session_state['df_clientes']
df_config = st.session_state['df_config']
dict_telefones = st.session_state['dict_telefones']

def atualizar_sistema():
    """Limpa cache e estado para forçar recarregamento."""
    st.cache_data.clear()
    for key in ['df_vendas', 'df_clientes', 'df_config', 'dict_telefones']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# --- FUNÇÕES AUXILIARES ---
def extrair_valores_carne(carne_texto):
    """Extrai total e pago do texto sem loops pesados."""
    linhas = str(carne_texto).split('\n')
    v_total = 0.0
    v_pago = 0.0
    for l in linhas:
        if "/" in l:
            try:
                p = l.split()
                valor = float(p[0])
                v_total += valor
                if "(Pago!)" in l:
                    v_pago += valor
            except: continue
    return v_total, v_pago

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
        f"💠 *DADOS PARA PAGAMENTO PIX* 💠\n\n"
        f"Olá! Aqui estão os dados para facilitar o seu pagamento:\n\n"
        f"💰 *Valor:* R$ {float(valor):.2f}\n"
        f"👤 *Recebedor:* {nome.upper()}\n"
        f"🔑 *Chave:* `{chave}`\n\n"
        f"------------------------------------------\n"
        f"💡 *Dica:* Copie a chave acima e utilize a opção 'Pix Copia e Cola' ou 'Chave Pix' no seu banco.\n\n"
        f"Após realizar o pagamento, se puder me enviar o comprovante, eu já atualizo aqui no sistema! 😊"
    )
    return msg

# --- NAVEGAÇÃO ---
st.sidebar.title("Navegação")
menu = st.sidebar.selectbox("Menu", 
    ["Registrar Venda Nova", "Registrar Venda em Andamento", "Registrar Cliente", "Histórico de Vendas", "Configurações Pix"]
)

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
            
            # --- O MENU QUE VOLTOU: Lógica de Quinzena ---
            if freq == "Quinzena":
                dia_base = st.selectbox("Dia Base da Quinzena (Próximo Mês)", [1, 15])
                # Ajusta a data inicial para o dia 1 ou 15 do mês que vem
                data_p = (datetime.now() + dateutil.relativedelta.relativedelta(months=1)).replace(day=dia_base)
            else:
                # Padrão mensal: Mesma data de hoje, no mês que vem
                data_p = datetime.now() + dateutil.relativedelta.relativedelta(months=1)

        with col2:
            num_p = st.number_input("Nº de Parcelas", min_value=1, value=1)
            prod = st.text_area("Produtos")

        if st.button("🚀 Salvar Venda", type="primary"):
            if cliente_sel and valor_t and prod:
                valores = calcular_parcelas_inteiras(valor_t, int(num_p))
                
                # Nova lógica JSON
                lista_parcelas = []
                data_corrente = data_p
                
                for i in range(int(num_p)):
                    lista_parcelas.append({
                        "n": i + 1,
                        "v": float(valores[i]),
                        "d": data_corrente.strftime("%d/%m"),
                        "p": False  # Inicia como não pago
                    })
                    
                    # Lógica de data (Quinzena ou Mensal)
                    if freq == "Quinzena":
                        if data_corrente.day == 1:
                            data_corrente = data_corrente.replace(day=15)
                        else:
                            data_corrente = (data_corrente + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
                    else:
                        data_corrente = data_corrente + dateutil.relativedelta.relativedelta(months=1)
        
                id_novo = int(df_vendas['id'].astype(int).max()) + 1 if not df_vendas.empty else 1
                nova_v = pd.DataFrame([{
                    "id": id_novo, 
                    "cliente": cliente_sel, 
                    "produtos": prod, 
                    "valor": valor_t, 
                    "data": datetime.now().strftime("%d/%m/%Y"), 
                    "carne": json.dumps(lista_parcelas), # Salva como JSON
                    "status": "Pendente"
                }])
                conn.update(worksheet="vendas", data=pd.concat([df_vendas, nova_v], ignore_index=True).astype(str))
                atualizar_sistema()

# --- 2. REGISTRAR VENDA EM ANDAMENTO ---
elif menu == "Registrar Venda em Andamento":
    st.subheader("📥 Importar do Caderno")
    if df_clientes.empty: st.warning("Cadastre um cliente primeiro!")
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
            
            id_novo = int(df_vendas['id'].astype(int).max()) + 1 if not df_vendas.empty else 1
            status = "Pago" if c_pagas_p == c_total_p else ("Pagamento Parcial" if c_pagas_p > 0 else "Pendente")
            nova_v = pd.DataFrame([{"id": id_novo, "cliente": cliente_sel, "produtos": c_prod, "valor": c_valor, "data": c_data_orig.strftime("%d/%m/%Y"), "carne": carne, "status": status}])
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
    
    st.subheader("🚨 Alertas de Cobrança")
    alertas_found = False
    if not df_vendas.empty:
        for idx_alerta, (index, row) in enumerate(df_vendas.iterrows()):
            # 1. Transforma o JSON da planilha em lista do Python
            try:
                parcelas = json.loads(row['carne'])
            except:
                continue # Pula caso a linha não seja um JSON válido

            for p in parcelas:
                # 2. Verifica se a parcela NÃO está paga (p['p'] == False)
                if not p['p']:
                    try:
                        # p['d'] contém a data (ex: "15/05")
                        d_p, m_p = map(int, p['d'].split('/'))
                        ano_ref = ano_at + 1 if m_p < mes_at and mes_at == 12 else ano_at
                        dt_p = datetime(ano_ref, m_p, d_p)
                        
                        if dt_p <= hoje_check:
                            alertas_found = True
                            st.warning(f"Atraso: {row['cliente']} (R$ {p['v']} em {p['d']})")
                            
                            tel_f = dict_telefones.get(row['cliente'], "")
                            
                            # 3. Criamos o resumo em texto apenas para a mensagem do WhatsApp
                            carne_formatada = ""
                            for parc in parcelas:
                                # Ícones: ✅ para pago, ⏳ para o que falta pagar
                                icone = "✅" if parc['p'] else "⏳"
                                status_txt = " (Pago)" if parc['p'] else ""
                                
                                # Monta a linha: ✅ R$ 250.00 - 15/05 (Pago)
                                carne_formatada += f"{icone} R$ {parc['v']:.2f} - {parc['d']}{status_txt}\n"

                            c1, c2 = st.columns(2)
                            with c1:
                                texto_cobranca = (
                                    f"⚠️ *AVISO DE VENCIMENTO* ⚠️\n\n"
                                    f"Olá, *{row['cliente']}*! Tudo bem?\n"
                                    f"Notamos uma pendência em sua compra:\n\n"
                                    f"📅 *Data da Venda:* {row['data']}\n"
                                    f"📦 *Produtos:* {row['produtos']}\n"
                                    f"💰 *Valor Total da Compra:* R$ {float(row['valor']):.2f}\n"
                                    f"------------------------------------------\n"
                                    f"📌 *DETALHE DA PARCELA VENCIDA:*\n"
                                    f"💵 *Valor:* R$ {p['v']:.2f}\n"
                                    f"📅 *Vencimento:* {p['d']}\n"
                                    f"------------------------------------------\n"
                                    f"📑 *SITUAÇÃO DO SEU CARNÊ:*\n"
                                    f"```\n{carne_formatada}```\n"
                                    f"------------------------------------------\n\n"
                                    f"Poderia nos confirmar se o pagamento já foi feito? Se precisar do PIX, é só avisar! 😊"
                                )
                                
                                msg_c = urllib.parse.quote(texto_cobranca)
                                st.link_button(f"📲 Cobrar {row['cliente']}", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_c}")
                            
                            with c2:
                                if pix_chave:
                                    # p['v'] é o valor numérico da parcela atrasada
                                    msg_pix = urllib.parse.quote(gerar_pix_texto(pix_chave, pix_nome, p['v']))
                                    st.link_button("💠 Enviar Pix", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_pix}")
                    except: 
                        continue

    if not alertas_found: 
        st.success("✅ Tudo em dia!")

    st.divider()

    # 📊 RELATÓRIO
    st.subheader(f"📊 Resumo Financeiro da Quinzena")
    vol, rec = 0.0, 0.0
    if not df_vendas.empty:
        # Usamos o helper do carnê para somar tudo (Sugestão 5)
        for _, row in df_vendas.iterrows():
            linhas = str(row['carne']).split('\n')
            for l in linhas:
                if "/" in l:
                    try:
                        p = l.split(); v = float(p[0]); d, m = map(int, p[1].split('/'))
                        if m == mes_at and ini_q <= d <= fim_q:
                            vol += v
                            if "(Pago!)" in l: rec += v
                    except: continue
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Parcelas no Período", f"R$ {vol:.2f}")
        m2.metric("Recebido", f"R$ {rec:.2f}")
        m3.metric("A Receber", f"R$ {vol-rec:.2f}", delta_color="inverse")
    
    st.divider()
    busca = st.text_input("🔍 Buscar Cliente no Histórico")
    
    if not df_vendas.empty:
        # Busca otimizada (como o DF já foi limpo no início, não precisa de .astype(str))
        df_f = df_vendas[df_vendas['cliente'].str.contains(busca, case=False)] if busca else df_vendas
        
        # Ordenar para ver as mais recentes primeiro (Sugestão adicional)
        df_f = df_f.sort_values(by='id', ascending=False)

        for i, (index, row) in enumerate(df_f.iterrows()):
            edit_key = f"edit_mode_{row['id']}_{i}" # Simplificado: usar apenas o ID único
            if edit_key not in st.session_state: 
                st.session_state[edit_key] = False

            # --- MELHORIA VISUAL: Barra de Progresso ---
            v_total, v_pago = extrair_valores_carne(row['carne'])
            percentual = v_pago / v_total if v_total > 0 else 0.0
            
            label_expander = f"{row['cliente']} - R$ {row['valor']} (Progresso: {int(percentual*100)}%)"
            
            with st.expander(label_expander):
                st.info("💡 Modo de Edição Inteligente")
    
                txt_key = f"txt_edit_{row['id']}"
                
                # --- 1. AO ABRIR: Converte JSON da planilha para TEXTO para o usuário editar ---
                if txt_key not in st.session_state:
                    try:
                        parcelas_init = json.loads(row['carne'])
                        texto_para_editar = ""
                        for p in parcelas_init:
                            status_txt = " (Pago!)" if p['p'] else ""
                            texto_para_editar += f"{p['v']:.2f} {p['d']}{status_txt}\n"
                        st.session_state[txt_key] = texto_para_editar
                    except:
                        st.session_state[txt_key] = row['carne'] # Fallback
            
                col_ed1, col_ed2, col_ed3 = st.columns([2, 1, 1])
                with col_ed1:
                    novo_prod = st.text_input("Produtos", value=row['produtos'], key=f"p_input_{row['id']}")
                    n_freq = st.radio("Nova Frequência", ["Mensal", "Quinzena"], horizontal=True, key=f"f_input_{row['id']}")
                with col_ed2:
                    n_valor = st.number_input("Valor Total (R$)", value=float(row['valor']), key=f"v_input_{row['id']}")
                    if n_freq == "Quinzena":
                        n_dia_base = st.selectbox("Dia Base", [1, 15], key=f"d_input_{row['id']}")
                with col_ed3:
                    # Conta parcelas no texto atual
                    qtd_atual = sum(1 for l in st.session_state[txt_key].split('\n') if "/" in l)
                    n_parcelas = st.number_input("Nº Parcelas", min_value=1, value=max(1, qtd_atual), key=f"q_input_{row['id']}")
            
                # --- 2. RECALCULAR: Gera TEXTO formatado (e não JSON bruto) ---
                if st.button("🔄 Recalcular Parcelas", key=f"btn_recalc_{row['id']}_{i}", use_container_width=True):
                    novos_v = calcular_parcelas_inteiras(n_valor, int(n_parcelas))
                    data_corrente = datetime.now() + dateutil.relativedelta.relativedelta(months=1)
                    if n_freq == "Quinzena": data_corrente = data_corrente.replace(day=n_dia_base)
                    
                    novo_texto_recalc = ""
                    for idx in range(int(n_parcelas)):
                        data_str = data_corrente.strftime("%d/%m")
                        novo_texto_recalc += f"{float(novos_v[idx]):.2f} {data_str}\n"
                        
                        if n_freq == "Quinzena":
                            if data_corrente.day == 1: data_corrente = data_corrente.replace(day=15)
                            else: data_corrente = (data_corrente + dateutil.relativedelta.relativedelta(months=1)).replace(day=1)
                        else:
                            data_corrente = data_corrente + dateutil.relativedelta.relativedelta(months=1)
                    
                    st.session_state[txt_key] = novo_texto_recalc
                    st.rerun()
            
                # O campo de texto agora mostra o carnê bonitinho (250.00 15/05)
                novo_carne_texto = st.text_area("Detalhamento do Carnê", value=st.session_state[txt_key], height=200, key=f"area_{row['id']}")
            
                st.divider()
                col_save1, col_save2 = st.columns(2)
                with col_save1:
                    if st.button("💾 Salvar Alterações", key=f"save_{row['id']}", type="primary", use_container_width=True):
                        # --- 3. AO SALVAR: Converte o TEXTO do campo de volta para JSON ---
                        linhas = novo_carne_texto.split('\n')
                        nova_lista_json = []
                        cont = 1
                        for linha in linhas:
                            if "/" in linha:
                                try:
                                    partes = linha.split()
                                    v_parc = float(partes[0].replace(',', '.'))
                                    d_parc = partes[1]
                                    p_parc = "(Pago!)" in linha
                                    nova_lista_json.append({"n": cont, "v": v_parc, "d": d_parc, "p": p_parc})
                                    cont += 1
                                except: continue
                        
                        df_vendas.at[index, 'produtos'] = novo_prod
                        df_vendas.at[index, 'valor'] = str(n_valor)
                        df_vendas.at[index, 'carne'] = json.dumps(nova_lista_json)
                        
                        conn.update(worksheet="vendas", data=df_vendas.astype(str))
                        
                        if txt_key in st.session_state: del st.session_state[txt_key]
                        st.session_state[edit_key] = False
                        atualizar_sistema()
                        
                with col_save2:
                    if st.button("❌ Cancelar", key=f"cancel_{row['id']}", use_container_width=True):
                        if txt_key in st.session_state: del st.session_state[txt_key]
                        st.session_state[edit_key] = False
                        st.rerun()
            
                else:
                    # --- MODO DE VISUALIZAÇÃO: ONDE A MÁGICA ACONTECE ---
                    st.progress(percentual)
                    
                    try:
                        # 1. Carregamos o JSON
                        parcelas_lista = json.loads(row['carne'])
                        
                        # 2. Criamos o texto formatado para o usuário
                        texto_bonito = f"📋 {row['produtos']}\n"
                        texto_bonito += f"💰 Valor Total: R$ {float(row['valor']):.2f}\n"
                        texto_bonito += "-" * 35 + "\n"
                        
                        for p in parcelas_lista:
                            icone = "✅" if p['p'] else "⏳"
                            pago_aviso = " (Pago!)" if p['p'] else ""
                            # Formata: ✅ 250.00 | 15/06 (Pago!)
                            texto_bonito += f"{icone} {p['v']:.2f}  |  {p['d']}{pago_aviso}\n"
                        
                        # 3. Exibimos o texto formatado
                        st.code(texto_bonito, language="text")
                        
                    except:
                        # Caso algum dado antigo ainda não seja JSON
                        st.warning("Formato antigo detectado:")
                        st.code(row['carne'])
                    
                    # --- COLUNAS DE BOTÕES ---
                    c_h = st.columns([1, 1, 1, 1, 1]) 
                    tel_f = dict_telefones.get(row['cliente'], "")
            
                    with c_h[0]: # PAGAR
                        if st.button("💰", key=f"p_{row['id']}_{i}"):
                            parcelas = json.loads(row['carne'])
                            for p in parcelas:
                                if not p['p']:
                                    p['p'] = True
                                    break
                            df_vendas.at[index, 'carne'] = json.dumps(parcelas)
                            df_vendas.at[index, 'status'] = "Pago" if all(p['p'] for p in parcelas) else "Pagamento Parcial"
                            conn.update(worksheet="vendas", data=df_vendas.astype(str))
                            atualizar_sistema()
            
                    with c_h[1]: # EDITAR
                        if st.button("✏️", key=f"btn_edit_{row['id']}_{i}"):
                            st.session_state[edit_key] = True
                            st.rerun()

                    with c_h[2]: # WHATSAPP (Usa o tel_f otimizado)
                        tel_f = dict_telefones.get(row['cliente'], "")
    
                        # 1. Traduz o JSON para um texto legível
                        parcelas_list = json.loads(row['carne'])
                        carne_txt = ""
                        for p in parcelas_list:
                            icone = "✅" if p['p'] else "⏳"
                            status_v = " (Pago)" if p['p'] else ""
                            carne_txt += f"{icone} R$ {p['v']:.2f} - {p['d']}{status_v}\n"
                    
                        # 2. Monta a mensagem completa
                        texto_whatsapp = (
                            f"💠 *RESUMO GERAL DA COMPRA* 💠\n\n"
                            f"👤 *Cliente:* {row['cliente']}\n"
                            f"📅 *Data da Venda:* {row['data']}\n"
                            f"📦 *Produtos:* {row['produtos']}\n"
                            f"💰 *Valor Total:* R$ {float(row['valor']):.2f}\n"
                            f"------------------------------------------\n"
                            f"📑 *DETALHAMENTO DO CARNÊ:*\n\n"
                            f"```\n{carne_txt}```\n" # Monospace para alinhar datas e valores
                            f"------------------------------------------\n"
                            f"✅ *Status:* {row['status']}\n\n"
                            f"Qualquer dúvida sobre os pagamentos, é só me chamar! 😊"
                        )
                        
                        msg = urllib.parse.quote(texto_whatsapp)
                        st.link_button("🟢", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg}")

                    with c_h[3]: # PIX (Usa o tel_f otimizado)
                        if pix_chave:
                            parcelas = json.loads(row['carne'])
                            # Pega a primeira que não está paga
                            proxima = next((p for p in parcelas if not p['p']), None)
                            valor_pix = proxima['v'] if proxima else row['valor']
                            
                            msg_pix = urllib.parse.quote(gerar_pix_texto(pix_chave, pix_nome, valor_pix))
                            st.link_button("💠", f"https://api.whatsapp.com/send?phone={tel_f}&text={msg_pix}")
                            
                    with c_h[4]: # EXCLUIR
                        with st.popover("🗑️"):
                            st.warning("Excluir venda?")
                            if st.button("Sim", key=f"conf_del_{row['id']}_{i}", type="primary"):
                                df_vendas = df_vendas.drop(index)
                                conn.update(worksheet="vendas", data=df_vendas.astype(str))
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
