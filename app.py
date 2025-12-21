import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import os
import requests
import io
import base64
from dash import Dash, html, dcc, Input, Output, State, callback
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

# --- 2. Data Loading (Memoized Logic) ---
def load_base_data():
    gdf = gpd.read_file(TOWNSHIPS_URL)
    df_doc = pd.read_csv(CSV_DOCTOR_URL)
    df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']]
    df_doc.columns = ['town_name', 'doctor_per_10k']
    df_doc['doctor_per_10k'] = pd.to_numeric(df_doc['doctor_per_10k'], errors='coerce').fillna(0)

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

    df_merged = pd.merge(df_pop_grouped, df_doc, left_on='area_name', right_on='town_name', how='inner')
    
    # Calculate BASE bins (to keep thresholds consistent)
    df_merged['v1_bin'] = pd.qcut(df_merged['pop_65plus'].rank(method='first'), 3, labels=['1', '2', '3'])
    # We store the rank thresholds for doctor density
    return gdf, df_merged

GDF_BASE, DF_BASE = load_base_data()

# --- 3. Plotting Function (Now accepts "deployed_vehicles" dict) ---
def generate_bivariate_map(vehicles_dict):
    df = DF_BASE.copy()
    
    # Apply Policy: 1 vehicle = 1 additional "medical resource unit"
    # Logic: doctor_sim = original_density + (vehicles / (pop_65plus / 10000))
    df['doctor_sim'] = df['doctor_per_10k']
    for town, count in vehicles_dict.items():
        idx = df['area_name'] == town
        if idx.any() and count > 0:
            pop = df.loc[idx, 'pop_65plus'].values[0]
            if pop > 0:
                df.loc[idx, 'doctor_sim'] += count / (pop / 10000)

    # Re-calculate bins for the Y-axis based on simulated data
    df['v2_bin'] = pd.qcut(df['doctor_sim'].rank(method='first'), 3, labels=['1', '2', '3'])
    df['bi_class'] = df['v1_bin'].astype(str) + df['v2_bin'].astype(str)
    
    gdf_final = GDF_BASE.merge(df, left_on='townname', right_on='area_name', how='inner')
    
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

    ax_leg = fig.add_axes([0.15, 0.05, 0.15, 0.15])
    for i in range(1, 4):
        for j in range(1, 4):
            ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))
    
    ax_leg.set_xlim(1, 4); ax_leg.set_ylim(1, 4)
    ax_leg.set_xticks([1.5, 2.5, 3.5]); ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
    ax_leg.set_yticks([1.5, 2.5, 3.5]); ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
    ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop)
    ax_leg.set_ylabel('醫療資源(含補給車) →', fontproperties=font_prop)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)
    data = base64.b64encode(buf.getbuffer()).decode("utf8")
    return f"data:image/png;base64,{data}"

# --- 4. Dash App Layout ---
app = Dash(__name__)

app.layout = html.Div(style={'display': 'flex', 'flexDirection': 'row', 'padding': '20px', 'fontFamily': 'sans-serif'}, children=[
    # Left Side: Map
    html.Div(style={'flex': '3', 'textAlign': 'center'}, children=[
        html.H1("彰化縣：高齡人口與補給車部署模擬"),
        html.Img(id='main-map', src=generate_bivariate_map({}), style={'width': '100%', 'maxWidth': '700px'})
    ]),
    
    # Right Side: Controls
    html.Div(style={'flex': '1', 'backgroundColor': '#f9f9f9', 'padding': '20px', 'borderRadius': '10px', 'marginLeft': '20px'}, children=[
        html.H3("政策模擬工具"),
        html.P("選擇鄉鎮："),
        dcc.Dropdown(
            id='town-dropdown',
            options=[{'label': t, 'value': t} for t in sorted(DF_BASE['area_name'].unique())],
            placeholder="請選擇鄉鎮..."
        ),
        html.Br(),
        html.P("部署醫療補給車數量："),
        html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'}, children=[
            html.Button("➖", id='btn-down', n_clicks=0),
            html.Span("0", id='vehicle-count', style={'fontSize': '20px', 'fontWeight': 'bold'}),
            html.Button("➕", id='btn-up', n_clicks=0),
        ]),
        html.Hr(),
        html.Div(id='status-text', children="請選擇鄉鎮以開始部署"),
        
        # Store for current deployment status: {TownName: Count}
        dcc.Store(id='deployment-store', data={})
    ])
])

# --- 5. Callbacks ---

# Callback to update the counter and store
@app.callback(
    [Output('vehicle-count', 'children'),
     Output('deployment-store', 'data'),
     Output('status-text', 'children')],
    [Input('btn-up', 'n_clicks'),
     Input('btn-down', 'n_clicks'),
     Input('town-dropdown', 'value')],
    [State('deployment-store', 'data')]
)
def update_vehicles(up, down, selected_town, current_store):
    if not selected_town:
        return "0", current_store, "請先選擇一個鄉鎮"
    
    # Identify which button was clicked by checking trigger
    from dash import callback_context
    triggered_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    
    current_val = current_store.get(selected_town, 0)
    
    if triggered_id == 'btn-up':
        current_val += 1
    elif triggered_id == 'btn-down':
        current_val = max(0, current_val - 1)
    
    current_store[selected_town] = current_val
    
    status = f"目前為 {selected_town} 部署 {current_val} 輛補給車"
    return str(current_val), current_store, status

# Callback to update the map whenever the store changes
@app.callback(
    Output('main-map', 'src'),
    Input('deployment-store', 'data')
)
def update_map(store_data):
    return generate_bivariate_map(store_data)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=7860)