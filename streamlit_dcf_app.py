
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import altair as alt
from io import StringIO

st.set_page_config(page_title="DCF Portfolio Analyzer", layout="wide")

log_entries = []

def get_fcf(ticker):
    try:
        stock = yf.Ticker(ticker)
        cf = stock.cashflow

        if cf is None or cf.empty:
            msg = f"No cash flow data available for {ticker}"
            st.warning(msg)
            log_entries.append(msg)
            return None

        st.write(f"{ticker} cashflow index: {list(cf.index)}")

        def find_label(possible_labels):
            for label in possible_labels:
                for idx in cf.index:
                    if label.lower() in idx.lower():
                        return cf.loc[idx].iloc[0]
            return None

        ocf = find_label(['Total Cash From Operating Activities', 'Operating Cash Flow'])
        capex = find_label(['Capital Expenditures', 'Capital Expenditures - Fixed Assets'])

        if ocf is None or capex is None:
            fallback_fcf = stock.info.get("freeCashflow", None)
            if fallback_fcf:
                msg = f"{ticker}: Used fallback FCF from summary: {fallback_fcf}"
                st.info(msg)
                log_entries.append(msg)
                return fallback_fcf
            else:
                msg = f"{ticker} missing OCF or CapEx and no fallback FCF available"
                st.warning(msg)
                log_entries.append(msg)
                return None

        fcf = ocf + capex
        msg = f"{ticker} FCF = {fcf}"
        st.write(msg)
        log_entries.append(msg)
        return fcf

    except Exception as e:
        msg = f"Error retrieving FCF for {ticker}: {e}"
        st.warning(msg)
        log_entries.append(msg)
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

if uploaded_file is None:
    st.info("No file uploaded. Using example portfolio.")
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

            if log_entries:
                log_output = "\n".join(log_entries)
                st.download_button("📄 Download Log File", log_output, "dcf_log.txt")

            # Charts
            chart_df = display_df[
                (display_df["DCF Value per Share ($)"] != "N/A") &
                (display_df["Market Price ($)"] != "N/A")
            ].copy()

            chart_df["DCF Value per Share ($)"] = pd.to_numeric(chart_df["DCF Value per Share ($)"])
            chart_df["Market Price ($)"] = pd.to_numeric(chart_df["Market Price ($)"])

            # Historical DCF trend
            dcf_trend_data = []
            for ticker in chart_df["Ticker"].unique():
                stock = yf.Ticker(ticker)
                cf = stock.cashflow
                shares_outstanding = stock.info.get("sharesOutstanding", None)

                try:
                    if cf is not None and not cf.empty and shares_outstanding:
                        years = list(cf.columns)[:5]
                        for year in years:
                            ocf = cf.loc["Total Cash From Operating Activities"][year] if "Total Cash From Operating Activities" in cf.index else None
                            capex = cf.loc["Capital Expenditures"][year] if "Capital Expenditures" in cf.index else None
                            if ocf and capex:
                                fcf = ocf + capex
                                dcf_value = fcf * 1.05 / (0.10 - 0.05)
                                dcf_per_share = dcf_value / shares_outstanding
                                dcf_trend_data.append({
                                    "Ticker": ticker,
                                    "Year": str(year.year) if hasattr(year, 'year') else str(year),
                                    "DCF": round(dcf_per_share, 2)
                                })
                except Exception as e:
                    st.warning(f"Failed historical DCF for {ticker}: {e}")
                    continue

                if cf is not None and not cf.empty and shares_outstanding:
                    try:
                        years = list(cf.columns)[:5]
                        for year in years:
                            ocf = cf.loc["Total Cash From Operating Activities"][year] if "Total Cash From Operating Activities" in cf.index else None
                            capex = cf.loc["Capital Expenditures"][year] if "Capital Expenditures" in cf.index else None
                            if ocf and capex:
                                fcf = ocf + capex
                                dcf_value = fcf * 1.05 / (0.10 - 0.05)
                                dcf_per_share = dcf_value / shares_outstanding
                                dcf_trend_data.append({
                                    "Ticker": ticker,
                                    "Year": str(year.year) if hasattr(year, 'year') else str(year),
                                    "DCF": round(dcf_per_share, 2)
                                })
                    except Exception as e:
                        st.warning(f"Failed historical DCF for {ticker}: {e}")
                        continue

            dcf_trend_df = pd.DataFrame(dcf_trend_data)

            # Superimpose market price
            current_prices = chart_df[["Ticker", "Market Price ($)"]].drop_duplicates()
            latest_year = max(dcf_trend_df["Year"].unique())

            price_overlay_data = pd.DataFrame([{
                "Ticker": row["Ticker"],
                "Year": latest_year,
                "Value": row["Market Price ($)"],
                "Type": "Market Price"
            } for _, row in current_prices.iterrows()])

            dcf_trend_df["Value"] = dcf_trend_df["DCF"]
            dcf_trend_df["Type"] = "Historical DCF"
            trend_combined = pd.concat([dcf_trend_df[["Ticker", "Year", "Value", "Type"]], price_overlay_data])

            line = alt.Chart(trend_combined).mark_line(point=True).encode(
                x=alt.X("Year:O", title="Year"),
                y=alt.Y("Value:Q", title="Per Share Value ($)"),
                color=alt.Color("Type:N"),
                strokeDash='Type:N',
                tooltip=["Ticker", "Year", "Type", "Value"]
            )

            super_chart = alt.FacetChart(
                data=trend_combined,
                facet=alt.Facet("Ticker:N", columns=3),
                spec=line.properties(height=300),
                title="Historical DCF with Market Price Overlay"
            )

            st.altair_chart(super_chart, use_container_width=True)
    except Exception as e:
        st.error(f"Something went wrong: {e}")
