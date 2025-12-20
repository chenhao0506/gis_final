import pandas as pd
import geopandas as gpd
import leafmap
import solara
from ipyleaflet import GeoJSON

# --- 1. Data Sources ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# --- 2. State Management ---
extra_cars = solara.reactive({})
selected_town = solara.reactive(None)

@solara.component
def Page():
    # --- 3. Data Processing ---
    def load_and_process(cars_dict):
        try:
            # A. Load Geography - Force EPSG:4326 for Leaflet compatibility
            gdf = gpd.read_file(TOWNSHIPS_URL)
            if gdf.crs is None or gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs(epsg=4326)
            
            # B. Load Doctor Data
            df_doc = pd.read_csv(CSV_DOCTOR_URL)
            df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']].copy()
            df_doc.columns = ['town_name', 'base_doctor_rate']

            # C. Load Population Data (Big5 encoding for Taiwan CSVs)
            df_pop = pd.read_csv(CSV_POPULATION_URL, encoding="big5")
            df_pop.columns = [str(c).strip() for c in df_pop.columns]
            
            # Clean numeric values
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)
            cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
            df_pop['pop_65plus'] = df_pop[cols_65].sum(axis=1)
            
            # Grouping by the first column (Town Name)
            town_col = df_pop.columns[0]
            pop_stats = df_pop.groupby(town_col).agg({'pop_total':'sum', 'pop_65plus':'sum'}).reset_index()
            pop_stats.columns = ['area_name', 'pop_total', 'pop_65plus']

            # D. Merge and Simulation logic
            df_merged = pd.merge(pop_stats, df_doc, left_on='area_name', right_on='town_name', how='inner')
            
            def calculate_new_rate(row):
                added = cars_dict.get(row['area_name'], 0)
                # 1 car = 1 doctor; Density per 10,000 people
                bonus = (added / (row['pop_total'] / 10000)) if row['pop_total'] > 0 else 0
                return row['base_doctor_rate'] + bonus

            df_merged['current_doctor_rate'] = df_merged.apply(calculate_new_rate, axis=1)
            
            # E. Bivariate Ranking
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            df_merged['v1_bin'] = get_bins(df_merged['pop_65plus'])
            df_merged['v2_bin'] = get_bins(df_merged['current_doctor_rate'])
            df_merged['bi_class'] = df_merged['v1_bin'].astype(str) + df_merged['v2_bin'].astype(str)
            
            # F. Color Mapping
            color_matrix = {
                '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
                '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
                '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
            }
            df_merged['color'] = df_merged['bi_class'].map(color_matrix)

            # Join back to GeoDataFrame
            final_gdf = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')
            
            if final_gdf.empty:
                return "Error: No matching towns found between GeoJSON and CSV."
            return final_gdf
            
        except Exception as e:
            return f"System Error: {str(e)}"

    # Memoize processing
    result = solara.use_memo(lambda: load_and_process(extra_cars.value), dependencies=[extra_cars.value])

    # --- 4. UI Layout ---
    with solara.Columns([3, 1]):
        with solara.Column():
            solara.Markdown("### 彰化縣醫療資源分佈模擬")
            
            if isinstance(result, str):
                solara.Error(result)
            else:
                # Initialize Map
                m = leafmap.Map(center=[23.98, 120.53], zoom=10)
                
                # Convert to GeoJSON for ipyleaflet
                geo_data = result.__geo_interface__
                
                # Define Click Event
                def on_click(feature, **kwargs):
                    if feature:
                        selected_town.value = feature['properties']['townname']

                # Create GeoJSON Layer
                geojson_layer = GeoJSON(
                    data=geo_data,
                    name="Townships",
                    style={
                        "fillOpacity": 0.7,
                        "weight": 1.5,
                        "color": "white"
                    },
                    hover_style={"fillOpacity": 0.9, "weight": 2, "color": "black"},
                    style_callback=lambda feat: {"fillColor": feat["properties"]["color"]}
                )
                
                geojson_layer.on_click(on_click)
                m.add_layer(geojson_layer)
                
                # Render Map
                m.element(height="650px")

        # --- 5. Sidebar Controls ---
        with solara.Column(style={"padding": "15px", "background": "#fdfdfd", "border-left": "1px solid #ddd"}):
            solara.Markdown("## 資源模擬工具")
            
            if selected_town.value:
                town = selected_town.value
                count = extra_cars.value.get(town, 0)
                
                solara.Info(f"選定區域：{town}")
                solara.Markdown(f"#### 額外配置醫療車：**{count}** 台")
                
                def update(delta):
                    new_map = extra_cars.value.copy()
                    new_map[town] = max(0, count + delta)
                    extra_cars.value = new_map

                with solara.Row():
                    solara.Button("＋ 增加一輛", on_click=lambda: update(1), color="success")
                    solara.Button("－ 減少一輛", on_click=lambda: update(-1), color="error")
                
                solara.Button("清除選擇", on_click=lambda: selected_town.set(None), text=True)
            else:
                solara.Warning("請點擊地圖上的鄉鎮開始配置資源")

            solara.Markdown("---")
            solara.Markdown("#### 圖例 (Bivariate Legend)")
            solara.Markdown("- 🟥 **紅色系 (31)**: 高齡人口多 / 醫療資源少")
            solara.Markdown("- 🟪 **紫色系 (33)**: 高齡人口多 / 醫療資源多")
            solara.Markdown("- ⬜ **灰色系 (11)**: 人口與資源皆低")

Page()