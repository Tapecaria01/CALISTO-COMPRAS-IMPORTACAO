import streamlit as st
import pandas as pd
import pypdf
import re
import json
import datetime
import plotly.express as px
import io

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E ESTADO (SESSÃO)
# ==========================================
st.set_page_config(page_title="Compras de Importação - Calisto", layout="wide")

if 'estoque_df' not in st.session_state:
    st.session_state.estoque_df = pd.DataFrame()
if 'pedidos_dict' not in st.session_state:
    st.session_state.pedidos_dict = {}
if 'import_log' not in st.session_state:
    st.session_state.import_log = []

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
    """Extrai os dados do PDF do TOTVS utilizando PyPDF."""
    dados = []
    try:
        reader = pypdf.PdfReader(arquivo)
        text = ""
        for page in reader.pages:
            text += page.extract_text(extraction_mode='layout') + "\n"
        
        # Regex para capturar as colunas do modelo TOTVS da Calisto
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
        df = pd.DataFrame(dados)
        return df
    except Exception as e:
        st.error(f"Erro ao processar {arquivo.name}: {e}")
        return pd.DataFrame()

def consolidar_estoque(lista_dfs):
    if not lista_dfs: return pd.DataFrame()
    df_final = lista_dfs[0]
    for df in lista_dfs[1:]:
        df_final = pd.merge(df_final, df, on=['CODIGO', 'DESCRICAO'], how='outer').fillna(0)
    
    # Criar colunas de soma total
    cols_estoque = [c for c in df_final.columns if 'ESTOQUE_' in c]
    cols_media = [c for c in df_final.columns if 'MEDIA_' in c]
    df_final['ESTOQUE_TOTAL'] = df_final[cols_estoque].sum(axis=1)
    df_final['MEDIA_TOTAL'] = df_final[cols_media].sum(axis=1)
    return df_final

# ==========================================
# MENU LATERAL (SIDEBAR)
# ==========================================
# INCLUSÃO DA LOGO AQUI:
try:
    st.sidebar.image("PASSALACQUA_Logo-Calisto&Co.png", use_column_width=True)
except:
    st.sidebar.title("Calisto & Co.")

st.sidebar.title("⚙️ Compras Calisto")
menu = st.sidebar.radio("Navegação", [
    "📊 Dashboard e Alertas", 
    "📥 1. Importar TOTVS (PDFs)", 
    "🚢 2. Gestão de Pedidos (Fornecedores)", 
    "🛒 3. Sugestão de Compras (Consolidado)", 
    "💾 4. Histórico e Backup"
])

st.sidebar.markdown("---")
st.sidebar.subheader("Parâmetros de Cálculo")
multiplicador = st.sidebar.number_input("Multiplicador da Média", min_value=1.0, value=2.0, step=0.5, help="Multiplica a coluna 'Média' para projetar a necessidade de compras.")

