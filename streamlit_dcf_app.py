
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import altair as alt
from io import StringIO

st.set_page_config(page_title="DCF Portfolio Analyzer", layout="wide")

def get_fcf(ticker):
    stock = yf.Ticker(ticker)
    cf = stock.cashflow

    if cf is None or cf.empty:
        return None

    def find_label(possible_labels):
        for label in possible_labels:
            for idx in cf.index:
                if label.lower() in idx.lower():
                    return cf.loc[idx].iloc[0]
        return None

    ocf = find_label(['Total Cash From Operating Activities', 'Operating Cash Flow'])
    capex = find_label(['Capital Expenditures', 'Capital Expenditures - Fixed Assets'])

    if ocf is None or capex is None:
        return stock.info.get("freeCashflow", None)

    return ocf + capex

def dcf_valuation(fcf, discount_rate=0.10, growth_rate=0.05, projection_years=5):
    if fcf is None or fcf <= 0:
        return None
    npv = sum(
        fcf * (1 + growth_rate) ** year / (1 + discount_rate) ** year
        for year in range(1, projection_years + 1)
    )
    terminal_value = (fcf * (1 + growth_rate) ** projection_years) * (1 + growth_rate) / (discount_rate - growth_rate)
    terminal_value_discounted = terminal_value / (1 + discount_rate) ** projection_years
    return npv + terminal_value_discounted

def analyze_portfolio(df, discount_rate, growth_rate, projection_years):
    results = []
    for _, row in df.iterrows():
        ticker = row['Ticker']
        shares = row['Shares']
        fcf = get_fcf(ticker)
        intrinsic_value = dcf_valuation(fcf, discount_rate, growth_rate, projection_years)

        stock = yf.Ticker(ticker)
        shares_outstanding = stock.info.get("sharesOutstanding", None)
        current_price = stock.info.get("currentPrice", None)

        value_per_share = (intrinsic_value / shares_outstanding) if intrinsic_value and shares_outstanding else None

        results.append({
            "Ticker": ticker,
            "Shares": shares,
            "DCF Value per Share ($)": round(value_per_share, 2) if value_per_share else None,
            "Market Price ($)": round(current_price, 2) if current_price else None
        })

    return pd.DataFrame(results)

st.title("📈 DCF Portfolio Analyzer")

st.sidebar.header("DCF Settings")
discount_rate = st.sidebar.slider("Discount Rate (%)", 5.0, 15.0, 10.0, 0.25) / 100
growth_rate = st.sidebar.slider("Growth Rate (%)", 0.0, 20.0, 5.0, 0.25) / 100
projection_years = st.sidebar.slider("Projection Period (Years)", 1, 10, 5, 1)

uploaded_file = st.file_uploader("Upload Portfolio CSV", type=["csv"])

if uploaded_file is None:
    st.info("No file uploaded. Using example portfolio.")
    uploaded_file = StringIO("""Ticker,Shares
AAPL,20
MSFT,15
GOOGL,10
NVDA,8
JNJ,25
""")

portfolio_df = pd.read_csv(uploaded_file)

if 'Ticker' not in portfolio_df.columns or 'Shares' not in portfolio_df.columns:
    st.error("CSV must include 'Ticker' and 'Shares' columns.")
else:
    results_df = analyze_portfolio(portfolio_df, discount_rate, growth_rate, projection_years)
    display_df = results_df.dropna()
    st.dataframe(display_df, use_container_width=True)

    chart_df = display_df.melt(
        id_vars="Ticker",
        value_vars=["DCF Value per Share ($)", "Market Price ($)"],
        var_name="Type",
        value_name="Price"
    )

    st.subheader("📊 DCF vs. Market Price per Stock")

    base = alt.Chart(chart_df).encode(
        x=alt.X('Ticker:N', title='Stock'),
        y=alt.Y('Price:Q', title='Per Share Value ($)'),
        color=alt.Color('Type:N'),
        tooltip=['Ticker', 'Type', 'Price']
    )

    bars = base.transform_filter(alt.datum.Type == "DCF Value per Share ($)").mark_bar()
    line = base.transform_filter(alt.datum.Type == "Market Price ($)").mark_line(point=True, strokeDash=[4, 2])
    chart = (bars + line).properties(height=400)

    st.altair_chart(chart, use_container_width=True)
