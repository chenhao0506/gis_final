import pandas as pd
import geopandas as gpd
import leafmap
import solara
from ipyleaflet import GeoJSON

# --- 1. Configuration & Data Sources ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# State management
extra_cars = solara.reactive({})
selected_town = solara.reactive(None)

@solara.component
def Page():
    # --- 2. Data Processing Core ---
    def load_and_process(cars_dict):
        try:
            # A. Load Geographic Data
            gdf = gpd.read_file(TOWNSHIPS_URL)
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs(epsg=4326)
            
            # B. Load Doctor Data
            df_doc = pd.read_csv(CSV_DOCTOR_URL)
            df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']].copy()
            df_doc.columns = ['town_name', 'base_doctor_rate']

            # C. Load Population Data (Handling potential encoding/header issues)
            # We use header=0 and let pandas parse columns directly
            df_pop = pd.read_csv(CSV_POPULATION_URL, encoding="big5")
            df_pop.columns = [str(c).strip() for c in df_pop.columns]
            
            # Clean numeric columns
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = pd.to_numeric(df_pop[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)
            cols_65 = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
            df_pop['pop_65plus'] = df_pop[cols_65].sum(axis=1)
            
            # Use first column as join key (usually '區域別')
            join_key = df_pop.columns[0]
            pop_stats = df_pop.groupby(join_key).agg({'pop_total':'sum', 'pop_65plus':'sum'}).reset_index()
            pop_stats.columns = ['area_name', 'pop_total', 'pop_65plus']

            # D. Merge and Calculate Dynamic Density
            df_merged = pd.merge(pop_stats, df_doc, left_on='area_name', right_on='town_name', how='inner')
            
            def calculate_new_rate(row):
                added = cars_dict.get(row['area_name'], 0)
                # Formula: 1 car = 1 doctor. Density = base + (added / (pop/10000))
                bonus = (added / (row['pop_total'] / 10000)) if row['pop_total'] > 0 else 0
                return row['base_doctor_rate'] + bonus

            df_merged['current_doctor_rate'] = df_merged.apply(calculate_new_rate, axis=1)
            
            # E. Bivariate Ranking
            def get_bins(series):
                # Use rank to avoid 'Bin edges must be unique' error
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            df_merged['v1_bin'] = get_bins(df_merged['pop_65plus'])
            df_merged['v2_bin'] = get_bins(df_merged['current_doctor_rate'])
            df_merged['bi_class'] = df_merged['v1_bin'].astype(str) + df_merged['v2_bin'].astype(str)
            
            # F. Color Matrix Mapping
            color_matrix = {
                '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
                '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
                '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
            }
            df_merged['color'] = df_merged['bi_class'].map(color_matrix)

            return gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')
            
        except Exception as e:
            return f"Error processing data: {str(e)}"

    # Re-calculate whenever extra_cars changes
    gdf_final = solara.use_memo(lambda: load_and_process(extra_cars.value), dependencies=[extra_cars.value])

    # --- 3. UI Layout ---
    with solara.Columns([3, 1]):
        with solara.Column():
            solara.Markdown("### 彰化縣醫療資源動態模擬")
            
            if isinstance(gdf_final, str):
                solara.Error(gdf_final)
            else:
                m = leafmap.Map(center=[24.0, 120.5], zoom=10)
                
                # Create the click handler for the layer
                def on_click(feature, **kwargs):
                    selected_town.value = feature['properties']['townname']

                # Convert GDF to GeoJSON for ipyleaflet compatibility
                geo_data = gdf_final.__geo_interface__
                
                # Add GeoJSON layer with custom styling and click event
                geojson_layer = GeoJSON(
                    data=geo_data,
                    name="醫療資源分布",
                    style={
                        "fillOpacity": 0.8,
                        "weight": 1,
                        "color": "white"
                    },
                    hover_style={"fillOpacity": 1, "weight": 2, "color": "black"},
                    # Apply the dynamic color from the dataframe
                    style_callback=lambda feat: {"fillColor": feat["properties"]["color"]}
                )
                
                geojson_layer.on_click(on_click)
                m.add_layer(geojson_layer)
                m.element(height="600px")

        with solara.Column(style={"padding": "20px", "background": "#f8f9fa", "border-radius": "10px"}):
            solara.Markdown("## 資源配置面板")
            
            if selected_town.value:
                town = selected_town.value
                current_cars = extra_cars.value.get(town, 0)
                
                solara.Info(f"選取區域：{town}")
                solara.Markdown(f"**目前配置醫療車：{current_cars} 台**")
                
                def update_count(delta):
                    new_state = extra_cars.value.copy()
                    new_state[town] = max(0, current_cars + delta)
                    extra_cars.value = new_state

                with solara.Row():
                    solara.Button("＋ 增加", on_click=lambda: update_count(1), color="success")
                    solara.Button("－ 減少", on_click=lambda: update_count(-1), color="error")
                
                if solara.Button("重設選取區域", color="primary", text=True):
                    selected_town.value = None
            else:
                solara.Warning("請點擊地圖上的鄉鎮開始模擬")

            solara.Markdown("---")
            solara.Markdown("#### 雙變量圖例說明")
            solara.Markdown("此地圖同時分析 **高齡人口 (X軸)** 與 **醫師密度 (Y軸)**：")
            solara.Markdown("- 🟥 **深紅 (31)**: 高齡人口多、醫師密度低 (優先投入)")
            solara.Markdown("- 🟪 **深紫 (33)**: 高齡人口多、醫師密度高")
            solara.Markdown("- ⬜ **淺灰 (11)**: 兩者皆低")
            
            

Page()