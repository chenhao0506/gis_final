import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import os
import requests
import io
import base64
from dash import Dash, html, dcc
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties

# --- 1. Data Sources & Font Setup ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/iansui/Iansui-Regular.ttf"
FONT_PATH = "Iansui-Regular.ttf"

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get(FONT_URL, timeout=10)
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
        except: pass

download_font()
font_prop = FontProperties(fname=FONT_PATH) if os.path.exists(FONT_PATH) else FontProperties(family="sans-serif")

# --- 2. Data Processing Function ---
def get_processed_data():
    gdf = gpd.read_file(TOWNSHIPS_URL)
    
    # Process Doctor Data
    df_doc = pd.read_csv(CSV_DOCTOR_URL)
    df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']]
    df_doc.columns = ['town_name', 'doctor_per_10k']
    df_doc['doctor_per_10k'] = pd.to_numeric(df_doc['doctor_per_10k'], errors='coerce').fillna(0)

    # Process Population Data
    pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding="big5", header=None)
    df_pop = pop_raw[0].str.split(',', expand=True)
    df_pop.columns = [str(c).strip() for c in df_pop.iloc[0]]
    df_pop = df_pop[df_pop.iloc[:, 0] != '區域別']
    df_pop.rename(columns={df_pop.columns[0]: 'area_name'}, inplace=True)

    age_cols = [c for c in df_pop.columns if '歲' in str(c)]
    for col in age_cols:
        df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101)) or '100' in c]
    df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
    df_pop_grouped = df_pop.groupby('area_name')['pop_65plus'].sum().reset_index()

    # Merge & Binning
    df_merged = pd.merge(df_pop_grouped, df_doc, left_on='area_name', right_on='town_name', how='inner')
    gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')

    gdf_final['v1_bin'] = pd.qcut(gdf_final['pop_65plus'].rank(method='first'), 3, labels=['1', '2', '3'])
    gdf_final['v2_bin'] = pd.qcut(gdf_final['doctor_per_10k'].rank(method='first'), 3, labels=['1', '2', '3'])
    gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)
    
    return gdf_final

# --- 3. Plotting Function (Matplotlib to Base64) ---
def generate_bivariate_map():
    gdf_final = get_processed_data()
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    fig = plt.figure(figsize=(10, 11))
    ax = fig.add_axes([0.05, 0.25, 0.9, 0.7])
    gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.5)
    ax.set_axis_off()

    # Legend
    ax_leg = fig.add_axes([0.15, 0.05, 0.15, 0.15])
    for i in range(1, 4):
        for j in range(1, 4):
            ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))
    
    ax_leg.set_xlim(1, 4); ax_leg.set_ylim(1, 4)
    ax_leg.set_xticks([1.5, 2.5, 3.5]); ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
    ax_leg.set_yticks([1.5, 2.5, 3.5]); ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
    ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop)
    ax_leg.set_ylabel('每萬人醫師數 →', fontproperties=font_prop)

    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)
    data = base64.b64encode(buf.getbuffer()).decode("utf8")
    return f"data:image/png;base64,{data}"

# --- 4. Dash App Layout ---
app = Dash(__name__)

app.layout = html.Div(style={'textAlign': 'center', 'fontFamily': 'sans-serif'}, children=[
    html.H1("彰化縣：高齡人口與醫師資源雙變量地圖分析"),
    html.Img(src=generate_bivariate_map(), style={'width': '80%', 'maxWidth': '800px'})
])

if __name__ == '__main__':
    app.run(debug=True)