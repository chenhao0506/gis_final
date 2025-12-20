import pandas as pd
import geopandas as gpd
import leafmap.solara_map as leafmap
import solara
import os
import requests
import json

# --- 1. 配置資料來源 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# 狀態管理：儲存每個行政區增加的醫療車數量 {town_name: count}
extra_cars = solara.reactive({})
selected_town = solara.reactive(None)

@solara.component
def Page():
    # --- 2. 資料讀取與處理核心 ---
    def load_and_process(cars_dict):
        try:
            # A. 讀取地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL)
            
            # B. 讀取醫師資料
            df_doc = pd.read_csv(CSV_DOCTOR_URL, encoding="utf-8")
            df_doc = df_doc[df_doc['區域'] != '總計']
            df_doc = df_doc[['區域', '總計']].copy()
            df_doc.columns = ['town_name', 'base_doctor_rate']

            # C. 讀取人口資料 (為了計算醫療車權重)
            pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding="big5", header=None)
            df_pop_split = pop_raw[0].str.split(',', expand=True)
            df_pop_split.columns = [str(c).strip() for c in df_pop_split.iloc[0]]
            df_pop = df_pop_split[df_pop_split.iloc[:, 0] != '區域別'].copy()
            df_pop.rename(columns={df_pop.columns[0]: 'area_name'}, inplace=True)
            
            # 計算總人口與65歲以上人口
            age_cols = [c for c in df_pop.columns if '歲' in str(c)]
            for col in age_cols:
                df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)
            cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
            df_pop['pop_65plus'] = df_pop[cols_65].sum(axis=1)
            
            pop_stats = df_pop.groupby('area_name').agg({'pop_total':'sum', 'pop_65plus':'sum'}).reset_index()

            # D. 合併並計算「動態醫師密度」
            df_merged = pd.merge(pop_stats, df_doc, left_on='area_name', right_on='town_name', how='inner')
            
            # 計算增加醫療車後的影響
            def calculate_new_rate(row):
                added = cars_dict.get(row['area_name'], 0)
                # 1台車 = 1名醫師，轉換為每萬人密度： (1 / (總人口/10000))
                bonus = (added / (row['pop_total'] / 10000)) if row['pop_total'] > 0 else 0
                return row['base_doctor_rate'] + bonus

            df_merged['current_doctor_rate'] = df_merged.apply(calculate_new_rate, axis=1)
            
            # E. 重新計算雙變量分級 (Quantiles)
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            df_merged['v1_bin'] = get_bins(df_merged['pop_65plus'])
            df_merged['v2_bin'] = get_bins(df_merged['current_doctor_rate'])
            df_merged['bi_class'] = df_merged['v1_bin'].astype(str) + df_merged['v2_bin'].astype(str)
            
            # F. 顏色映射
            color_matrix = {
                '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
                '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
                '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
            }
            df_merged['color'] = df_merged['bi_class'].map(color_matrix)

            return gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')
            
        except Exception as e:
            return str(e)

    # 當 extra_cars 改變時，自動重新計算
    gdf_final = solara.use_memo(lambda: load_and_process(extra_cars.value), dependencies=[extra_cars.value])

    # --- 3. 介面佈局 ---
    with solara.Columns([3, 1]):
        with solara.Column():
            solara.Markdown("### 彰化縣醫療資源動態模擬 (底圖: OpenStreetMap)")
            
            if isinstance(gdf_final, str):
                solara.Error(f"資料錯誤: {gdf_final}")
            else:
                # 建立 Leafmap
                m = leafmap.Map(center=[24.0, 120.5], zoom=10)
                m.add_gdf(
                    gdf_final,
                    layer_name="醫療資源分布",
                    style_callback=lambda feat: {
                        "fillColor": feat["properties"]["color"],
                        "fillOpacity": 0.7,
                        "color": "white",
                        "weight": 1
                    },
                    info_mode="on_click"
                )
                
                # 點擊事件監聽
                def handle_click(feature, **kwargs):
                    selected_town.value = feature['properties']['townname']
                
                m.on_layer_click("醫療資源分布", handle_click)
                m.element(height="600px")

        with solara.Column(style={"padding": "20px", "background": "#f9f9f9"}):
            solara.Markdown("## 資源配置面板")
            
            if selected_town.value:
                town = selected_town.value
                current_cars = extra_cars.value.get(town, 0)
                
                solara.Info(f"目前選取：{town}")
                solara.Markdown(f"**目前已投入醫療車：{current_cars} 台**")
                
                def change_cars(delta):
                    new_dict = extra_cars.value.copy()
                    new_dict[town] = max(0, current_cars + delta)
                    extra_cars.value = new_dict

                with solara.Row():
                    solara.Button("＋ 增加一輛車", on_click=lambda: change_cars(1), color="success")
                    solara.Button("－ 減少一輛車", on_click=lambda: change_cars(-1), color="error")
                
                solara.Markdown("---")
                solara.Markdown("💡 *點擊地圖不同區域進行切換*")
                solara.Markdown("💡 *每增加一台車，系統會即時重新計算全縣排名顏色*")
            else:
                solara.Warning("請點擊地圖上的鄉鎮開始模擬")

            # 圖例預覽
            solara.Markdown("#### 雙變量圖例說明")
            solara.Markdown("- **深紫色 (33)**: 高齡人口多且醫師密度高")
            solara.Markdown("- **深紅色 (31)**: 高齡人口多但醫師密度低 (急需資源)")
            solara.Markdown("- **淺灰色 (11)**: 高齡人口少且醫師密度低")

Page()