import streamlit as st
import pandas as pd
import pypdf
import re
import json
import datetime
import plotly.express as px
import plotly.graph_objects as go
import io

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Compras de Importação - Calisto", layout="wide", initial_sidebar_state="expanded")

if 'estoque_df' not in st.session_state:
    st.session_state.estoque_df = pd.DataFrame()
if 'pedidos_dict' not in st.session_state:
    st.session_state.pedidos_dict = {}
if 'import_log' not in st.session_state:
    st.session_state.import_log = []
# Nova variável de estado para os fornecedores
if 'fornecedores_df' not in st.session_state:
    st.session_state.fornecedores_df = pd.DataFrame(columns=["Fornecedor", "País de Origem", "Prazo Médio de Trânsito (Dias)", "Contato / Observações"])

# ==========================================
# FUNÇÕES DE PROCESSAMENTO
# ==========================================
def registrar_log(acao, detalhes):
    st.session_state.import_log.append({
        "Data/Hora": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Ação": acao,
        "Detalhes": detalhes
    })

def ler_pdf_totvs(arquivo, filial):
    dados = []
    try:
        reader = pypdf.PdfReader(arquivo)
        text = ""
        for page in reader.pages:
            text += page.extract_text(extraction_mode='layout') + "\n"
        
        for linha in text.split('\n'):
            m = re.search(r'^\s*(\d{4,5})\s+(.+?)\s+(MT/\d+|CX|PCT|UN)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', linha)
            if m:
                dados.append({
                    'CODIGO': m.group(1),
                    'DESCRICAO': m.group(2).strip(),
                    f'ESTOQUE_{filial}': float(m.group(9).replace('.','').replace(',','.')),
                    f'VENDAS_M1_{filial}': float(m.group(4).replace('.','').replace(',','.')),
                    f'VENDAS_M2_{filial}': float(m.group(5).replace('.','').replace(',','.')),
                    f'VENDAS_M3_{filial}': float(m.group(6).replace('.','').replace(',','.')),
                    f'VENDAS_M4_{filial}': float(m.group(7).replace('.','').replace(',','.')),
                    f'MEDIA_{filial}': float(m.group(8).replace('.','').replace(',','.'))
                })
        return pd.DataFrame(dados)
    except Exception as e:
        st.error(f"Erro ao processar {arquivo.name}: {e}")
        return pd.DataFrame()

def consolidar_estoque(lista_dfs):
    if not lista_dfs: return pd.DataFrame()
    df_final = lista_dfs[0]
    for df in lista_dfs[1:]:
        df_final = pd.merge(df_final, df, on=['CODIGO', 'DESCRICAO'], how='outer').fillna(0)
    
    cols_estoque = [c for c in df_final.columns if 'ESTOQUE_' in c]
    cols_media = [c for c in df_final.columns if 'MEDIA_' in c]
    df_final['ESTOQUE_TOTAL'] = df_final[cols_estoque].sum(axis=1)
    df_final['MEDIA_TOTAL'] = df_final[cols_media].sum(axis=1)
    
    for i in range(1, 5):
        cols_vendas = [c for c in df_final.columns if f'VENDAS_M{i}_' in c]
        df_final[f'VENDAS_M{i}_TOTAL'] = df_final[cols_vendas].sum(axis=1)
        
    return df_final

def gerar_analise_completa(df_estoque, dict_pedidos, mult):
    if df_estoque.empty: return pd.DataFrame()
    df_calc = df_estoque.copy()
    df_calc['TRANSITO_OU_PRODUCAO'] = 0
    
    for nome_forn, df_forn in dict_pedidos.items():
        if 'CODIGO' in df_forn.columns and 'QTD_PEDIDO' in df_forn.columns:
            df_forn['QTD_PEDIDO'] = pd.to_numeric(df_forn['QTD_PEDIDO'], errors='coerce').fillna(0)
            agrupado = df_forn.groupby('CODIGO')['QTD_PEDIDO'].sum().reset_index()
            df_calc = pd.merge(df_calc, agrupado, on='CODIGO', how='left')
            df_calc['QTD_PEDIDO'] = df_calc['QTD_PEDIDO'].fillna(0)
            df_calc['TRANSITO_OU_PRODUCAO'] += df_calc['QTD_PEDIDO']
            df_calc = df_calc.drop(columns=['QTD_PEDIDO'])
            
    df_calc['MÉDIA_PROJETADA'] = df_calc['MEDIA_TOTAL'] * mult
    df_calc['DISPONIBILIDADE_TOTAL'] = df_calc['ESTOQUE_TOTAL'] + df_calc['TRANSITO_OU_PRODUCAO']
    df_calc['SUGESTÃO_COMPRA'] = df_calc['MÉDIA_PROJETADA'] - df_calc['DISPONIBILIDADE_TOTAL']
    df_calc['SUGESTÃO_COMPRA'] = df_calc['SUGESTÃO_COMPRA'].apply(lambda x: x if x > 0 else 0)
    
    df_calc['STATUS'] = df_calc.apply(lambda row: '🔴 Crítico' if row['DISPONIBILIDADE_TOTAL'] < row['MEDIA_TOTAL'] else ('🟢 OK' if row['SUGESTÃO_COMPRA'] == 0 else '🟡 Atenção'), axis=1)
    return df_calc

