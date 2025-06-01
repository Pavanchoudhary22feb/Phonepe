# PhonePe Data Visualization with Filters, Pagination, and Export

import pandas as pd
import plotly.express as px
import mysql.connector as sql
import streamlit as st
from streamlit_option_menu import option_menu
import io
import requests
import json

# --- STREAMLIT CONFIG ---
st.set_page_config(page_title="PhonePe Dashboard", page_icon="📊", layout="wide")
st.sidebar.header("📱 Welcome to the PhonePe Dashboard")

# --- DATABASE CONNECTION ---
@st.cache_resource
def connect_db():
    return sql.connect(
        host="localhost",
        user="root",
        password="Choudhary@24",
        database="phonepe"
    )

try:
    Mydb = connect_db()
    cursor = Mydb.cursor(buffered=True)
except sql.Error as e:
    st.error(f"Database connection failed: {e}")
    st.stop()


# --- HELPER FUNCTION ---
def fetch_dataframe(query, params=None, columns=None):
    cursor.execute(query, params)
    rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)

# --- SIDEBAR MENU ---
with st.sidebar:
    selected = option_menu("Menu",
                           ["Home", "Top Charts", "Explore Data", "Visual Insights", "Top Locations", "About"],
                           icons=["house", "bar-chart", "search", "pie-chart", "geo-alt", "info-circle"],
                           menu_icon="cast", default_index=0)

# --- HOME ---
if selected == "Home":
    st.title("📊 PhonePe Data Visualization")
    st.subheader("Explore transactions, users, and trends across India using PhonePe data.")
    st.image("https://upload.wikimedia.org/wikipedia/commons/f/f0/PhonePe_Logo.png", width=200)
    st.markdown("""
    ### Domain: Fintech  
    ### Technologies: Python, Pandas, MySQL, Streamlit, Plotly  
    This dashboard provides insights into PhonePe transactions and user behaviors across states, districts, and mobile brands.
    """)

# --- TOP CHARTS ---
elif selected == "Top Charts":
    st.header("Top Charts")
    Type = st.selectbox("Type", ["Transactions", "Users"])
    Year = st.selectbox("Year", ['2018', '2019', '2020', '2021', '2022'])
    Quarter = st.selectbox("Quarter", ['1', '2', '3', '4'])

    cursor.execute("SELECT DISTINCT State FROM aggregated_trans ORDER BY State;")
    state_options = ["All"] + [row[0] for row in cursor.fetchall()]
    selected_state = st.selectbox("Filter by State", state_options)

    if Type == "Transactions":
        query = """
            SELECT State, ROUND(SUM(Transaction_amount), 2) AS Total
            FROM aggregated_trans
            WHERE Year = %s AND Quarter = %s
        """
        params = [Year, Quarter]
        if selected_state != "All":
            query += " AND State = %s"
            params.append(selected_state)
        query += " GROUP BY State ORDER BY Total DESC LIMIT 10;"
        df = fetch_dataframe(query, params, ['State', 'Total'])
        fig = px.bar(df, x='Total', y='State', orientation='h', color='Total',
                     title='Top 10 States by Transaction Amount (in Millions)')
        st.plotly_chart(fig, use_container_width=True)

    else:
        if Year == "2022" and Quarter in ["2", "3", "4"]:
            st.warning("No user data available for 2022 Q2–Q4")
        else:
            query = """
                SELECT Brands, SUM(Count) AS Users, ROUND(AVG(Percentage), 2) AS Percentage
                FROM aggregate_user
                WHERE Year = %s AND Quarter = %s
                GROUP BY Brands
                ORDER BY Users DESC
                LIMIT 10;
            """
            df = fetch_dataframe(query, (Year, Quarter), ['Brands', 'Users', 'Percentage'])
            fig = px.bar(df, x='Users', y='Brands', orientation='h', color='Percentage',
                         title='Top 10 Brands by User Count (%)')
            st.plotly_chart(fig, use_container_width=True)

