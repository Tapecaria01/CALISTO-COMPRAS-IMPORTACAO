import streamlit as st
import pandas as pd
import pypdf
import re
import json
import datetime
import plotly.express as px
import plotly.graph_objects as go
import io
import numpy as np

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E CSS (Estilo BI)
# ==========================================
st.set_page_config(page_title="Compras Calisto", layout="wide", initial_sidebar_state="expanded")

# CSS customizado para os cartões de KPI ficarem parecidos com a referência
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 32px !important;
        color: #1F4E78 !important;
    }
    div.css-1r6slb0.e1tzin5v2 {
        background-color: #f0f8ff;
        border: 1px solid #d0e3f5;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# Variáveis de Estado
if 'estoque_df' not in st.session_state: st.session_state.estoque_df = pd.DataFrame()
if 'pedidos_dict' not in st.session_state: st.session_state.pedidos_dict = {}
if 'import_log' not in st.session_state: st.session_state.import_log = []
if 'fornecedores_df' not in st.session_state: st.session_state.fornecedores_df = pd.DataFrame(columns=["Fornecedor", "País", "Lead Time (Dias)", "Contato"])

# ==========================================
# FUNÇÕES DE PROCESSAMENTO
# ==========================================
def registrar_log(acao, detalhes):
    st.session_state.import_log.append({
        "Data": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "Ação": acao, "Detalhes": detalhes
    })

def ler_pdf_totvs(arquivo, filial):
    dados = []
    try:
        reader = pypdf.PdfReader(arquivo)
        text = "".join([page.extract_text(extraction_mode='layout') + "\n" for page in reader.pages])
        for linha in text.split('\n'):
            m = re.search(r'^\s*(\d{4,5})\s+(.+?)\s+(MT/\d+|CX|PCT|UN)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', linha)
            if m:
                dados.append({
                    'CODIGO': m.group(1), 'DESCRICAO': m.group(2).strip(),
                    f'ESTOQUE_{filial}': float(m.group(9).replace('.','').replace(',','.')),
                    f'VENDAS_M1_{filial}': float(m.group(4).replace('.','').replace(',','.')),
                    f'VENDAS_M2_{filial}': float(m.group(5).replace('.','').replace(',','.')),
                    f'VENDAS_M3_{filial}': float(m.group(6).replace('.','').replace(',','.')),
                    f'VENDAS_M4_{filial}': float(m.group(7).replace('.','').replace(',','.')),
                    f'MEDIA_{filial}': float(m.group(8).replace('.','').replace(',','.'))
                })
        return pd.DataFrame(dados)
    except Exception: return pd.DataFrame()

def consolidar_estoque(lista_dfs):
    if not lista_dfs: return pd.DataFrame()
    df_final = lista_dfs[0]
    for df in lista_dfs[1:]: df_final = pd.merge(df_final, df, on=['CODIGO', 'DESCRICAO'], how='outer').fillna(0)
    
    cols_estoque = [c for c in df_final.columns if 'ESTOQUE_' in c]
    cols_media = [c for c in df_final.columns if 'MEDIA_' in c]
    df_final['ESTOQUE_TOTAL'] = df_final[cols_estoque].sum(axis=1)
    df_final['MEDIA_TOTAL'] = df_final[cols_media].sum(axis=1)
    for i in range(1, 5):
        df_final[f'VENDAS_M{i}_TOTAL'] = df_final[[c for c in df_final.columns if f'VENDAS_M{i}_' in c]].sum(axis=1)
    return df_final

def gerar_analise_completa(df_estoque, dict_pedidos, mult):
    if df_estoque.empty: return pd.DataFrame()
    df_calc = df_estoque.copy()
    df_calc['TRANSITO_PRODUCAO'] = 0
    
    for nome_forn, df_forn in dict_pedidos.items():
        if 'CODIGO' in df_forn.columns and 'QTD_PEDIDO' in df_forn.columns:
            df_forn['QTD_PEDIDO'] = pd.to_numeric(df_forn['QTD_PEDIDO'], errors='coerce').fillna(0)
            agrupado = df_forn.groupby('CODIGO')['QTD_PEDIDO'].sum().reset_index()
            df_calc = pd.merge(df_calc, agrupado, on='CODIGO', how='left')
            df_calc['TRANSITO_PRODUCAO'] += df_calc['QTD_PEDIDO'].fillna(0)
            df_calc = df_calc.drop(columns=['QTD_PEDIDO'])
            
    df_calc['MEDIA_PROJETADA'] = df_calc['MEDIA_TOTAL'] * mult
    df_calc['DISPONIBILIDADE_TOTAL'] = df_calc['ESTOQUE_TOTAL'] + df_calc['TRANSITO_PRODUCAO']
    df_calc['SUGESTAO_COMPRA'] = np.where((df_calc['MEDIA_PROJETADA'] - df_calc['DISPONIBILIDADE_TOTAL']) > 0, 
                                           df_calc['MEDIA_PROJETADA'] - df_calc['DISPONIBILIDADE_TOTAL'], 0)
    
    # Cálculo de Cobertura em Meses
    df_calc['COBERTURA_MESES'] = np.where(df_calc['MEDIA_TOTAL'] > 0, df_calc['DISPONIBILIDADE_TOTAL'] / df_calc['MEDIA_TOTAL'], 99)
    df_calc['STATUS'] = np.where(df_calc['COBERTURA_MESES'] < 1.5, '🔴 Crítico', 
                                 np.where(df_calc['COBERTURA_MESES'] > mult, '🟢 OK', '🟡 Atenção'))
    return df_calc

# ==========================================
# MENU LATERAL (ESTILO BI)
# ==========================================
try:
    st.sidebar.image("logo.png", use_container_width=True)
except: pass

st.sidebar.markdown("### 🎛️ Painel de Controle")
menu = st.sidebar.radio("Módulos", ["📊 Dashboard BI", "📥 1. Integração TOTVS", "🚢 2. Pedidos Importação", "🛒 3. Plano de Compras", "👥 4. Fornecedores", "⚙️ 5. Sistema"])

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 Filtros Globais")
multiplicador = st.sidebar.slider("Cobertura Alvo (Meses)", min_value=1.0, max_value=6.0, value=2.0, step=0.5)
filtro_status = st.sidebar.multiselect("Status de Cobertura", ['🔴 Crítico', '🟡 Atenção', '🟢 OK'], default=['🔴 Crítico', '🟡 Atenção', '🟢 OK'])

# ==========================================
# TELA 0: DASHBOARD BI (NOVO LAYOUT)
# ==========================================
if menu == "📊 Dashboard BI":
    st.title("Visão Executiva - Importação e Suprimentos")
    
    if st.session_state.estoque_df.empty:
        st.info("👈 Importe os dados do TOTVS no menu lateral para visualizar os indicadores.")
    else:
        df_dash = gerar_analise_completa(st.session_state.estoque_df, st.session_state.pedidos_dict, multiplicador)
        df_dash = df_dash[df_dash['STATUS'].isin(filtro_status)] # Aplica filtro global
        
        # 1. KPIs no Topo (5 Cartões inspirados na imagem)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("SKUs Filtrados", f"{len(df_dash)}")
        c2.metric("Estoque Físico (Un)", f"{df_dash['ESTOQUE_TOTAL'].sum():,.0f}".replace(',','.'))
        c3.metric("Em Trânsito/Mar (Un)", f"{df_dash['TRANSITO_PRODUCAO'].sum():,.0f}".replace(',','.'))
        c4.metric("Sugestão Compra (Un)", f"{df_dash['SUGESTAO_COMPRA'].sum():,.0f}".replace(',','.'))
        cobertura_media = df_dash.loc[df_dash['COBERTURA_MESES'] < 99, 'COBERTURA_MESES'].mean()
        c5.metric("Cobertura Média", f"{cobertura_media:.1f} Meses")

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. Gráficos (Grid 2x2)
        r1_c1, r1_c2 = st.columns(2)
        
        # Gráfico 1: Evolução de Vendas (Linha - Igual a imagem)
        with r1_c1:
            st.markdown("**Evolução Consolidada de Vendas (4 Meses)**")
            vendas = {'Mês 1': df_dash['VENDAS_M1_TOTAL'].sum(), 'Mês 2': df_dash['VENDAS_M2_TOTAL'].sum(), 
                      'Mês 3': df_dash['VENDAS_M3_TOTAL'].sum(), 'Atual': df_dash['VENDAS_M4_TOTAL'].sum()}
            df_v = pd.DataFrame(list(vendas.items()), columns=['Mês', 'Volume'])
            fig1 = px.line(df_v, x='Mês', y='Volume', markers=True, template="plotly_white", color_discrete_sequence=['#1da1f2'])
            fig1.update_traces(line=dict(width=3), marker=dict(size=8))
            st.plotly_chart(fig1, use_container_width=True)

        # Gráfico 2: Distribuição de Status (Barras Horizontais)
        with r1_c2:
            st.markdown("**Volume de SKUs por Status de Saúde**")
            status_df = df_dash['STATUS'].value_counts().reset_index()
            status_df.columns = ['Status', 'Qtd']
            cores = {'🔴 Crítico': '#ef4444', '🟡 Atenção': '#f59e0b', '🟢 OK': '#10b981'}
            fig2 = px.bar(status_df, y='Status', x='Qtd', color='Status', color_discrete_map=cores, orientation='h', template="plotly_white")
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        # Gráfico 3: Cobertura por Filial (Barras Verticais)
        st.markdown("**Disponibilidade Física por Filial**")
        cols_filiais = [c for c in df_dash.columns if 'ESTOQUE_' in c and c != 'ESTOQUE_TOTAL']
        if cols_filiais:
            df_melt = df_dash.melt(id_vars=['DESCRICAO'], value_vars=cols_filiais, var_name='Filial', value_name='Qtd')
            df_melt['Filial'] = df_melt['Filial'].str.replace('ESTOQUE_', '')
            fig3 = px.bar(df_melt.groupby('Filial')['Qtd'].sum().reset_index(), x='Filial', y='Qtd', template="plotly_white", color_discrete_sequence=['#3b82f6'])
            st.plotly_chart(fig3, use_container_width=True)

# ==========================================
# TELA 3: SUGESTÃO DE COMPRAS (TABELA PRO)
# ==========================================
elif menu == "🛒 3. Plano de Compras":
    st.title("Sugestão de Compras e Cobertura")
    if st.session_state.estoque_df.empty: st.warning("Importe os dados do TOTVS primeiro.")
    else:
        df_calc = gerar_analise_completa(st.session_state.estoque_df, st.session_state.pedidos_dict, multiplicador)
        df_calc = df_calc[df_calc['STATUS'].isin(filtro_status)]
        
        # Filtro de volume mínimo
        minimo = st.number_input("Ocultar sugestões de compra abaixo de (Unidades):", min_value=0, value=10)
        df_calc = df_calc[df_calc['SUGESTAO_COMPRA'] >= minimo]
        
        # Preparando colunas vitais para o Dataframe estilo BI
        df_view = df_calc[['CODIGO', 'DESCRICAO', 'STATUS', 'ESTOQUE_TOTAL', 'TRANSITO_PRODUCAO', 'MEDIA_TOTAL', 'COBERTURA_MESES', 'SUGESTAO_COMPRA']].copy()
        
        # Configuração das Colunas com Barras Nativas do Streamlit!
        st.dataframe(
            df_view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "CODIGO": st.column_config.TextColumn("Código", width="small"),
                "DESCRICAO": st.column_config.TextColumn("Produto", width="large"),
                "ESTOQUE_TOTAL": st.column_config.NumberColumn("Físico", format="%d"),
                "MEDIA_TOTAL": st.column_config.NumberColumn("Média/Mês", format="%.0f"),
                "COBERTURA_MESES": st.column_config.ProgressColumn(
                    "Cobertura (Meses)",
                    help="Quantos meses o estoque físico + trânsito vai durar.",
                    format="%.1f",
                    min_value=0, max_value=6 # Barra enche até 6 meses
                ),
                "SUGESTAO_COMPRA": st.column_config.NumberColumn("Comprar (Un)", format="%d", help="Quantidade sugerida para atingir a cobertura alvo.")
            }
        )
        
        # Exportar Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_view.to_excel(writer, index=False, sheet_name='Sugestao')
        st.download_button("📥 Exportar Relatório Excel", output.getvalue(), "Plano_Compras_Calisto.xlsx", type="primary")

