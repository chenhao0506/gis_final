import pandas as pd
import geopandas as gpd
import plotly.express as px
import solara
import json

# --- 1. 資料來源配置 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# --- 2. 狀態管理 ---
extra_cars = solara.reactive({})
selected_town = solara.reactive(None)

# --- 3. 雙變量顏色矩陣定義 ---
COLOR_MATRIX = {
    '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a',  # 第一列 (低醫師密度)
    '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356',  # 第二列
    '13': '#64acbe', '23': '#627f8c', '33': '#574249'   # 第三列 (高醫師密度)
}

@solara.component
def BivariateLegend():
    """建立自定義 3x3 圖例矩陣"""
    return solara.HTML(tag="div", unsafe_innerHTML=f"""
        <div style="display: flex; flex-direction: column; align-items: center; font-size: 12px; margin-top: 10px;">
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="writing-mode: vertical-rl; transform: rotate(180deg); margin-right: 5px;">醫師密度 →</div>
                <div style="display: grid; grid-template-columns: repeat(3, 30px); grid-template-rows: repeat(3, 30px); border: 1px solid #ccc;">
                    <div style="background-color: {COLOR_MATRIX['13']};"></div><div style="background-color: {COLOR_MATRIX['23']};"></div><div style="background-color: {COLOR_MATRIX['33']};"></div>
                    <div style="background-color: {COLOR_MATRIX['12']};"></div><div style="background-color: {COLOR_MATRIX['22']};"></div><div style="background-color: {COLOR_MATRIX['32']};"></div>
                    <div style="background-color: {COLOR_MATRIX['11']};"></div><div style="background-color: {COLOR_MATRIX['21']};"></div><div style="background-color: {COLOR_MATRIX['31']};"></div>
                </div>
            </div>
            <div>高齡人口 →</div>
        </div>
    """)

@solara.component
def Page():
    # --- 4. 資料處理核心 (使用 memo 優化效能) ---
    def load_and_process(cars_dict):
        try:
            # A. 讀取與轉換地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL)
            gdf = gdf.to_crs(epsg=4326)
            
            # B. 讀取醫師資料
            df_doc = pd.read_csv(CSV_DOCTOR_URL)
            df_doc = df_doc[df_doc['區域'] != '總計'].copy()
            df_doc = df_doc[['區域', '總計']]
            df_doc.columns = ['town_name', 'base_doctor_rate']

            # C. 讀取人口資料 (處理 Big5 與欄位清理)
            df_pop = pd.read_csv(CSV_POPULATION_URL, encoding="big5")
            df_pop.columns = [str(c).strip() for c in df_pop.columns]
            
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)
            cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
            df_pop['pop_65plus'] = df_pop[cols_65].sum(axis=1)
            
            town_col = df_pop.columns[0]
            pop_stats = df_pop.groupby(town_col).agg({'pop_total':'sum', 'pop_65plus':'sum'}).reset_index()
            pop_stats.columns = ['area_name', 'pop_total', 'pop_65plus']

            # D. 資料合併與模擬計算
            df_merged = pd.merge(pop_stats, df_doc, left_on='area_name', right_on='town_name', how='inner')
            
            def calculate_new_rate(row):
                added = cars_dict.get(row['area_name'], 0)
                bonus = (added / (row['pop_total'] / 10000)) if row['pop_total'] > 0 else 0
                return row['base_doctor_rate'] + bonus

            df_merged['current_doctor_rate'] = df_merged.apply(calculate_new_rate, axis=1)
            
            # E. 雙變量分級計算 (1-3 級)
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            df_merged['v1_bin'] = get_bins(df_merged['pop_65plus'])
            df_merged['v2_bin'] = get_bins(df_merged['current_doctor_rate'])
            df_merged['bi_class'] = df_merged['v1_bin'].astype(str) + df_merged['v2_bin'].astype(str)
            
            # F. 合併回 GeoDataFrame
            final_gdf = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')
            return final_gdf
            
        except Exception as e:
            return f"Error: {str(e)}"

    result_gdf = solara.use_memo(lambda: load_and_process(extra_cars.value), dependencies=[extra_cars.value])

    # --- 5. 介面佈局 ---
    with solara.Columns([3, 1]):
        with solara.Column():
            solara.Markdown("### 彰化縣醫療資源動態模擬 (Plotly 引擎)")
            
            if isinstance(result_gdf, str):
                solara.Error(result_gdf)
            elif result_gdf.empty:
                solara.Warning("查無匹配資料，請檢查區域名稱。")
            else:
                # 準備 Plotly 地圖所需資料
                geojson_data = json.loads(result_gdf.to_json())
                
                fig = px.choropleth_mapbox(
                    result_gdf,
                    geojson=geojson_data,
                    locations=result_gdf.index,
                    color="bi_class",
                    color_discrete_map=COLOR_MATRIX,
                    mapbox_style="carto-positron",
                    center={"lat": 23.98, "lon": 120.53},
                    zoom=9.5,
                    opacity=0.8,
                    hover_name="townname",
                    hover_data={
                        "pop_65plus": True, 
                        "current_doctor_rate": ":.2f",
                        "bi_class": False
                    },
                    labels={
                        "pop_65plus": "高齡人口 (人)",
                        "current_doctor_rate": "醫師密度 (每萬人)"
                    }
                )
                
                fig.update_layout(
                    margin={"r":0,"t":0,"l":0,"b":0},
                    showlegend=False,
                    clickmode='event+select'
                )

                # 處理地圖點擊事件 (Plotly 互動)
                def handle_click(data):
                    if data and "points" in data:
                        idx = data["points"][0]["location"]
                        selected_town.value = result_gdf.iloc[idx]["townname"]

                solara.FigurePlotly(fig, on_selection=handle_click)

        # --- 6. 側邊面板 ---
        with solara.Column(style={"padding": "20px", "background": "#f8f9fa"}):
            solara.Markdown("## 模擬配置面板")
            
            if selected_town.value:
                town = selected_town.value
                current = extra_cars.value.get(town, 0)
                
                solara.Info(f"當前選取：{town}")
                solara.Markdown(f"**額外投入醫療車：{current} 台**")
                
                def change(delta):
                    new = extra_cars.value.copy()
                    new[town] = max(0, current + delta)
                    extra_cars.value = new

                with solara.Row():
                    solara.Button("＋ 增加", on_click=lambda: change(1), color="success")
                    solara.Button("－ 減少", on_click=lambda: change(-1), color="error")
                
                solara.Button("重置選擇", on_click=lambda: selected_town.set(None), text=True)
            else:
                solara.Warning("請點擊地圖區塊開始模擬")

            solara.Markdown("---")
            solara.Markdown("#### 雙變量圖例指標")
            BivariateLegend()
            solara.Markdown("""
            - **深紅色 (31)**: 高齡人口多但醫療資源最匱乏。
            - **深紫色 (33)**: 高齡人口多且醫療資源相對充足。
            - **淺灰色 (11)**: 兩者皆處於低位。
            """)

Page()