import streamlit as st
import pandas as pd
import pypdf
import re
import json
import datetime
import plotly.express as px
import numpy as np
import io

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CSS (LIGHT THEME)
# ==========================================
st.set_page_config(page_title="Painel Operacional - Calisto", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* Esconde o menu lateral nativo para forçar navegação no topo */
    [data-testid="collapsedControl"] { display: none; }
    section[data-testid="stSidebar"] { display: none; }
    
    /* Fundo da aplicação */
    .stApp { background-color: #f8fafc; }
    
    /* Estilo dos Cartões (Métricas) idêntico ao print */
    [data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 12px !important;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 5px;
    }
    [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-size: 28px !important;
        font-weight: 700;
    }
    
    /* Alerta de Ruptura */
    .alert-box {
        background-color: #fef2f2;
        border: 1px solid #f87171;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 20px;
    }
    .alert-title { color: #dc2626; font-size: 12px; font-weight: bold; margin: 0 0 4px 0; text-transform: uppercase; }
    .alert-text { color: #111827; font-size: 18px; font-weight: 600; margin: 0 0 8px 0; }
    .alert-link { color: #3b82f6; font-size: 14px; text-decoration: none; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# VARIÁVEIS DE ESTADO
# ==========================================
if 'estoque_df' not in st.session_state: st.session_state.estoque_df = pd.DataFrame()
if 'pedidos_dict' not in st.session_state: st.session_state.pedidos_dict = {}
if 'import_log' not in st.session_state: st.session_state.import_log = []
if 'fornecedores_df' not in st.session_state: st.session_state.fornecedores_df = pd.DataFrame(columns=["Fornecedor", "País", "Lead Time", "Contato"])

# ==========================================
# FUNÇÕES DE PROCESSAMENTO
# ==========================================
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

def gerar_analise_completa(df_estoque, dict_pedidos, mult=2.0):
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
    df_calc['COBERTURA_MESES'] = np.where(df_calc['MEDIA_TOTAL'] > 0, df_calc['DISPONIBILIDADE_TOTAL'] / df_calc['MEDIA_TOTAL'], 99)
    df_calc['STATUS'] = np.where(df_calc['COBERTURA_MESES'] < 1.0, '🔴 Crítico', 
                                 np.where(df_calc['COBERTURA_MESES'] > mult, '🟢 OK', '🟡 Atenção'))
    return df_calc

# ==========================================
# 2. CABEÇALHO E MENU SUPERIOR (TOP NAV)
# ==========================================
col_logo, col_title, col_user = st.columns([1, 4, 1])
with col_logo:
    try:
        st.image("PASSALACQUA_Logo-Calisto&Co.png", width=150)
    except:
        st.markdown("**CALISTO & CO**")
with col_title:
    st.markdown("<h4 style='margin: 0; color: #0f172a;'>Compras de Importação</h4><p style='margin: 0; color: #64748b; font-size: 12px; text-transform: uppercase;'>Painel Operacional</p>", unsafe_allow_html=True)
with col_user:
    st.markdown("<p style='text-align: right; color: #64748b; font-size: 14px; margin-top: 10px;'>🟢 online</p>", unsafe_allow_html=True)

st.markdown("---")

# Menu Horizontal
menu = st.radio("Navegação", ["Dashboard", "Importar Dados", "Fornecedores", "Sugestão de Compra", "Backup"], horizontal=True, label_visibility="collapsed")

# ==========================================
# 3. TELAS DO SISTEMA
# ==========================================

if menu == "Dashboard":
    st.markdown("<h2 style='color: #0f172a;'>Dashboard</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748b;'>Visão geral de estoques nas 5 filiais, pedidos em andamento e sugestão de compras consolidada.</p>", unsafe_allow_html=True)
    
    if st.session_state.estoque_df.empty:
        st.info("Utilize a aba 'Importar Dados' no menu superior para iniciar.")
    else:
        df_dash = gerar_analise_completa(st.session_state.estoque_df, st.session_state.pedidos_dict, mult=2.0)
        itens_criticos = df_dash[df_dash['COBERTURA_MESES'] < 1.0]
        qtd_criticos = len(itens_criticos)
        
        # Alerta de Ruptura (Igual à Imagem)
        if qtd_criticos > 0:
            st.markdown(f"""
            <div class="alert-box">
                <p class="alert-title">• RISCO DE RUPTURA</p>
                <p class="alert-text">{qtd_criticos} SKU(s) com cobertura < 1 mês</p>
                <a href="#" class="alert-link">Ver sugestão &rarr;</a>
            </div>
            """, unsafe_allow_html=True)

        # Cartões
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("SKUS ATIVOS", f"{len(df_dash)}")
        c2.metric("ESTOQUE TOTAL", f"{df_dash['ESTOQUE_TOTAL'].sum():,.0f}".replace(',','.'))
        c3.metric("EM PRODUÇÃO", f"{df_dash['TRANSITO_PRODUCAO'].sum():,.0f}".replace(',','.'))
        c4.metric("EM TRÂNSITO", "0") # Placeholder como na imagem
        c5.metric("ITENS CRÍTICOS", f"{qtd_criticos}", delta=f"Sugestão total: {df_dash['SUGESTAO_COMPRA'].sum():,.0f}".replace(',','.'), delta_color="off")

        st.markdown("<br>", unsafe_allow_html=True)

        # Gráficos em Fundo Branco
        r1_c1, r1_c2 = st.columns(2)
        with r1_c1:
            st.markdown("##### Evolução de vendas (4 meses)")
            vendas = {'mar/2026': df_dash['VENDAS_M1_TOTAL'].sum(), 'abr/2026': df_dash['VENDAS_M2_TOTAL'].sum(), 
                      'mai/2026': df_dash['VENDAS_M3_TOTAL'].sum(), 'jun/2026': df_dash['VENDAS_M4_TOTAL'].sum()}
            df_v = pd.DataFrame(list(vendas.items()), columns=['Mês', 'Volume'])
            fig1 = px.line(df_v, x='Mês', y='Volume', markers=True)
            fig1.update_traces(line=dict(color='#cbd5e1'), marker=dict(size=8, color='#f59e0b'))
            fig1.update_layout(template="plotly_white", margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig1, use_container_width=True)

        with r1_c2:
            st.markdown("##### Produtos · Sugestão de compra (Top 10)")
            top_sugestoes = df_dash.nlargest(10, 'SUGESTAO_COMPRA')
            fig2 = px.bar(top_sugestoes, x='SUGESTAO_COMPRA', y='DESCRICAO', orientation='h')
            fig2.update_traces(marker_color='#000000') # Barras pretas como na imagem
            fig2.update_layout(template="plotly_white", margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Sugestão", yaxis_title=None)
            st.plotly_chart(fig2, use_container_width=True)

elif menu == "Importar Dados":
    st.markdown("<h2 style='color: #0f172a;'>Integração de Arquivos</h2>", unsafe_allow_html=True)
    
    st.subheader("1. Arquivos do TOTVS (PDF)")
    c1, c2 = st.columns(2)
    with c1: 
        pdf_m = st.file_uploader("Matriz", type=['pdf']); pdf_r = st.file_uploader("Ribeirão", type=['pdf']); pdf_f = st.file_uploader("Franca", type=['pdf'])
    with c2: 
        pdf_b = st.file_uploader("BH", type=['pdf']); pdf_l = st.file_uploader("Londrina", type=['pdf'])
    if st.button("Consolidar PDFs TOTVS", type="primary"):
        dfs = [ler_pdf_totvs(pdf, nome) for pdf, nome in [(pdf_m,"MATRIZ"), (pdf_r,"RIBEIRAO"), (pdf_f,"FRANCA"), (pdf_b,"BH"), (pdf_l,"LONDRINA")] if pdf]
        if dfs:
            st.session_state.estoque_df = consolidar_estoque(dfs)
            st.success("Dados de estoque atualizados!")

    st.markdown("---")
    st.subheader("2. Pedidos em Andamento (Excel)")
    up = st.file_uploader("Subir Excel do Fornecedor", type=['xlsx', 'xls'])
    if up:
        xls = pd.ExcelFile(up)
        for s in xls.sheet_names:
            df_f = pd.read_excel(xls, sheet_name=s)
            for col in ["QTD_PEDIDO"]:
                if col not in df_f.columns: df_f[col] = 0
            st.session_state.pedidos_dict[f"{up.name} - {s}"] = df_f
        st.success("Pedidos carregados nas memórias!")
    
    if st.session_state.pedidos_dict:
        aba = st.selectbox("Editar Pedidos/Trânsito:", list(st.session_state.pedidos_dict.keys()))
        st.session_state.pedidos_dict[aba] = st.data_editor(st.session_state.pedidos_dict[aba], num_rows="dynamic")

elif menu == "Fornecedores":
    st.markdown("<h2 style='color: #0f172a;'>Cadastro de Fornecedores</h2>", unsafe_allow_html=True)
    with st.form("form_f", clear_on_submit=True):
        c1, c2 = st.columns(2)
        n = c1.text_input("Nome da Empresa *")
        p = c2.text_input("País de Origem")
        if st.form_submit_button("Adicionar") and n.strip():
            st.session_state.fornecedores_df.loc[len(st.session_state.fornecedores_df)] = [n, p, 0, ""]
    st.data_editor(st.session_state.fornecedores_df, use_container_width=True, num_rows="dynamic")

elif menu == "Sugestão de Compra":
    st.markdown("<h2 style='color: #0f172a;'>Sugestão Consolidada</h2>", unsafe_allow_html=True)
    if st.session_state.estoque_df.empty: st.warning("Importe os dados primeiro.")
    else:
        mult = st.slider("Multiplicador da Média (Meses de Cobertura Alvo)", 1.0, 6.0, 2.0, 0.5)
        df_calc = gerar_analise_completa(st.session_state.estoque_df, st.session_state.pedidos_dict, mult)
        
        df_view = df_calc[['CODIGO', 'DESCRICAO', 'STATUS', 'ESTOQUE_TOTAL', 'TRANSITO_PRODUCAO', 'MEDIA_TOTAL', 'COBERTURA_MESES', 'SUGESTAO_COMPRA']]
        
        st.dataframe(
            df_view, use_container_width=True, hide_index=True,
            column_config={
                "ESTOQUE_TOTAL": st.column_config.NumberColumn("Físico"),
                "MEDIA_TOTAL": st.column_config.NumberColumn("Média/Mês"),
                "COBERTURA_MESES": st.column_config.ProgressColumn("Cobertura", format="%.1f meses", min_value=0, max_value=6),
                "SUGESTAO_COMPRA": st.column_config.NumberColumn("Comprar (Un)", format="%d")
            }
        )
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_view.to_excel(writer, index=False)
        st.download_button("📥 Exportar Relatório Excel", output.getvalue(), "Plano_Compras.xlsx", type="primary")

elif menu == "Backup":
    st.markdown("<h2 style='color: #0f172a;'>Manutenção de Dados</h2>", unsafe_allow_html=True)
    bkp = {"estoque_df": st.session_state.estoque_df.to_json(orient='records'),
           "pedidos_dict": {k: v.to_json(orient='records') for k, v in st.session_state.pedidos_dict.items()}}
    st.download_button("📦 Baixar Backup (.json)", json.dumps(bkp), "backup_calisto.json", type="primary")