# ==========================================
# AS OUTRAS TELAS MANTIDAS
# ==========================================
elif menu == "📥 1. Integração TOTVS":
    st.title("Base de Dados TOTVS")
    c1, c2 = st.columns(2)
    with c1: pdf_m = st.file_uploader("Matriz", type=['pdf']); pdf_r = st.file_uploader("Ribeirão", type=['pdf']); pdf_f = st.file_uploader("Franca", type=['pdf'])
    with c2: pdf_b = st.file_uploader("BH", type=['pdf']); pdf_l = st.file_uploader("Londrina", type=['pdf'])
    
    if st.button("Processar Documentos", type="primary"):
        dfs = []
        if pdf_m: dfs.append(ler_pdf_totvs(pdf_m, "MATRIZ"))
        if pdf_r: dfs.append(ler_pdf_totvs(pdf_r, "RIBEIRAO"))
        if pdf_f: dfs.append(ler_pdf_totvs(pdf_f, "FRANCA"))
        if pdf_b: dfs.append(ler_pdf_totvs(pdf_b, "BH"))
        if pdf_l: dfs.append(ler_pdf_totvs(pdf_l, "LONDRINA"))
        if dfs:
            st.session_state.estoque_df = consolidar_estoque(dfs)
            st.success("Dados sincronizados!")
    
    if not st.session_state.estoque_df.empty:
        st.subheader("Visualização e Correção (Físico)")
        st.session_state.estoque_df = st.data_editor(st.session_state.estoque_df, num_rows="dynamic")

