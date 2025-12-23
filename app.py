import solara
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import os
import requests
import io
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties

# --- 1. 配置與字體設定 ---
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
        except Exception as e:
            print(f"Font download failed: {e}")

download_font()
font_prop = FontProperties(fname=FONT_PATH) if os.path.exists(FONT_PATH) else FontProperties(family="sans-serif")

# --- 2. 資料處理 (快取以提高性能) ---
@solara.memoize
def get_processed_data():
    gdf = gpd.read_file(TOWNSHIPS_URL)
    
    # 處理醫師資料
    df_doc = pd.read_csv(CSV_DOCTOR_URL)
    df_doc = df_doc[df_doc['區域'] != '總計'][['區域', '總計']]
    df_doc.columns = ['town_name', 'doctor_per_10k']
    df_doc['doctor_per_10k'] = pd.to_numeric(df_doc['doctor_per_10k'], errors='coerce').fillna(0)

    # 處理人口資料
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

    # 合併與分箱
    df_merged = pd.merge(df_pop_grouped, df_doc, left_on='area_name', right_on='town_name', how='inner')
    gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')

    gdf_final['v1_bin'] = pd.qcut(gdf_final['pop_65plus'].rank(method='first'), 3, labels=['1', '2', '3'])
    gdf_final['v2_bin'] = pd.qcut(gdf_final['doctor_per_10k'].rank(method='first'), 3, labels=['1', '2', '3'])
    gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)
    
    return gdf_final

# --- 3. Solara 組件 ---
@solara.component
def Page():
    # 獲取資料
    gdf_final = get_processed_data()
    
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    with solara.Column(align="center", style={"padding": "20px"}):
        solara.Markdown("# 彰化縣：高齡人口與醫師資源雙變量地圖分析")
        
        # 建立 Matplotlib 圖表
        fig = plt.figure(figsize=(10, 11))
        ax = fig.add_axes([0.05, 0.25, 0.9, 0.7])
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.5)
        ax.set_axis_off()

        # 圖例 (Legend)
        ax_leg = fig.add_axes([0.15, 0.05, 0.15, 0.15])
        for i in range(1, 4):
            for j in range(1, 4):
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))
        
        ax_leg.set_xlim(1, 4)
        ax_leg.set_ylim(1, 4)
        ax_leg.set_xticks([1.5, 2.5, 3.5])
        ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_yticks([1.5, 2.5, 3.5])
        ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop)
        ax_leg.set_ylabel('每萬人醫師數 →', fontproperties=font_prop)

        # 使用 Solara 的 Figure 組件直接顯示
        solara.FigureMatplotlib(fig)
        
        solara.Markdown("> 註：顏色深淺代表資源與人口的相對集中程度。")