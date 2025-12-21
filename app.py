import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import os
import requests
import io
import base64
from dash import Dash, html, dcc, Input, Output, State
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties

# =============================
# 1. 基本設定
# =============================
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

FONT_URL = "https://github.com/google/fonts/raw/main/ofl/iansui/Iansui-Regular.ttf"
FONT_PATH = "Iansui-Regular.ttf"

MED_THRESHOLDS = {
    "low": 6,
    "mid": 10
}

NEAR_THRESHOLD = 1.5   # 距離門檻 <= 1.5 才提前變色


# =============================
# 2. 字型
# =============================
def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get(FONT_URL, timeout=10)
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
        except:
            pass

download_font()
font_prop = FontProperties(fname=FONT_PATH) if os.path.exists(FONT_PATH) else FontProperties()


# =============================
# 3. 載入資料（只一次）
# =============================
def load_base_data():
    gdf = gpd.read_file(TOWNSHIPS_URL)

    df_doc = pd.read_csv(CSV_DOCTOR_URL)
    df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']]
    df_doc.columns = ['town_name', 'doctor_per_10k']
    df_doc['doctor_per_10k'] = pd.to_numeric(df_doc['doctor_per_10k'], errors='coerce').fillna(0)

    pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding="big5", header=None)
    df_pop = pop_raw[0].str.split(',', expand=True)
    df_pop.columns = df_pop.iloc[0]
    df_pop = df_pop[df_pop.iloc[:, 0] != '區域別']
    df_pop.rename(columns={df_pop.columns[0]: 'area_name'}, inplace=True)

    age_cols = [c for c in df_pop.columns if '歲' in str(c)]
    for c in age_cols:
        df_pop[c] = pd.to_numeric(df_pop[c].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
    df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)

    df_pop = df_pop.groupby('area_name')['pop_65plus'].sum().reset_index()

    df = pd.merge(df_pop, df_doc, left_on='area_name', right_on='town_name', how='inner')

    # 高齡人口結構分級（固定）
    df['v1_bin'] = pd.qcut(df['pop_65plus'].rank(method='first'), 3, labels=['1', '2', '3'])

    return gdf, df


GDF_BASE, DF_BASE = load_base_data()


# =============================
# 4. gap 計算（唯一真實版本）
# =============================
def calc_gap(val):
    if val < MED_THRESHOLDS['low']:
        return MED_THRESHOLDS['low'] - val, 'low→mid'
    elif val < MED_THRESHOLDS['mid']:
        return MED_THRESHOLDS['mid'] - val, 'mid→high'
    else:
        return 0, 'top'


# =============================
# 5. 地圖產生
# =============================
def generate_bivariate_map(vehicles_dict):
    df = DF_BASE.copy()
    df['doctor_sim'] = df['doctor_per_10k']

    for town, count in vehicles_dict.items():
        idx = df['area_name'] == town
        if idx.any() and count > 0:
            pop = df.loc[idx, 'pop_65plus'].values[0]
            if pop > 0:
                df.loc[idx, 'doctor_sim'] += count / (pop / 10000)

    # 醫療資源結構分級（相對）
    df['v2_bin'] = pd.qcut(
        df['doctor_sim'].rank(method='first'),
        3,
        labels=['1', '2', '3']
    )

    df['bi_class'] = df['v1_bin'].astype(str) + df['v2_bin'].astype(str)

    # gap（同一套邏輯）
    df[['gap_to_next', 'gap_stage']] = df['doctor_sim'].apply(
        lambda x: pd.Series(calc_gap(x))
    )

    # 視覺提前升級
    def promote(row):
        if row['gap_to_next'] <= NEAR_THRESHOLD:
            new_v2 = min(int(row['v2_bin']) + 1, 3)
            return row['v1_bin'] + str(new_v2)
        return row['bi_class']

    df['bi_class_vis'] = df.apply(promote, axis=1)

    gdf_final = GDF_BASE.merge(df, left_on='townname', right_on='area_name')

    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a',
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356',
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'
    }

    gdf_final['color'] = gdf_final['bi_class_vis'].map(color_matrix)

    fig = plt.figure(figsize=(10, 11))
    ax = fig.add_axes([0.05, 0.25, 0.9, 0.7])
    gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.5)
    ax.set_axis_off()

    ax_leg = fig.add_axes([0.15, 0.05, 0.2, 0.2])
    for i in range(1, 4):
        for j in range(1, 4):
            ax_leg.add_patch(Rectangle((i, j), 1, 1,
                                       facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))

    ax_leg.set_xlim(1, 4)
    ax_leg.set_ylim(1, 4)
    ax_leg.set_xticks([1.5, 2.5, 3.5])
    ax_leg.set_yticks([1.5, 2.5, 3.5])
    ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
    ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
    ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop)
    ax_leg.set_ylabel('醫療資源（含補給車） →', fontproperties=font_prop)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)

    return f"data:image/png;base64,{base64.b64encode(buf.getbuffer()).decode()}"


# =============================
# 6. Dash App
# =============================
app = Dash(__name__)

app.layout = html.Div(style={'display': 'flex', 'padding': '20px'}, children=[

    html.Div(style={'flex': 3}, children=[
        html.H2("彰化縣高齡人口與醫療補給車模擬"),
        html.Img(id='main-map', src=generate_bivariate_map({}), style={'width': '100%'})
    ]),

    html.Div(style={'flex': 1, 'padding': '20px', 'background': '#f5f5f5'}, children=[
        html.H4("政策模擬"),
        dcc.Dropdown(
            id='town-dropdown',
            options=[{'label': t, 'value': t} for t in sorted(DF_BASE['area_name'].unique())],
            placeholder="選擇鄉鎮"
        ),
        html.Br(),
        html.Div([
            html.Button("➖", id='btn-down'),
            html.Span("0", id='vehicle-count', style={'margin': '0 15px'}),
            html.Button("➕", id='btn-up'),
        ]),
        html.Hr(),
        html.Div(id='status-text'),
        dcc.Store(id='deployment-store', data={})
    ])
])


# =============================
# 7. Callback（語意一致版）
# =============================
@app.callback(
    [Output('vehicle-count', 'children'),
     Output('deployment-store', 'data'),
     Output('status-text', 'children')],
    [Input('btn-up', 'n_clicks'),
     Input('btn-down', 'n_clicks'),
     Input('town-dropdown', 'value')],
    State('deployment-store', 'data')
)
def update_vehicles(up, down, town, store):
    if not town:
        return "0", store, "請先選擇鄉鎮"

    from dash import callback_context
    trigger = callback_context.triggered[0]['prop_id'].split('.')[0]

    val = store.get(town, 0)
    if trigger == 'btn-up':
        val += 1
    elif trigger == 'btn-down':
        val = max(0, val - 1)

    store[town] = val

    row = DF_BASE[DF_BASE['area_name'] == town].iloc[0]
    pop = row['pop_65plus']
    base = row['doctor_per_10k']

    sim = base + (val / (pop / 10000)) if pop > 0 else base
    gap, stage = calc_gap(sim)

    if gap > 0:
        text = f"{town} 已部署 {val} 輛補給車 ｜距離下一級尚差 {gap:.2f}"
    else:
        text = f"{town} 已達最高醫療資源等級"

    return str(val), store, text


@app.callback(
    Output('main-map', 'src'),
    Input('deployment-store', 'data')
)
def update_map(data):
    return generate_bivariate_map(data)


if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=7860, debug=False)