elif menu == "🚢 2. Pedidos Importação":
    st.title("Gestão de Trânsito e Produção")
    up = st.file_uploader("Planilha do Fornecedor (Excel)", type=['xlsx', 'xls'])
    if up:
        xls = pd.ExcelFile(up)
        for s in xls.sheet_names:
            df_f = pd.read_excel(xls, sheet_name=s)
            for col in ["PRODUCAO_CHINA", "PREVISAO_EMBARQUE", "PREVISAO_CHEGADA", "QTD_PEDIDO"]:
                if col not in df_f.columns: df_f[col] = 0 if col in ["PRODUCAO_CHINA", "QTD_PEDIDO"] else ""
            st.session_state.pedidos_dict[f"{up.name} - {s}"] = df_f
        st.success("Pedidos processados!")

    if st.session_state.pedidos_dict:
        aba = st.selectbox("Aba/Fornecedor:", list(st.session_state.pedidos_dict.keys()))
        st.session_state.pedidos_dict[aba] = st.data_editor(st.session_state.pedidos_dict[aba], num_rows="dynamic")

elif menu == "👥 4. Fornecedores":
    st.title("Diretório de Fornecedores")
    with st.expander("➕ Novo Fornecedor", expanded=True):
        with st.form("form_f", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n = c1.text_input("Empresa *")
            p = c2.text_input("País")
            lt = c1.number_input("Transit Time (Dias)", step=1)
            c = c2.text_input("Contato")
            if st.form_submit_button("Salvar") and n.strip():
                st.session_state.fornecedores_df.loc[len(st.session_state.fornecedores_df)] = [n, p, lt, c]
                st.success(f"{n} salvo!")
                st.rerun()
    st.data_editor(st.session_state.fornecedores_df, use_container_width=True, num_rows="dynamic")

elif menu == "⚙️ 5. Sistema":
    st.title("Administração e Backup")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Salvar Progresso")
        bkp = {"estoque_df": st.session_state.estoque_df.to_json(orient='records'),
               "fornecedores_df": st.session_state.fornecedores_df.to_json(orient='records'),
               "pedidos_dict": {k: v.to_json(orient='records') for k, v in st.session_state.pedidos_dict.items()}}
        st.download_button("📦 Baixar Backup", json.dumps(bkp), "backup_calisto.json")
    with c2:
        st.subheader("Restaurar")
        up_bkp = st.file_uploader("Arquivo .json", type=['json'])
        if up_bkp and st.button("Restaurar"):
            d = json.load(up_bkp)
            st.session_state.estoque_df = pd.read_json(io.StringIO(d.get('estoque_df', '[]')))
            st.session_state.fornecedores_df = pd.read_json(io.StringIO(d.get('fornecedores_df', '[]')))
            st.session_state.pedidos_dict = {k: pd.read_json(io.StringIO(v)) for k, v in d.get('pedidos_dict', {}).items()}
            st.success("Restaurado!")
