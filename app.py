import pandas as pd
import geopandas as gpd
import plotly.express as px
import solara
import json

# -----------------------------
# 資料來源
# -----------------------------
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# -----------------------------
# 狀態
# -----------------------------
selected_town = solara.reactive(None)
extra_doctors = solara.reactive({})

# 固定的雙變量配色
COLOR_MATRIX = {
    '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a',
    '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356',
    '13': '#64acbe', '23': '#627f8c', '33': '#574249'
}

# -----------------------------
# 一次性資料處理（原始現況）
# -----------------------------
@solara.memoize
def load_base_data():
    gdf = gpd.read_file(TOWNSHIPS_URL).to_crs(epsg=4326)

    df_doc = pd.read_csv(CSV_DOCTOR_URL)
    df_doc = df_doc[df_doc['區域'] != '總計']
    df_doc = df_doc[['區域', '總計']]
    df_doc.columns = ['area_name', 'doctor_per_10k']
    df_doc['doctor_per_10k'] = pd.to_numeric(df_doc['doctor_per_10k'], errors='coerce').fillna(0)

    pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding="big5")
    pop_raw.columns = [str(c).strip() for c in pop_raw.columns]
    town_col = pop_raw.columns[0]

    age_cols = [c for c in pop_raw.columns if '歲' in c]
    for c in age_cols:
        pop_raw[c] = (
            pop_raw[c].astype(str)
            .str.replace(',', '')
            .replace(['nan', 'None', ''], '0')
            .astype(float)
        )

    cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
    pop_raw['pop_65plus'] = pop_raw[cols_65].sum(axis=1)

    df_pop = pop_raw.groupby(town_col).agg({
        'pop_65plus': 'sum'
    }).reset_index()
    df_pop.columns = ['area_name', 'pop_65plus']

    df = pd.merge(df_pop, df_doc, on='area_name', how='left').fillna(0)

    # 固定分級切點（只算一次）
    df['v1_bin'] = pd.qcut(df['pop_65plus'].rank(method='first'), 3, labels=['1', '2', '3'])
    df['v2_bin_base'] = pd.qcut(df['doctor_per_10k'].rank(method='first'), 3, labels=['1', '2', '3'])

    gdf = gdf.merge(df, left_on='townname', right_on='area_name', how='inner')
    return gdf


# -----------------------------
# 依據互動更新單一鄉鎮
# -----------------------------
def apply_policy(gdf):
    gdf = gdf.copy()
    gdf['doctor_sim'] = gdf['doctor_per_10k']

    for town, added in extra_doctors.value.items():
        idx = gdf['townname'] == town
        if idx.any():
            pop = gdf.loc[idx, 'pop_65plus'].values[0]
            if pop > 0:
                gdf.loc[idx, 'doctor_sim'] += added / (pop / 10000)

    # 使用「原始切點」重新判斷該鄉鎮落在哪一級
    bins = pd.qcut(
        gdf['doctor_per_10k'].rank(method='first'),
        3,
        retbins=True,
        labels=['1', '2', '3']
    )[1]

    def classify(val):
        if val <= bins[1]:
            return '1'
        elif val <= bins[2]:
            return '2'
        else:
            return '3'

    gdf['v2_bin'] = gdf.apply(
        lambda r: classify(r['doctor_sim'])
        if r['townname'] in extra_doctors.value
        else r['v2_bin_base'],
        axis=1
    )

    gdf['bi_class'] = gdf['v1_bin'].astype(str) + gdf['v2_bin'].astype(str)
    gdf['color'] = gdf['bi_class'].map(COLOR_MATRIX)
    return gdf


# -----------------------------
# 主頁面
# -----------------------------
@solara.component
def Page():
    base_gdf = load_base_data()
    gdf = apply_policy(base_gdf)

    geojson = json.loads(gdf.to_json())

    fig = px.choropleth_map(
        gdf,
        geojson=geojson,
        locations="townname",
        featureidkey="properties.townname",
        color="bi_class",
        color_discrete_map=COLOR_MATRIX,
        map_style="carto-positron",
        center={"lat": 23.98, "lon": 120.53},
        zoom=9.3,
        opacity=0.85,
        hover_name="townname",
        custom_data=["townname"]
    )

    fig.update_layout(
        margin=dict(r=0, t=0, l=0, b=0),
        showlegend=False,
        uirevision="fixed"
    )

    def handle_click(data):
        if not data:
            return
        pts = data.get("points", [])
        if not pts:
            return
        town = pts[0].get("customdata", [None])[0]
        if town:
            selected_town.value = town

    with solara.Columns([3, 1]):
        with solara.Column():
            solara.FigurePlotly(fig, on_click=handle_click, on_relayout=None)

        with solara.Column(style={"padding": "20px"}):
            if selected_town.value:
                town = selected_town.value
                current = extra_doctors.value.get(town, 0)

                solara.Markdown(f"### {town}")

                def update(delta):
                    d = extra_doctors.value.copy()
                    d[town] = max(0, current + delta)
                    extra_doctors.value = d

                solara.Button("增加 1 名醫師", on_click=lambda: update(1))
                solara.Button("減少 1 名醫師", on_click=lambda: update(-1))
                solara.Markdown(f"目前投入：**{current} 名**")
            else:
                solara.Markdown("請點選地圖中的鄉鎮")

Page()
