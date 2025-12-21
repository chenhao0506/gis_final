import pandas as pd
import geopandas as gpd
import plotly.express as px
import solara
import json

# --- 1. 資料來源配置 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# 狀態管理
extra_cars = solara.reactive({})
selected_town = solara.reactive(None)

# 顏色矩陣
COLOR_MATRIX = {
    '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
    '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
    '13': '#64acbe', '23': '#627f8c', '33': '#574249'
}

@solara.component
def Page():
    def load_and_process(cars_dict):
        try:
            # A. 讀取地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL).to_crs(epsg=4326)
            
            # B. 讀取醫師資料
            df_doc = pd.read_csv(CSV_DOCTOR_URL)
            df_doc = df_doc[df_doc['區域'] != '總計'].copy()
            df_doc = df_doc[['區域', '總計']]
            df_doc.columns = ['town_name', 'base_doctor_rate']

            # C. 讀取人口資料並處理碎片化
            df_pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding="big5")
            df_pop = df_pop_raw.copy() # 解決 PerformanceWarning 的關鍵
            df_pop.columns = [str(c).strip() for c in df_pop.columns]
            
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            # 計算總人口
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)
            cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
            df_pop['pop_65plus'] = df_pop[cols_65].sum(axis=1)
            
            # 聚合資料
            town_col = df_pop.columns[0]
            pop_stats = df_pop.groupby(town_col).agg({'pop_total':'sum', 'pop_65plus':'sum'}).reset_index()
            pop_stats.columns = ['area_name', 'pop_total', 'pop_65plus']

            # D. 合併與模擬
            df_merged = pd.merge(pop_stats, df_doc, left_on='area_name', right_on='town_name', how='inner')
            
            def calculate_new_rate(row):
                added = cars_dict.get(row['area_name'], 0)
                bonus = (added / (row['pop_total'] / 10000)) if row['pop_total'] > 0 else 0
                return row['base_doctor_rate'] + bonus

            df_merged['current_doctor_rate'] = df_merged.apply(calculate_new_rate, axis=1)
            
            # E. 雙變量分級
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            df_merged['v1_bin'] = get_bins(df_merged['pop_65plus'])
            df_merged['v2_bin'] = get_bins(df_merged['current_doctor_rate'])
            df_merged['bi_class'] = df_merged['v1_bin'].astype(str) + df_merged['v2_bin'].astype(str)
            
            return gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')
            
        except Exception as e:
            return str(e)

    result_gdf = solara.use_memo(lambda: load_and_process(extra_cars.value), dependencies=[extra_cars.value])

    with solara.Columns([3, 1]):
        with solara.Column():
            solara.Markdown("### 彰化縣醫療資源動態模擬")
            
            if isinstance(result_gdf, str):
                solara.Error(f"資料處理錯誤: {result_gdf}")
            elif not result_gdf.empty:
                # 使用更新後的 choropleth_map (不帶 box 尾碼)
                fig = px.choropleth_map(
                    result_gdf,
                    geojson=json.loads(result_gdf.to_json()),
                    locations=result_gdf.index,
                    color="bi_class",
                    color_discrete_map=COLOR_MATRIX,
                    map_style="carto-positron",
                    center={"lat": 23.98, "lon": 120.53},
                    zoom=9,
                    hover_name="townname"
                )
                
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, showlegend=False)

                # 關鍵：處理點擊事件
                def handle_click(data):
                    if data and "points" in data:
                        idx = data["points"][0]["location"]
                        selected_town.value = result_gdf.iloc[idx]["townname"]

                # 渲染圖表
                solara.FigurePlotly(fig, on_click=handle_click)

        with solara.Column(style={"padding": "20px"}):
            solara.Markdown("## 模擬配置面板")
            if selected_town.value:
                town = selected_town.value
                current = extra_cars.value.get(town, 0)
                solara.Info(f"選取區域: {town}")
                
                def update(delta):
                    new = extra_cars.value.copy()
                    new[town] = max(0, current + delta)
                    extra_cars.value = new

                solara.Button("增加醫療車", on_click=lambda: update(1), color="success")
                solara.Button("減少醫療車", on_click=lambda: update(-1), color="error")
                solara.Text(f"已投入：{current} 台")
            else:
                solara.Warning("請點擊地圖區域")

Page()