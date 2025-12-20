import pandas as pd
import geopandas as gpd
import leafmap
import solara
from ipyleaflet import GeoJSON

# --- 1. 資料來源 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# --- 2. 狀態管理 ---
extra_cars = solara.reactive({})
selected_town = solara.reactive(None)

@solara.component
def Page():
    # --- 3. 資料處理核心 ---
    def load_and_process(cars_dict):
        try:
            # A. 讀取地理資料並強制轉換座標系
            gdf = gpd.read_file(TOWNSHIPS_URL)
            gdf = gdf.to_crs(epsg=4326) # 強制使用 WGS84
            
            # B. 讀取醫師資料
            df_doc = pd.read_csv(CSV_DOCTOR_URL)
            df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']].copy()
            df_doc.columns = ['town_name', 'base_doctor_rate']

            # C. 讀取人口資料 (處理 Big5 編碼)
            df_pop = pd.read_csv(CSV_POPULATION_URL, encoding="big5")
            df_pop.columns = [str(c).strip() for c in df_pop.columns]
            
            # 清理人口數值
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)
            cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
            df_pop['pop_65plus'] = df_pop[cols_65].sum(axis=1)
            
            # 以第一欄作為行政區名稱
            town_col = df_pop.columns[0]
            pop_stats = df_pop.groupby(town_col).agg({'pop_total':'sum', 'pop_65plus':'sum'}).reset_index()
            pop_stats.columns = ['area_name', 'pop_total', 'pop_65plus']

            # D. 合併資料
            df_merged = pd.merge(pop_stats, df_doc, left_on='area_name', right_on='town_name', how='inner')
            
            # 計算模擬後的醫師密度
            def calculate_new_rate(row):
                added = cars_dict.get(row['area_name'], 0)
                bonus = (added / (row['pop_total'] / 10000)) if row['pop_total'] > 0 else 0
                return row['base_doctor_rate'] + bonus

            df_merged['current_doctor_rate'] = df_merged.apply(calculate_new_rate, axis=1)
            
            # E. 雙變量分級 (使用 rank 避免重複值錯誤)
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            df_merged['v1_bin'] = get_bins(df_merged['pop_65plus'])
            df_merged['v2_bin'] = get_bins(df_merged['current_doctor_rate'])
            df_merged['bi_class'] = df_merged['v1_bin'].astype(str) + df_merged['v2_bin'].astype(str)
            
            # F. 顏色映射表
            color_matrix = {
                '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
                '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
                '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
            }
            df_merged['color'] = df_merged['bi_class'].map(color_matrix)

            # 與地理資料合併
            final_gdf = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')
            
            return final_gdf
            
        except Exception as e:
            return f"系統錯誤: {str(e)}"

    # 監聽模擬變化
    result = solara.use_memo(lambda: load_and_process(extra_cars.value), dependencies=[extra_cars.value])

    # --- 4. 介面佈局 ---
    with solara.Columns([3, 1]):
        with solara.Column():
            solara.Markdown("### 彰化縣醫療資源分佈模擬 (無底圖模式)")
            
            if isinstance(result, str):
                solara.Error(result)
            elif result.empty:
                solara.Error("資料合併後為空，請檢查 GeoJSON 的 'townname' 與 CSV 的區域名稱是否一致。")
            else:
                # 初始化地圖，設置 basemap=None 移除 OSM 底圖
                m = leafmap.Map(center=[23.98, 120.53], zoom=10, basemap=None)
                
                # 將 GeoDataFrame 轉為 GeoJSON 格式
                geo_data = result.__geo_interface__
                
                # 點擊事件處理
                def on_click(feature, **kwargs):
                    if feature:
                        selected_town.value = feature['properties']['townname']

                # 建立圖層
                geojson_layer = GeoJSON(
                    data=geo_data,
                    style={
                        "fillOpacity": 0.8,
                        "weight": 1,
                        "color": "#333333" # 行政區邊界線顏色
                    },
                    hover_style={"fillOpacity": 1, "weight": 2, "color": "black"},
                    style_callback=lambda feat: {"fillColor": feat["properties"]["color"]}
                )
                
                geojson_layer.on_click(on_click)
                m.add_layer(geojson_layer)
                
                m.element(height="650px")

        # --- 5. 側邊控制面板 ---
        with solara.Column(style={"padding": "15px", "background": "#fdfdfd"}):
            solara.Markdown("## 資源模擬工具")
            
            # 除錯資訊：顯示目前成功加載的鄉鎮數
            if not isinstance(result, str):
                solara.Text(f"成功加載鄉鎮數: {len(result)}")
            
            if selected_town.value:
                town = selected_town.value
                count = extra_cars.value.get(town, 0)
                
                solara.Info(f"選定區域：{town}")
                
                def update(delta):
                    new_map = extra_cars.value.copy()
                    new_map[town] = max(0, count + delta)
                    extra_cars.value = new_map

                with solara.Row():
                    solara.Button("＋ 增加", on_click=lambda: update(1), color="success")
                    solara.Button("－ 減少", on_click=lambda: update(-1), color="error")
                
                solara.Button("取消選取", on_click=lambda: selected_town.set(None), text=True)
            else:
                solara.Warning("請點擊地圖區塊開始配置")

            solara.Markdown("---")
            solara.Markdown("#### 圖例 (Bivariate Legend)")
            solara.Markdown("- 🟥 **紅色系 (31)**: 高齡人口多 / 醫療資源少")
            solara.Markdown("- 🟪 **紫色系 (33)**: 高齡人口多 / 醫療資源多")
            solara.Markdown("- ⬜ **灰色系 (11)**: 兩者皆低")

Page()