
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import altair as alt

st.set_page_config(page_title="DCF Portfolio Analyzer", layout="wide")

def get_fcf(ticker):
    try:
        stock = yf.Ticker(ticker)
        cf = stock.cashflow
        if cf is None or cf.empty:
            st.warning(f"No cash flow data for {ticker}")
            return None
        ocf = cf.loc['Total Cash From Operating Activities'].iloc[0]
        capex = cf.loc['Capital Expenditures'].iloc[0]
        fcf = ocf + capex
        st.write(f"{ticker} FCF: OCF={ocf}, CapEx={capex}, FCF={fcf}")
        return fcf
    except Exception as e:
        st.warning(f"Error retrieving FCF for {ticker}: {e}")
        return None

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

def valuation_flag(dcf, market, tolerance=0.1):
    if not dcf or not market:
        return None
    diff = (dcf - market) / market
    if diff > tolerance:
        return "Undervalued"
    elif diff < -tolerance:
        return "Overvalued"
    else:
        return "Fairly Valued"

def analyze_portfolio(df, discount_rate, growth_rate, projection_years):
    results = []
    total_value = 0

    for _, row in df.iterrows():
        ticker = row['Ticker']
        shares = row['Shares']
        fcf = get_fcf(ticker)
        intrinsic_value = dcf_valuation(fcf, discount_rate, growth_rate, projection_years)

        stock = yf.Ticker(ticker)
        shares_outstanding = stock.info.get("sharesOutstanding", None)
        current_price = stock.info.get("currentPrice", None)

        if not shares_outstanding:
            st.warning(f"{ticker}: Missing 'sharesOutstanding' in yfinance data.")

        value_per_share = (intrinsic_value / shares_outstanding) if intrinsic_value and shares_outstanding else None
        holding_value = value_per_share * shares if value_per_share else None

        if holding_value:
            total_value += holding_value

        flag = valuation_flag(value_per_share, current_price)

        results.append({
            "Ticker": ticker,
            "Shares": shares,
            "DCF Value per Share ($)": round(value_per_share, 2) if value_per_share else None,
            "Market Price ($)": round(current_price, 2) if current_price else None,
            "Difference ($)": round((value_per_share - current_price), 2) if value_per_share and current_price else None,
            "Upside/Downside (%)": round(((value_per_share - current_price) / current_price * 100), 2) if value_per_share and current_price else None,
            "Valuation": flag,
            "Estimated Holding Value ($)": round(holding_value, 2) if holding_value else None
        })

    return pd.DataFrame(results), total_value

st.title("📈 DCF Portfolio Analyzer")

st.sidebar.header("DCF Settings")
discount_rate = st.sidebar.slider("Discount Rate (%)", 5.0, 15.0, 10.0, 0.25) / 100
growth_rate = st.sidebar.slider("Growth Rate (%)", 0.0, 20.0, 5.0, 0.25) / 100
projection_years = st.sidebar.slider("Projection Period (Years)", 1, 10, 5, 1)


uploaded_file = st.file_uploader("Upload Portfolio CSV", type=["csv"])

# Fallback to sample CSV if nothing is uploaded
if uploaded_file is None:
    st.info("No file uploaded. Using example portfolio.")
    from io import StringIO
    uploaded_file = StringIO("""Ticker,Shares
AAPL,20
MSFT,15
GOOGL,10
NVDA,8
JNJ,25
""")


if uploaded_file:
    try:
        portfolio_df = pd.read_csv(uploaded_file)
        if 'Ticker' not in portfolio_df.columns or 'Shares' not in portfolio_df.columns:
            st.error("CSV must include 'Ticker' and 'Shares' columns.")
        else:
            with st.spinner("Analyzing portfolio..."):
                results_df, total_estimate = analyze_portfolio(portfolio_df, discount_rate, growth_rate, projection_years)

            display_df = results_df.fillna("N/A")
            st.dataframe(display_df, use_container_width=True)
            st.subheader(f"💰 Estimated Total Portfolio Value: ${round(total_estimate, 2)}")

            csv_export = display_df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", csv_export, "dcf_results.csv", "text/csv")

            chart_df = display_df[
                (display_df["DCF Value per Share ($)"] != "N/A") &
                (display_df["Market Price ($)"] != "N/A")
            ].copy()

            chart_df["DCF Value per Share ($)"] = pd.to_numeric(chart_df["DCF Value per Share ($)"])
            chart_df["Market Price ($)"] = pd.to_numeric(chart_df["Market Price ($)"])

            chart_data = chart_df.melt(
                id_vars="Ticker",
                value_vars=["DCF Value per Share ($)", "Market Price ($)"],
                var_name="Type",
                value_name="Price"
            )

            st.subheader("📊 DCF vs. Market Price")
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('Ticker:N'),
                y=alt.Y('Price:Q'),
                color='Type:N',
                column='Type:N'
            ).properties(height=300).configure_axis(labelAngle=0)

            st.altair_chart(chart, use_container_width=True)
    except Exception as e:
        st.error(f"Something went wrong: {e}")
