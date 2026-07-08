
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import zipfile, io, csv, re
from datetime import datetime, date, timedelta
from collections import defaultdict

st.set_page_config(page_title="NAMO Plus Sales Dashboard", layout="wide")
st.title("NAMO Plus Sales Dashboard")
st.caption("Upload Square item sales ZIP/CSV. Dashboard filters to NAMO Plus categories only.")

TARGET_CATEGORIES = {
    "acai bowls & smoothies": "Acai bowls & Smoothies",
    "coffee & more": "Coffee & more",
    "fruit tea": "Fruit tea",
    "milk tea": "Milk tea",
    "namo plus": "Namo Plus",
    "namo plus extras": "Namo Plus Extras",
    "smoothies": "Smoothies",
    "specials": "Specials",
}

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())

def parse_money(s):
    s = str(s or "").replace("€", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try: return float(s)
    except: return 0.0

def load_square_file(uploaded):
    files=[]
    name=uploaded.name.lower()
    if name.endswith('.zip'):
        z=zipfile.ZipFile(uploaded)
        for n in z.namelist():
            if n.lower().endswith('.csv'):
                files.append((n, z.open(n)))
    else:
        files.append((uploaded.name, uploaded))
    frames=[]
    for fname, fh in files:
        df=pd.read_csv(fh, encoding='utf-16', sep='\t', low_memory=False)
        df.columns=(df.columns.str.strip().str.lower().str.replace(' ','_',regex=False).str.replace('-','_',regex=False))
        frames.append(df)
    return pd.concat(frames, ignore_index=True)

uploaded = st.file_uploader("Upload Square item sales ZIP or CSV", type=["zip","csv"])
if uploaded is None:
    st.info("Upload your current and previous Square item sales exports to begin.")
    st.stop()

df = load_square_file(uploaded)

# Clean columns
if 'category' not in df.columns or 'item' not in df.columns:
    st.error("Required columns missing. Expected Square item sales export with Category and Item columns.")
    st.stop()

df['category_norm'] = df['category'].map(norm)
df = df[df['category_norm'].isin(TARGET_CATEGORIES.keys())].copy()
df['category_clean'] = df['category_norm'].map(TARGET_CATEGORIES)
if 'event_type' in df.columns:
    df = df[df['event_type'].eq('Payment')].copy()

df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date
df = df.dropna(subset=['date','item'])
df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
df['net_sales'] = df['net_sales'].apply(parse_money)
df['gross_sales'] = df.get('gross_sales',0).apply(parse_money) if 'gross_sales' in df.columns else df['net_sales']
df['location'] = df['location'].fillna('Unknown') if 'location' in df.columns else 'Unknown'
df['transaction_id'] = df['transaction_id'].fillna('') if 'transaction_id' in df.columns else ''

st.sidebar.header("Filters")
locations = sorted(df['location'].dropna().unique())
selected_locations = st.sidebar.multiselect("Shop", locations, default=locations)
min_date, max_date = df['date'].min(), df['date'].max()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
metric = st.sidebar.radio("Main metric", ["Net Revenue", "Quantity"], horizontal=True)

if selected_locations:
    df = df[df['location'].isin(selected_locations)]
if len(date_range)==2:
    df = df[(df['date']>=date_range[0]) & (df['date']<=date_range[1])]

if df.empty:
    st.warning("No rows match the selected filters.")
    st.stop()

# KPIs
total_rev=df['net_sales'].sum(); total_qty=df['qty'].sum(); total_trans=df['transaction_id'].nunique(); avg_price=total_rev/total_qty if total_qty else 0
best_drink = df.groupby('item')['net_sales'].sum().idxmax() if not df.empty else '-'
best_shop = df.groupby('location')['net_sales'].sum().idxmax() if not df.empty else '-'
cols=st.columns(5)
cols[0].metric("Net Revenue", f"€{total_rev:,.0f}")
cols[1].metric("Quantity Sold", f"{total_qty:,.0f}")
cols[2].metric("Transactions", f"{total_trans:,.0f}")
cols[3].metric("Avg Price", f"€{avg_price:,.2f}")
cols[4].metric("Top Drink", best_drink)

st.divider()

st.header("1. Shop Performance")
st.markdown("Shows which shops generate the most NAMO Plus revenue or quantity for the selected period.")
shop = df.groupby('location', as_index=False).agg(**{'Net Revenue':('net_sales','sum'), 'Quantity':('qty','sum')}).sort_values(metric, ascending=True)
fig=px.bar(shop, x=metric, y='location', orientation='h', text=metric, template='plotly_white')
fig.update_traces(texttemplate='€%{text:,.0f}' if metric=='Net Revenue' else '%{text:,.0f}', textposition='outside')
fig.update_layout(height=450, xaxis_title=metric, yaxis_title='Shop')
st.plotly_chart(fig, use_container_width=True)

st.header("2. Top Drinks")
st.markdown("Identifies best sellers by revenue or quantity. Use this for menu positioning and availability planning.")
drink = df.groupby(['category_clean','item'], as_index=False).agg(**{'Net Revenue':('net_sales','sum'), 'Quantity':('qty','sum')}).sort_values(metric, ascending=False).head(20).sort_values(metric)
fig=px.bar(drink, x=metric, y='item', color='category_clean', orientation='h', text=metric, template='plotly_white')
fig.update_traces(texttemplate='€%{text:,.0f}' if metric=='Net Revenue' else '%{text:,.0f}', textposition='outside')
fig.update_layout(height=650, xaxis_title=metric, yaxis_title='Drink', legend_title='Category')
st.plotly_chart(fig, use_container_width=True)

st.header("3. Drink Performance by Shop")
st.markdown("Heatmap showing which drinks perform best in each shop. Darker cells indicate stronger sales.")
top_items = df.groupby('item')['net_sales'].sum().nlargest(20).index
heat = df[df['item'].isin(top_items)].pivot_table(index='location', columns='item', values='net_sales' if metric=='Net Revenue' else 'qty', aggfunc='sum', fill_value=0)
fig=px.imshow(heat, aspect='auto', color_continuous_scale='YlGnBu', labels={'color':metric})
fig.update_layout(height=550)
st.plotly_chart(fig, use_container_width=True)

st.header("4. Monthly Trend")
st.markdown("Shows seasonality and whether NAMO Plus sales are growing or declining over time.")
df['month'] = pd.to_datetime(df['date']).dt.to_period('M').astype(str)
monthly=df.groupby('month', as_index=False).agg(**{'Net Revenue':('net_sales','sum'), 'Quantity':('qty','sum')})
fig=px.line(monthly, x='month', y=metric, markers=True, template='plotly_white')
fig.update_layout(height=450, xaxis_title='Month', yaxis_title=metric)
st.plotly_chart(fig, use_container_width=True)

st.header("5. Menu Filtering Recommendations")
st.markdown("Simple framework: Keep high revenue/high volume drinks, promote high revenue/low volume drinks, review low performers.")
menu=df.groupby(['category_clean','item'], as_index=False).agg(**{'Net Revenue':('net_sales','sum'), 'Quantity':('qty','sum')})
rev_med=menu['Net Revenue'].median(); qty_med=menu['Quantity'].median()
def classify(r):
    if r['Net Revenue']>=rev_med and r['Quantity']>=qty_med: return 'Keep'
    if r['Net Revenue']>=rev_med and r['Quantity']<qty_med: return 'Promote'
    if r['Net Revenue']<rev_med and r['Quantity']>=qty_med: return 'Review Margin'
    return 'Review / Remove'
menu['Recommendation']=menu.apply(classify, axis=1)
menu=menu.sort_values(['Recommendation','Net Revenue'], ascending=[True,False])
st.dataframe(menu, use_container_width=True, hide_index=True)

csv_data = menu.to_csv(index=False).encode('utf-8')
st.download_button("Download menu recommendations CSV", csv_data, "namo_plus_menu_recommendations.csv", "text/csv")
