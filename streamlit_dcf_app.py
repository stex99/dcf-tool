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
        if cf is None or 'Total Cash From Operating Activities' not in cf or 'Capital Expenditures' not in cf:
            return None
        ocf = cf.loc['Total Cash From Operating Activities'].iloc[0]
        capex = cf.loc['Capital Expenditures'].iloc[0]
        return ocf + capex
    except:
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
        return "N/A"
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

        if intrinsic_value and shares_outstanding:
            dcf_per_share = intrinsic_value / shares_outstanding
            holding_value = dcf_per_share * shares
        else:
            dcf_per_share = None
            holding_value = None

        if holding_value:
            total_value += holding_value

        flag = valuation_flag(dcf_per_share, current_price)

        results.append({
            "Ticker": ticker,
            "Shares": shares,
            "DCF Value per Share ($)": round(dcf_per_share, 2) if dcf_per_share else "N/A",
            "Market Price ($)": round(current_price, 2) if current_price else "N/A",
            "Difference ($)": round((dcf_per_share - current_price), 2) if dcf_per_share and current_price else "N/A",
            "Upside/Downside (%)": round(((dcf_per_share - current_price) / current_price * 100), 2) if dcf_per_share and current_price else "N/A",
            "Valuation": flag,
            "Estimated Holding Value ($)": round(holding_value, 2) if holding_value else "N/A"
        })

    return pd.DataFrame(results), total_value

# Streamlit UI
st.title("📈 DCF Portfolio Analyzer")

st.sidebar.header("DCF Settings")
discount_rate = st.sidebar.slider("Discount Rate (%)", 5.0, 15.0, 10.0, 0.25) / 100
growth_rate = st.sidebar.slider("Growth Rate (%)", 0.0, 20.0, 5.0, 0.25) / 100
projection_years = st.sidebar.slider("Projection Period (Years)", 1, 10, 5, 1)

uploaded_file = st.file_uploader("Upload Portfolio CSV", type=["csv"])

st.markdown("""
**Upload Format:**  
A `.csv` file with at least two columns:
- `Ticker` (e.g., AAPL)
- `Shares` (e.g., 10)
""")

if uploaded_file:
    try:
        portfolio_df = pd.read_csv(uploaded_file)
        if 'Ticker' not in portfolio_df.columns or 'Shares' not in portfolio_df.columns:
            st.error("CSV must include 'Ticker' and 'Shares' columns.")
        else:
            with st.spinner("Performing DCF analysis..."):
                results_df, total_estimate = analyze_portfolio(
                    portfolio_df, discount_rate, growth_rate, projection_years
                )

            st.success("Analysis complete!")
            st.dataframe(results_df, use_container_width=True)
            st.subheader(f"💰 Estimated Total Portfolio Value: ${round(total_estimate, 2)}")

            # Export button
            csv_export = results_df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", csv_export, "dcf_results.csv", "text/csv")

            # Chart
            chart_df = results_df[
                (results_df["DCF Value per Share ($)"] != "N/A") &
                (results_df["Market Price ($)"] != "N/A")
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
