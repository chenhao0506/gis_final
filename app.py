import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import solara
import os
import requests
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties

# --- 配置區 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_HOSPITAL_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/113hospital.csv"

# 下載中文字型 (避免 Hugging Face 亂碼)
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
FONT_PATH = "NotoSansTC.ttf"

if not os.path.exists(FONT_PATH):
    r = requests.get(FONT_URL)
    with open(FONT_PATH, "wb") as f:
        f.write(r.content)

font_prop = FontProperties(fname=FONT_PATH)

@solara.component
def Page():
    # 使用 solara.use_memo 來避免重複讀取資料，提高效能
    def load_and_process():
        # 1. 讀取
        gdf = gpd.read_file(TOWNSHIPS_URL)
        df_pop = pd.read_csv(CSV_POPULATION_URL)
        df_hosp = pd.read_csv(CSV_HOSPITAL_URL, encoding = big5)

        # 2. 處理人口 (清理逗號並轉數字)
        age_cols = df_pop.columns[2:]
        for col in age_cols:
            df_pop[col] = df_pop[col].astype(str).str.replace(',', '').replace('nan', '0').astype(float)

        # 加總 65 歲以上 (從第 67 欄位開始大致為 65 歲)
        # 這裡精確根據欄位名稱包含數字來篩選
        cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101))]
        
        df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
        df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)

        df_pop_grouped = df_pop.groupby('區域別').agg({
            'pop_65plus': 'sum',
            'pop_total': 'sum'
        }).reset_index()

        # 3. 合併醫院與地理
        df_merged = pd.merge(df_pop_grouped, df_hosp[['鄉鎮', '醫院數']], left_on='區域別', right_on='鄉鎮', how='left').fillna(0)
        
        # 計算核心變數
        df_merged['var1'] = df_merged['pop_65plus']
        df_merged['var2'] = (df_merged['醫院數'] / df_merged['pop_total']) * 10000

        gdf_final = gdf.merge(df_merged, left_on='townname', right_on='區域別')

        # 4. 雙變量分類
        def get_bins(series):
            return pd.qcut(series.rank(method='first'), 3, labels=[1, 2, 3]).astype(int)

        gdf_final['v1_bin'] = get_bins(gdf_final['var1'])
        gdf_final['v2_bin'] = get_bins(gdf_final['var2'])
        gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)

        return gdf_final

    gdf_final = solara.use_memo(load_and_process)

    # 5. 配色矩陣
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a',
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    # --- 介面呈現 ---
    with solara.Column(align="center", style={"padding": "20px"}):
        solara.Markdown("# 彰化縣雙變量面量圖分析")
        solara.Markdown("### 分析指標：65歲以上人口 vs. 每萬人醫院數")
        
        # 繪圖邏輯
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.5)
        ax.set_axis_off()

        # 加上非旋轉圖例
        ax_leg = fig.add_axes([0.1, 0.1, 0.18, 0.18])
        for i in range(1, 4):
            for j in range(1, 4):
                code = f"{i}{j}"
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[code]))
        
        ax_leg.set_xlim(1, 4); ax_leg.set_ylim(1, 4)
        ax_leg.set_xticks([1.5, 2.5, 3.5]); ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_yticks([1.5, 2.5, 3.5]); ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_xlabel('65歲以上人口', fontproperties=font_prop, fontsize=10)
        ax_leg.set_ylabel('每萬人醫院數', fontproperties=font_prop, fontsize=10)
        ax_leg.set_aspect('equal')
        for s in ax_leg.spines.values(): s.set_visible(False)

        # 顯示圖片
        solara.FigureMatplotlib(fig)
        
        solara.Info("圖例說明：深紫色代表高齡人口多且醫療資源密度高；深紅色代表高齡人口多但資源密度低（需關注區域）。")