# ==========================================
# TELA 1: IMPORTAÇÃO TOTVS
# ==========================================
if menu == "📥 1. Importar TOTVS (PDFs)":
    st.header("Importação de Estoque e Vendas (TOTVS)")
    st.info("Faça o upload dos 5 PDFs referentes às filiais. O sistema consolidará os dados automaticamente.")
    
    col1, col2 = st.columns(2)
    with col1: pdf_matriz = st.file_uploader("PDF Matriz", type=['pdf'])
    with col1: pdf_ribeirao = st.file_uploader("PDF Ribeirão (Álvaro de Lima)", type=['pdf'])
    with col1: pdf_franca = st.file_uploader("PDF Franca", type=['pdf'])
    with col2: pdf_bh = st.file_uploader("PDF BH", type=['pdf'])
    with col2: pdf_londrina = st.file_uploader("PDF Londrina", type=['pdf'])
    
    if st.button("Processar PDFs"):
        dfs = []
        if pdf_matriz: dfs.append(ler_pdf_totvs(pdf_matriz, "MATRIZ"))
        if pdf_ribeirao: dfs.append(ler_pdf_totvs(pdf_ribeirao, "RIBEIRAO"))
        if pdf_franca: dfs.append(ler_pdf_totvs(pdf_franca, "FRANCA"))
        if pdf_bh: dfs.append(ler_pdf_totvs(pdf_bh, "BH"))
        if pdf_londrina: dfs.append(ler_pdf_totvs(pdf_londrina, "LONDRINA"))
        
        if dfs:
            df_consolidado = consolidar_estoque(dfs)
            st.session_state.estoque_df = df_consolidado
            registrar_log("Importação TOTVS", f"Importados {len(dfs)} arquivos. Total de SKUs lidos: {len(df_consolidado)}.")
            st.success("Dados importados e consolidados com sucesso!")
        else:
            st.warning("Nenhum arquivo enviado.")
            
    if not st.session_state.estoque_df.empty:
        st.markdown("---")
        st.subheader("Edição Manual de Estoque (Correção)")
        st.caption("Altere os valores na tabela abaixo caso o TOTVS tenha trazido algum dado divergente. As alterações são aplicadas na hora.")
        st.session_state.estoque_df = st.data_editor(st.session_state.estoque_df, num_rows="dynamic", key="editor_estoque")

# ==========================================
# TELA 2: GESTÃO DE PEDIDOS (FORNECEDORES)
# ==========================================
elif menu == "🚢 2. Gestão de Pedidos (Fornecedores)":
    st.header("Adicionar e Editar Pedidos de Fornecedores")
    
    st.subheader("Importar Excel de Fornecedor")
    upload_fornecedor = st.file_uploader("Suba o Excel do Pedido", type=['xlsx', 'xls'])
    
    if upload_fornecedor:
        nome_arquivo = upload_fornecedor.name
        # Evitar duplicatas perguntando se quer atualizar
        if nome_arquivo in st.session_state.pedidos_dict:
            st.warning(f"O arquivo '{nome_arquivo}' já foi importado anteriormente. Deseja atualizar?")
            if st.button("Sim, atualizar pedido"):
                xls = pd.ExcelFile(upload_fornecedor)
                for sheet_name in xls.sheet_names:
                    df_forn = pd.read_excel(xls, sheet_name=sheet_name)
                    # Colunas vitais
                    for col in ["PRODUCAO_CHINA", "PREVISAO_EMBARQUE", "PREVISAO_CHEGADA", "QTD_PEDIDO"]:
                        if col not in df_forn.columns: df_forn[col] = 0 if col in ["PRODUCAO_CHINA", "QTD_PEDIDO"] else ""
                    st.session_state.pedidos_dict[f"{nome_arquivo} - {sheet_name}"] = df_forn
                registrar_log("Atualização de Pedido", f"Pedido {nome_arquivo} atualizado.")
                st.success("Pedido atualizado com sucesso!")
        else:
            xls = pd.ExcelFile(upload_fornecedor)
            for sheet_name in xls.sheet_names:
                df_forn = pd.read_excel(xls, sheet_name=sheet_name)
                for col in ["PRODUCAO_CHINA", "PREVISAO_EMBARQUE", "PREVISAO_CHEGADA", "QTD_PEDIDO"]:
                    if col not in df_forn.columns: df_forn[col] = 0 if col in ["PRODUCAO_CHINA", "QTD_PEDIDO"] else ""
                st.session_state.pedidos_dict[f"{nome_arquivo} - {sheet_name}"] = df_forn
            registrar_log("Novo Pedido", f"Arquivo {nome_arquivo} importado.")
            st.success("Pedido adicionado com sucesso! Cada aba virou um fornecedor/seção.")

    # Edição Manual das Abas
    if st.session_state.pedidos_dict:
        st.markdown("---")
        st.subheader("Painel de Edição: Embarque e Produção")
        fornecedor_selecionado = st.selectbox("Selecione a aba do fornecedor para editar as datas e quantidades:", list(st.session_state.pedidos_dict.keys()))
        
        st.caption("Você pode editar as datas de 'Previsão Embarque', 'Previsão Chegada' e as quantidades diretamente na tabela abaixo.")
        df_edit = st.data_editor(st.session_state.pedidos_dict[fornecedor_selecionado], num_rows="dynamic")
        st.session_state.pedidos_dict[fornecedor_selecionado] = df_edit