# ==========================================
# MENU LATERAL (SIDEBAR)
# ==========================================
st.sidebar.markdown("""
    <style>
        [data-testid="stSidebarNav"] {display: none;}
    </style>
""", unsafe_allow_html=True)

try:
    st.sidebar.image("logo.png", width=200)
except:
    pass

st.sidebar.markdown("### ⚙️ Sistema de Importação")
menu = st.sidebar.radio("Navegação", [
    "📊 Dashboard Geral", 
    "📥 1. Importar TOTVS", 
    "🚢 2. Pedidos em Trânsito", 
    "🛒 3. Sugestão de Compras", 
    "👥 4. Cadastro de Fornecedores",
    "💾 5. Config. e Backup"
])

st.sidebar.markdown("---")
st.sidebar.markdown("**Parâmetros de Análise**")
multiplicador = st.sidebar.number_input("Cobertura Alvo (Multiplicador)", min_value=1.0, value=2.0, step=0.5, help="Ex: 2.0 significa projetar estoque para 2 meses de vendas.")

# ==========================================
# TELA 0: DASHBOARD GERAL
# ==========================================
if menu == "📊 Dashboard Geral":
    st.title("Painel de Inteligência de Importação")
    
    if st.session_state.estoque_df.empty:
        st.info("👋 Bem-vindo! Vá para a aba **1. Importar TOTVS** para iniciar suas análises.")
    else:
        df_dash = gerar_analise_completa(st.session_state.estoque_df, st.session_state.pedidos_dict, multiplicador)
        
        st.markdown("#### Visão Executiva")
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("📦 SKUs Monitorados", f"{len(df_dash)}")
        col2.metric("🏢 Estoque Físico", f"{df_dash['ESTOQUE_TOTAL'].sum():,.0f}".replace(',', '.'))
        col3.metric("🚢 Em Trânsito/Prod.", f"{df_dash['TRANSITO_OU_PRODUCAO'].sum():,.0f}".replace(',', '.'))
        col4.metric("🛒 Sugestão de Compra", f"{df_dash['SUGESTÃO_COMPRA'].sum():,.0f}".replace(',', '.'), delta="Necessidade", delta_color="inverse")

        st.markdown("---")
        row1_c1, row1_c2 = st.columns([1, 2])
        
        with row1_c1:
            st.markdown("##### Saúde da Cobertura")
            status_counts = df_dash['STATUS'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Quantidade']
            cores_status = {'🔴 Crítico': '#d9534f', '🟡 Atenção': '#f0ad4e', '🟢 OK': '#5cb85c'}
            fig_status = px.pie(status_counts, values='Quantidade', names='Status', hole=0.5, color='Status', color_discrete_map=cores_status)
            fig_status.update_layout(margin=dict(t=20, b=20, l=20, r=20), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_status, use_container_width=True)

        with row1_c2:
            st.markdown("##### Evolução de Vendas Consolidada")
            vendas_historico = {
                'Mês 1': df_dash['VENDAS_M1_TOTAL'].sum(),
                'Mês 2': df_dash['VENDAS_M2_TOTAL'].sum(),
                'Mês 3': df_dash['VENDAS_M3_TOTAL'].sum(),
                'Mês 4 (Atual)': df_dash['VENDAS_M4_TOTAL'].sum()
            }
            df_vendas_hist = pd.DataFrame(list(vendas_historico.items()), columns=['Período', 'Volume'])
            fig_vendas = px.line(df_vendas_hist, x='Período', y='Volume', markers=True, text='Volume')
            fig_vendas.update_traces(textposition='top center', line_color='#1F4E78', marker=dict(size=10))
            st.plotly_chart(fig_vendas, use_container_width=True)
            
        st.markdown("---")
        st.markdown("##### Distribuição Físico por Filial")
        cols_filiais = [c for c in df_dash.columns if 'ESTOQUE_' in c and c != 'ESTOQUE_TOTAL']
        if cols_filiais:
            df_melt = df_dash.melt(id_vars=['DESCRICAO'], value_vars=cols_filiais, var_name='Filial', value_name='Qtd')
            df_melt['Filial'] = df_melt['Filial'].str.replace('ESTOQUE_', '')
            fig_bar = px.bar(df_melt.groupby('Filial')['Qtd'].sum().reset_index(), x='Filial', y='Qtd', text='Qtd', color='Filial', color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_bar.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# TELA 1: IMPORTAÇÃO TOTVS
# ==========================================
elif menu == "📥 1. Importar TOTVS":
    st.title("Importação de Dados - TOTVS")
    st.info("Selecione os PDFs gerados pelo sistema TOTVS.")
    
    col1, col2 = st.columns(2)
    with col1: 
        pdf_matriz = st.file_uploader("🏢 Matriz", type=['pdf'])
        pdf_ribeirao = st.file_uploader("🏢 Ribeirão Preto", type=['pdf'])
        pdf_franca = st.file_uploader("🏢 Franca", type=['pdf'])
    with col2: 
        pdf_bh = st.file_uploader("🏢 Belo Horizonte", type=['pdf'])
        pdf_londrina = st.file_uploader("🏢 Londrina", type=['pdf'])
    
    if st.button("Processar Documentos TOTVS", type="primary"):
        dfs = []
        if pdf_matriz: dfs.append(ler_pdf_totvs(pdf_matriz, "MATRIZ"))
        if pdf_ribeirao: dfs.append(ler_pdf_totvs(pdf_ribeirao, "RIBEIRAO"))
        if pdf_franca: dfs.append(ler_pdf_totvs(pdf_franca, "FRANCA"))
        if pdf_bh: dfs.append(ler_pdf_totvs(pdf_bh, "BH"))
        if pdf_londrina: dfs.append(ler_pdf_totvs(pdf_londrina, "LONDRINA"))
        
        if dfs:
            st.session_state.estoque_df = consolidar_estoque(dfs)
            registrar_log("Importação TOTVS", "Base atualizada com sucesso.")
            st.success("Dados estruturados com sucesso!")
        else:
            st.warning("Nenhum PDF foi selecionado.")

# ==========================================
# TELA 2: GESTÃO DE FORNECEDORES (PEDIDOS)
# ==========================================
elif menu == "🚢 2. Pedidos em Trânsito":
    st.title("Controle de Pedidos e Trânsito")
    
    upload_fornecedor = st.file_uploader("Anexar Planilha do Fornecedor (Excel)", type=['xlsx', 'xls'])
    if upload_fornecedor:
        nome_arquivo = upload_fornecedor.name
        xls = pd.ExcelFile(upload_fornecedor)
        for sheet_name in xls.sheet_names:
            df_forn = pd.read_excel(xls, sheet_name=sheet_name)
            for col in ["PRODUCAO_CHINA", "PREVISAO_EMBARQUE", "PREVISAO_CHEGADA", "QTD_PEDIDO"]:
                if col not in df_forn.columns: df_forn[col] = 0 if col in ["PRODUCAO_CHINA", "QTD_PEDIDO"] else ""
            st.session_state.pedidos_dict[f"{nome_arquivo} - {sheet_name}"] = df_forn
        registrar_log("Importação Fornecedor", f"{nome_arquivo} processado.")
        st.success("Planilha processada com sucesso!")

    if st.session_state.pedidos_dict:
        st.markdown("---")
        fornecedor_selecionado = st.selectbox("Selecione o pedido ativo para editar datas e volumes:", list(st.session_state.pedidos_dict.keys()))
        st.session_state.pedidos_dict[fornecedor_selecionado] = st.data_editor(st.session_state.pedidos_dict[fornecedor_selecionado], num_rows="dynamic")

# ==========================================
# TELA 3: SUGESTÃO DE COMPRAS
# ==========================================
elif menu == "🛒 3. Sugestão de Compras":
    st.title("Sugestão Inteligente de Compras")
    if st.session_state.estoque_df.empty:
        st.warning("Requer importação inicial dos dados do TOTVS.")
    else:
        df_sugestao = gerar_analise_completa(st.session_state.estoque_df, st.session_state.pedidos_dict, multiplicador)
        col_f1, col_f2 = st.columns(2)
        status_filter = col_f1.multiselect("Nível de Urgência", ['🔴 Crítico', '🟡 Atenção', '🟢 OK'], default=['🔴 Crítico', '🟡 Atenção'])
        sugestao_minima = col_f2.number_input("Ocultar sugestões menores que:", value=0)
        
        df_filtrado = df_sugestao[(df_sugestao['STATUS'].isin(status_filter)) & (df_sugestao['SUGESTÃO_COMPRA'] >= sugestao_minima)]
        st.data_editor(df_filtrado, use_container_width=True, hide_index=True)

        @st.cache_data
        def converter_df_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
        
        st.download_button("📥 Exportar Relatório (Excel)", converter_df_excel(df_filtrado), f"Sugestao_Calisto.xlsx", type="primary")

# ==========================================
# TELA 4: CADASTRO DE FORNECEDORES (NOVO)
# ==========================================
elif menu == "👥 4. Cadastro de Fornecedores":
    st.title("Cadastro de Fornecedores Parceiros")
    st.write("Mantenha o banco de dados dos seus fornecedores atualizado para facilitar consultas rápidas.")
    
    # Formulário de Cadastro
    with st.expander("➕ Adicionar Novo Fornecedor", expanded=True):
        with st.form("form_fornecedor", clear_on_submit=True):
            col_form1, col_form2 = st.columns(2)
            nome_fornecedor = col_form1.text_input("Nome da Empresa / Fornecedor *")
            pais_origem = col_form2.text_input("País de Origem (Ex: China, Índia)")
            prazo_transito = col_form1.number_input("Prazo Médio de Trânsito (Dias)", min_value=0, step=1)
            contato_obs = col_form2.text_input("Contato ou Observações Rápidas")
            
            submit = st.form_submit_button("Salvar Fornecedor", type="primary")
            
            if submit:
                if nome_fornecedor.strip() == "":
                    st.error("O campo 'Nome da Empresa' é obrigatório.")
                else:
                    novo_registro = pd.DataFrame([{
                        "Fornecedor": nome_fornecedor,
                        "País de Origem": pais_origem,
                        "Prazo Médio de Trânsito (Dias)": prazo_transito,
                        "Contato / Observações": contato_obs
                    }])
                    st.session_state.fornecedores_df = pd.concat([st.session_state.fornecedores_df, novo_registro], ignore_index=True)
                    registrar_log("Cadastro Fornecedor", f"{nome_fornecedor} cadastrado.")
                    st.success(f"Fornecedor **{nome_fornecedor}** cadastrado com sucesso!")
                    st.rerun()

    # Tabela Editável
    st.markdown("---")
    st.subheader("Fornecedores Cadastrados")
    if st.session_state.fornecedores_df.empty:
        st.info("Nenhum fornecedor cadastrado ainda.")
    else:
        st.caption("Você pode editar as informações diretamente na tabela abaixo ou deletar uma linha selecionando-a na lateral esquerda e apertando Delete.")
        st.session_state.fornecedores_df = st.data_editor(st.session_state.fornecedores_df, use_container_width=True, num_rows="dynamic")

# ==========================================
# TELA 5: CONFIG. E BACKUP
# ==========================================
elif menu == "💾 5. Config. e Backup":
    st.title("Manutenção e Segurança de Dados")
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.subheader("Exportar Backup Completo")
        estado_para_salvar = {
            "estoque_df": st.session_state.estoque_df.to_json(orient='records') if not st.session_state.estoque_df.empty else "[]",
            "fornecedores_df": st.session_state.fornecedores_df.to_json(orient='records') if not st.session_state.fornecedores_df.empty else "[]",
            "import_log": st.session_state.import_log,
            "pedidos_dict": {k: v.to_json(orient='records') for k, v in st.session_state.pedidos_dict.items()}
        }
        st.download_button("📦 Baixar Backup (.json)", json.dumps(estado_para_salvar, indent=4), f"backup_calisto.json")
        
    with col_b2:
        st.subheader("Restaurar Sessão")
        arquivo_backup = st.file_uploader("Anexar arquivo de Backup", type=['json'])
        if arquivo_backup is not None and st.button("Iniciar Restauração"):
            dados = json.load(arquivo_backup)
            st.session_state.estoque_df = pd.read_json(io.StringIO(dados.get('estoque_df', '[]')))
            st.session_state.fornecedores_df = pd.read_json(io.StringIO(dados.get('fornecedores_df', '[]')))
            st.session_state.import_log = dados.get('import_log', [])
            st.session_state.pedidos_dict = {k: pd.read_json(io.StringIO(v)) for k, v in dados.get('pedidos_dict', {}).items()}
            st.success("Dados restaurados!")
