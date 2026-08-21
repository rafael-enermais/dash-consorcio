"""
Painel de Usinas — Consórcio Enermais Energia (Streamlit)
Mesmo padrão do RADAR/RHDADOS: login real via Supabase Auth, tema EnerMais,
roda local (streamlit run) ou hospedado no Streamlit Community Cloud.

pip install -r requirements.txt
streamlit run app_painel_usinas.py
"""

import base64
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo-enermais.png")
APP_VERSION = "1.0"  # atualizar a cada versão nova


@st.cache_data
def logo_base64():
    with open(LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()


def render_logo(height=56):
    st.markdown(
        f"""
        <img src="data:image/png;base64,{logo_base64()}" height="{height}"
             style="filter: brightness(0) invert(1); margin-bottom: 12px;">
        """,
        unsafe_allow_html=True,
    )


def config(chave):
    """Lê do .env local OU dos 'Secrets' do Streamlit Cloud — mesmo arquivo
    funciona nos dois lugares sem mudar nada (padrão RADAR)."""
    try:
        if chave in st.secrets:
            return st.secrets[chave]
    except Exception:
        pass
    return os.environ[chave]


SUPABASE_URL = config("SUPABASE_URL")
SUPABASE_ANON_KEY = config("SUPABASE_ANON_KEY")  # anon/publishable key, NUNCA a service_role
supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

st.set_page_config(page_title="Painel de Usinas — EnerMais", page_icon="⚡", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        background-color: #0A0C2E;
        min-width: 260px;
        max-width: 260px;
    }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #F99D20;
    }
    hr { border-color: #F99D20 !important; opacity: 0.5; }
    [data-testid="stSidebarUserContent"], [data-testid="stSidebar"] > div:first-child {
        padding-top: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- login (Supabase Auth nativo — crie os usuários em Authentication > Users
#     no projeto "consorcio-enermais", igual já feito no RADAR/RHDADOS) ---
if "session" not in st.session_state:
    st.session_state.session = None

if st.session_state.session is None:
    render_logo(height=72)
    st.title("Painel de Usinas — login")
    email = st.text_input("E-mail")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        try:
            resp = supabase.auth.sign_in_with_password({"email": email, "password": senha})
            st.session_state.session = resp.session
            st.rerun()
        except Exception as e:
            st.error(f"Login inválido: {e}")
    st.stop()

# Reanexa o token a cada rerun (senão as consultas seguintes viajam como
# usuário anônimo e a política de segurança do banco bloqueia silenciosamente
# — mesma lição do RADAR).
supabase.postgrest.auth(st.session_state.session.access_token)

with st.sidebar:
    render_logo(height=72)
    st.caption(f"Logado como: {st.session_state.session.user.email}")
    if st.button("Sair"):
        st.session_state.session = None
        st.rerun()
    if st.button("🔄 Recarregar dados"):
        st.cache_data.clear()
        st.rerun()

# --- painel principal ---
st.title("Painel de Usinas — Consórcio Enermais")
st.caption("Capacidade instalada e comprometimento por usina e concessionária — dados anonimizados (sem PII).")


@st.cache_data(ttl=300, show_spinner="Carregando dados do Supabase...")
def carregar_dados(_client):
    dados = _client.table("vw_dashboard_usinas_publico").select("*").order("usina_codigo").execute().data
    return pd.DataFrame(dados)


df = carregar_dados(supabase)

if df.empty:
    st.info("Nenhuma usina cadastrada ainda.")
    st.stop()

# --- resumo por concessionária ---
st.subheader("Resumo por concessionária")
resumo = (
    df.groupby("concessionaria")
    .agg(
        qtd_usinas=("usina_codigo", "count"),
        potencia_kwh=("potencia_kwh", "sum"),
        kwh_comprometido=("kwh_comprometido", "sum"),
        geracao_disponivel_venda=("geracao_disponivel_venda", "sum"),
    )
    .reset_index()
)

cols = st.columns(len(resumo)) if len(resumo) <= 4 else st.columns(4)
for i, row in resumo.iterrows():
    col = cols[i % len(cols)]
    with col:
        st.metric(
            label=f"{row['concessionaria']} — {int(row['qtd_usinas'])} usina(s)",
            value=f"{row['potencia_kwh']:,.0f} kWh".replace(",", "."),
        )
        st.caption(
            f"Comprometido: {row['kwh_comprometido']:,.0f} · "
            f"Disponível: {row['geracao_disponivel_venda']:,.0f} kWh".replace(",", ".")
        )

st.divider()

# --- detalhe por usina ---
st.subheader("Detalhe por usina")

with st.sidebar:
    st.divider()
    st.header("Filtros")
    concessionarias = st.multiselect("Concessionária", sorted(df["concessionaria"].dropna().unique()))
    status_usina = st.multiselect("Status", sorted(df["status_usina"].dropna().unique()))

df_filtrado = df.copy()
if concessionarias:
    df_filtrado = df_filtrado[df_filtrado["concessionaria"].isin(concessionarias)]
if status_usina:
    df_filtrado = df_filtrado[df_filtrado["status_usina"].isin(status_usina)]

st.dataframe(
    df_filtrado.rename(columns={
        "usina_codigo": "Código",
        "concessionaria": "Concessionária",
        "uf": "UF",
        "tipo_gd": "Tipo GD",
        "status_usina": "Status",
        "potencia_kwp": "Potência (kWp)",
        "potencia_kwh": "Capacidade (kWh)",
        "kwh_comprometido": "Comprometido (kWh)",
        "kwh_efetivo_rateado": "Rateado Efetivo (kWh)",
        "geracao_disponivel_venda": "Disponível p/ Venda (kWh)",
    }),
    use_container_width=True,
    hide_index=True,
)

st.markdown(
    f"""
    <div style="margin-top: 2rem; padding-top: 0.75rem;
                border-top: 1px solid rgba(245,246,250,0.12);
                font-size: 0.72rem; color: rgba(245,246,250,0.45);">
        Painel de Usinas EnerMais · v{APP_VERSION} · dados em tempo real (vw_dashboard_usinas_publico) · rafael.nakahara@enermais.com.br
    </div>
    """,
    unsafe_allow_html=True,
)