# --- EXPLORE DATA ---
elif selected == "Explore Data":
    st.header("Explore Raw Data")
    table = st.selectbox("Choose Table", ["aggregate_user", "aggregated_trans", "map_trans", "map_user", "top_trans", "top_user"])
    query = f"SELECT * FROM `{table}`;"
    cursor.execute(query)
    columns = [i[0] for i in cursor.description]
    df = pd.DataFrame(cursor.fetchall(), columns=columns)

    search_term = st.text_input("Search:")
    if search_term:
        df = df[df.astype(str).apply(lambda row: row.str.contains(search_term, case=False)).any(axis=1)]

    rows_per_page = st.slider("Rows per page", 10, 100, 20)
    page = st.number_input("Page", min_value=1, max_value=(len(df) // rows_per_page) + 1, step=1)
    start = (page - 1) * rows_per_page
    end = start + rows_per_page
    st.dataframe(df.iloc[start:end], use_container_width=True)

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download CSV", csv, "data.csv", "text/csv")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    st.download_button("⬇️ Download Excel", output.getvalue(), "data.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --- VISUAL INSIGHTS ---
elif selected == "Visual Insights":
    st.header("📈 Visual Insights by State")
    cursor.execute("SELECT DISTINCT State FROM aggregated_trans ORDER BY State;")
    states = [row[0] for row in cursor.fetchall()]
    state = st.selectbox("Choose State", states)
    metric = st.radio("Metric", ["Transaction Amount", "RegisteredUsers"])

    if metric == "Transaction Amount":
        query = """
            SELECT Year, Quarter, SUM(Transaction_amount)
            FROM aggregated_trans
            WHERE State = %s
            GROUP BY Year, Quarter
            ORDER BY Year, Quarter;
        """
        df = fetch_dataframe(query, (state,), ['Year', 'Quarter', 'Amount'])
    else:
        query = """
            SELECT Year, Quarter, SUM(RegisteredUser) AS Users
            FROM map_user
            WHERE State = %s
            GROUP BY Year, Quarter
            ORDER BY Year, Quarter;
        """
        df = fetch_dataframe(query, (state,), ['Year', 'Quarter', 'Users'])

    if df.empty:
        st.warning("No data available for the selected state and metric.")
    else:
        df['Year-Quarter'] = df['Year'].astype(str) + "-Q" + df['Quarter'].astype(str)
        y_col = 'Amount' if metric == "Transaction Amount" else 'Users'
        fig = px.line(df, x='Year-Quarter', y=y_col, title=f'{state} - {metric} Over Time')
        st.plotly_chart(fig, use_container_width=True)

# --- TOP LOCATIONS ---
elif selected == "Top Locations":
    st.header("🗺️ Interactive Map: State Overview + District Drilldown")

    dataset = st.selectbox("Select Dataset", ["Transactions", "Registered Users"])
    year = st.selectbox("Select Year", ['2018', '2019', '2020', '2021', '2022'])
    quarter = st.selectbox("Select Quarter", ['1', '2', '3', '4'])

    # --- GeoJSON Loaders ---
    @st.cache_data
    def load_state_geojson():
        with open(r"D:\DSprojects\Phonepe\Geo_Json\india_state.geojson", "r", encoding="utf-8") as f:
            return json.load(f)

    @st.cache_data
    def load_district_geojson():
        with open(r"D:\DSprojects\Phonepe\Geo_Json\india_district.geojson", "r", encoding="utf-8") as f:
            return json.load(f)

    state_geojson = load_state_geojson()
    district_geojson = load_district_geojson()

    # --- Data Fetch ---
    if dataset == "Transactions":
        query = """
            SELECT State, District, SUM(Amount) AS Total_Amount
            FROM map_trans
            WHERE Year = %s AND Quarter = %s
            GROUP BY State, District
        """
        df = fetch_dataframe(query, [year, quarter], ["State", "District", "Total_Amount"])
        df["Value"] = df["Total_Amount"]
        label = "Transaction Amount (₹Millions)"
    else:
        query = """
            SELECT State, District, SUM(RegisteredUser) AS Total_Users
            FROM map_user
            WHERE Year = %s AND Quarter = %s
            GROUP BY State, District
        """
        df = fetch_dataframe(query, [year, quarter], ["State", "District", "Total_Users"])
        df["Value"] = df["Total_Users"]
        label = "Registered Users"

    df["State"] = df["State"].str.title().str.strip()
    df["District"] = df["District"].str.title().str.strip()

    # --- STATE LEVEL MAP ---
    state_df = df.groupby("State")["Value"].sum().reset_index()
    geojson_states = {f["properties"]["NAME_1"].title() for f in state_geojson["features"]}
    state_df = state_df[state_df["State"].isin(geojson_states)]

    st.subheader("🧭 State-wise Overview")
    fig_state = px.choropleth(
        state_df,
        geojson=state_geojson,
        featureidkey="properties.NAME_1",
        locations="State",
        color="Value",
        color_continuous_scale="Purples",
        title=f"{label} by State"
    )
    fig_state.update_geos(fitbounds="locations", visible=False)
    fig_state.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
    st.plotly_chart(fig_state, use_container_width=True)

    # --- STATE SELECTION FOR DRILLDOWN ---
    selected_state = st.selectbox("🔍 Select a State to view District-level data", sorted(state_df["State"].unique()))

    # --- DISTRICT LEVEL MAP ---
    st.subheader(f"🏙️ District-level View for {selected_state}")

    district_df = df[df["State"] == selected_state]
    geojson_districts = {f["properties"]["NAME_2"].title() for f in district_geojson["features"]}
    district_df = district_df[district_df["District"].isin(geojson_districts)]

    map_district_df = district_df[["District", "Value"]].groupby("District").sum().reset_index()

    if not map_district_df.empty:
        fig_district = px.choropleth(
            map_district_df,
            geojson=district_geojson,
            featureidkey="properties.NAME_2",  # Adjust if your file uses a different key
            locations="District",
            color="Value",
            color_continuous_scale="Purples",
            title=f"{label} by District in {selected_state}"
        )
        fig_district.update_geos(fitbounds="locations", visible=False)
        fig_district.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
        st.plotly_chart(fig_district, use_container_width=True)
    else:
        st.warning("No district data available for the selected state.")

    # --- Data Table ---
    with st.expander("📋 View District-level Data"):
        st.dataframe(district_df.sort_values("Value", ascending=False), use_container_width=True)


# --- ABOUT ---
elif selected == "About":
    st.title("📘 About This Project")
    st.markdown("""
    - **Project Name:** PhonePe Data Visualization  
    - **Developer:** [Pavan Kumar]  
    - **Purpose:** Analyze and visualize PhonePe data trends across India  
    - **Data Source:** [PhonePe Pulse](https://www.phonepe.com/pulse/)
    """)
