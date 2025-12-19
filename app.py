import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import solara
import os
import requests
import io
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties

# --- 1. 配置資料來源 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_HOSPITAL_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/113hospital.csv"

# --- FONT SETTING: Iansui (芫荽) ---
# Using the official Google Fonts static URL to ensure the download works
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/iansui/Iansui-Regular.ttf"
FONT_PATH = "Iansui-Regular.ttf"

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            print("Downloading font...")
            r = requests.get(FONT_URL, timeout=10)
            r.raise_for_status()
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
            print("Font downloaded successfully.")
        except Exception as e:
            print(f"Font download failed: {e}")

# Trigger download
download_font()

# Use a fallback if font download fails
if os.path.exists(FONT_PATH):
    font_prop = FontProperties(fname=FONT_PATH)
else:
    font_prop = FontProperties(family="sans-serif")

@solara.component
def Page():
    def load_and_process():
        try:
            # A. 讀取地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL)
            
            # B. 讀取醫院資料
            hosp_raw = pd.read_csv(CSV_HOSPITAL_URL, encoding="big5", header=None)
            df_hosp = hosp_raw[0].str.split(',', expand=True)
            df_hosp.columns = ['town_name', 'total', 'hosp_count', 'clinic_count']
            df_hosp = df_hosp[df_hosp['town_name'] != '鄉鎮']
            df_hosp['hosp_count'] = pd.to_numeric(df_hosp['hosp_count'], errors='coerce').fillna(0)

            # C. 讀取人口資料
            pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding="big5", header=None)
            df_pop = pop_raw[0].str.split(',', expand=True)
            
            pop_header = df_pop.iloc[0].tolist()
            df_pop.columns = pop_header
            df_pop = df_pop[df_pop.iloc[:, 0] != '區域別'] 
            
            df_pop.columns = [str(c).strip() for c in df_pop.columns]
            df_pop.rename(columns={df_pop.columns[0]: 'area_name'}, inplace=True)

            # D. 處理人口數據加總
            age_cols = [c for c in df_pop.columns if '歲' in str(c)]
            for col in age_cols:
                df_pop[col] = df_pop[col].astype(str).str.replace(',', '').replace(['nan', 'None', ''], '0')
                df_pop[col] = pd.to_numeric(df_pop[col], errors='coerce').fillna(0)

            cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101)) or '100' in c]
            df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)

            df_pop_grouped = df_pop.groupby('area_name').agg({
                'pop_65plus': 'sum', 
                'pop_total': 'sum'
            }).reset_index()

            # E. 合併資料並計算指標
            df_merged = pd.merge(
                df_pop_grouped, 
                df_hosp[['town_name', 'hosp_count']], 
                left_on='area_name', 
                right_on='town_name', 
                how='left'
            ).fillna(0)
            
            df_merged['var1'] = df_merged['pop_65plus']
            df_merged['var2'] = (df_merged['hosp_count'] / (df_merged['pop_total'] + 1)) * 10000

            # F. 合併至地理資料
            gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')

            # G. 雙變量分級
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            gdf_final['v1_bin'] = get_bins(gdf_final['var1'])
            gdf_final['v2_bin'] = get_bins(gdf_final['var2'])
            gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)

            return gdf_final
            
        except Exception as e:
            import traceback
            return f"錯誤詳情: {str(e)}\n{traceback.format_exc()}"

    result = solara.use_memo(load_and_process, dependencies=[])

    if isinstance(result, str):
        with solara.Column():
            solara.Error("資料處理失敗")
            solara.Preformatted(result)
        return

    gdf_final = result

    # --- 2. 配色與繪圖 ---
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    with solara.Column(align="center", style={"width": "100%"}):
        # We can use the font name directly in Markdown/HTML headers via CSS
        solara.Markdown("# 彰化縣：高齡人口與醫療資源雙變量地圖分析")
        
        fig = plt.figure(figsize=(10, 11)) 
        
        # --- Map Position ---
        ax = fig.add_axes([0.05, 0.25, 0.9, 0.7])
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.5)
        ax.set_axis_off()

        # --- Legend Position ---
        ax_leg = fig.add_axes([0.08, 0.03, 0.16, 0.16])
        for i in range(1, 4):
            for j in range(1, 4):
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))
        
        ax_leg.set_xlim(1, 4); ax_leg.set_ylim(1, 4)
        
        # Labels using Iansui font
        ax_leg.set_xticks([1.5, 2.5, 3.5])
        ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop, fontsize=15)
        ax_leg.set_yticks([1.5, 2.5, 3.5])
        ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop, fontsize=15)
        
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop, fontsize=20)
        ax_leg.set_ylabel('每萬人醫院密度 →', fontproperties=font_prop, fontsize=20)
        
        # Style cleaning
        for s in ax_leg.spines.values(): s.set_visible(False)
        ax_leg.tick_params(left=False, bottom=False)

        solara.FigureMatplotlib(fig)

Page()