# ==========================================
# TELA 3: SUGESTÃO DE COMPRAS (O CORAÇÃO DO SISTEMA)
# ==========================================
elif menu == "🛒 3. Sugestão de Compras (Consolidado)":
    st.header("Análise Inteligente e Sugestão de Compras")
    
    if st.session_state.estoque_df.empty:
        st.warning("Para gerar as sugestões, importe os PDFs do TOTVS na aba 1 primeiro.")
    else:
        df_sugestao = st.session_state.estoque_df.copy()
        
        # Consolida todos os pedidos que estão em trânsito/produção
        df_sugestao['TRANSITO_OU_PRODUCAO'] = 0
        for nome_forn, df_forn in st.session_state.pedidos_dict.items():
            if 'CODIGO' in df_forn.columns and 'QTD_PEDIDO' in df_forn.columns:
                df_forn['QTD_PEDIDO'] = pd.to_numeric(df_forn['QTD_PEDIDO'], errors='coerce').fillna(0)
                agrupado = df_forn.groupby('CODIGO')['QTD_PEDIDO'].sum().reset_index()
                df_sugestao = pd.merge(df_sugestao, agrupado, on='CODIGO', how='left')
                df_sugestao['QTD_PEDIDO'] = df_sugestao['QTD_PEDIDO'].fillna(0)
                df_sugestao['TRANSITO_OU_PRODUCAO'] += df_sugestao['QTD_PEDIDO']
                df_sugestao = df_sugestao.drop(columns=['QTD_PEDIDO'])
        
        # Cálculos de Sugestão
        df_sugestao['MÉDIA_PROJETADA'] = df_sugestao['MEDIA_TOTAL'] * multiplicador
        df_sugestao['DISPONIBILIDADE_TOTAL'] = df_sugestao['ESTOQUE_TOTAL'] + df_sugestao['TRANSITO_OU_PRODUCAO']
        df_sugestao['SUGESTÃO_COMPRA'] = df_sugestao['MÉDIA_PROJETADA'] - df_sugestao['DISPONIBILIDADE_TOTAL']
        df_sugestao['SUGESTÃO_COMPRA'] = df_sugestao['SUGESTÃO_COMPRA'].apply(lambda x: x if x > 0 else 0)
        
        # Define Status
        df_sugestao['STATUS'] = df_sugestao.apply(lambda row: '🔴 Crítico' if row['DISPONIBILIDADE_TOTAL'] < row['MEDIA_TOTAL'] else ('🟢 OK' if row['SUGESTÃO_COMPRA'] == 0 else '🟡 Atenção'), axis=1)

        # Filtros Avançados
        st.subheader("Filtros Avançados")
        col_f1, col_f2 = st.columns(2)
        status_filter = col_f1.multiselect("Filtrar por Status de Cobertura", ['🔴 Crítico', '🟡 Atenção', '🟢 OK'], default=['🔴 Crítico', '🟡 Atenção', '🟢 OK'])
        sugestao_minima = col_f2.number_input("Ocultar sugestões de compra menores que (Unidades):", value=0)
        
        df_filtrado = df_sugestao[(df_sugestao['STATUS'].isin(status_filter)) & (df_sugestao['SUGESTÃO_COMPRA'] >= sugestao_minima)]
        
        # Mostra a tabela editável
        st.data_editor(df_filtrado, use_container_width=True, hide_index=True)

        # Download do Excel
        @st.cache_data
        def converter_df_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Sugestao_Geral')
            return output.getvalue()
        
        st.download_button(
            label="📥 Baixar Planilha Consolidada (Excel)", 
            data=converter_df_excel(df_filtrado), 
            file_name=f"Sugestao_Calisto_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ==========================================
# TELA 4: DASHBOARD E ALERTAS
# ==========================================
elif menu == "📊 Dashboard e Alertas":
    st.header("Visão Geral do Negócio")
    
    if st.session_state.estoque_df.empty:
        st.info("Importe os dados do TOTVS para visualizar os gráficos e alertas.")
    else:
        df_dash = st.session_state.estoque_df
        total_skus = len(df_dash)
        total_estoque = df_dash['ESTOQUE_TOTAL'].sum() if 'ESTOQUE_TOTAL' in df_dash.columns else 0
        
        # Cards Rápidos
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 SKUs Gerenciados", f"{total_skus}")
        c2.metric("🏢 Volume Total em Estoque", f"{total_estoque:,.0f}")
        c3.metric("🚢 Abas de Fornecedores Ativas", len(st.session_state.pedidos_dict))
        
        st.markdown("---")
        
        # Gráficos
        st.subheader("Cobertura de Estoque por Filial")
        cols_filiais = [c for c in df_dash.columns if 'ESTOQUE_' in c and c != 'ESTOQUE_TOTAL']
        if cols_filiais:
            df_melt = df_dash.melt(id_vars=['DESCRICAO'], value_vars=cols_filiais, var_name='Filial', value_name='Qtd')
            df_melt['Filial'] = df_melt['Filial'].str.replace('ESTOQUE_', '')
            fig = px.bar(df_melt.groupby('Filial')['Qtd'].sum().reset_index(), x='Filial', y='Qtd', color='Filial', title="Estoque Atual Total por Filial")
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# TELA 5: HISTÓRICO E BACKUP
# ==========================================
elif menu == "💾 4. Histórico e Backup":
    st.header("Histórico de Ações e Backup de Dados")
    
    st.subheader("Log de Eventos (Rastreabilidade)")
    if st.session_state.import_log:
        st.dataframe(pd.DataFrame(st.session_state.import_log), use_container_width=True)
    else:
        st.write("Nenhum evento registrado na sessão atual.")

    st.markdown("---")
    
    st.subheader("Backup Total do Sistema")
    st.write("Exporte todo o estado atual (Tabelas do TOTVS, Dados dos Fornecedores e Histórico) para salvar o seu trabalho e carregar amanhã.")
    
    estado_para_salvar = {
        "estoque_df": st.session_state.estoque_df.to_json(orient='records') if not st.session_state.estoque_df.empty else "[]",
        "import_log": st.session_state.import_log,
        "pedidos_dict": {k: v.to_json(orient='records') for k, v in st.session_state.pedidos_dict.items()}
    }
    
    json_string = json.dumps(estado_para_salvar, indent=4)
    st.download_button(label="📦 Baixar Backup do Sistema (.json)", data=json_string, file_name=f"backup_calisto_{datetime.datetime.now().strftime('%Y%m%d')}.json", mime="application/json")
    
    st.markdown("---")
    st.subheader("Restaurar Backup")
    arquivo_backup = st.file_uploader("Suba um arquivo .json de backup salvo anteriormente", type=['json'])
    if arquivo_backup is not None:
        if st.button("Restaurar Dados"):
            try:
                dados_restaurados = json.load(arquivo_backup)
                st.session_state.estoque_df = pd.read_json(io.StringIO(dados_restaurados['estoque_df']))
                st.session_state.import_log = dados_restaurados['import_log']
                st.session_state.pedidos_dict = {k: pd.read_json(io.StringIO(v)) for k, v in dados_restaurados['pedidos_dict'].items()}
                registrar_log("Restauração de Backup", "Sistema restaurado via arquivo JSON.")
                st.success("Sistema restaurado com sucesso! Navegue pelas abas ao lado.")
            except Exception as e:
                st.error(f"Erro ao tentar restaurar: {e}")
