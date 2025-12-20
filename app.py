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
# 更新後的醫師資料網址
CSV_DOCTOR_URL = "https://raw.githubusercontent.com/chenhao0506/gis_final/main/changhua_doctors_per_10000.csv"

# --- FONT SETTING: Iansui (芫荽) ---
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/iansui/Iansui-Regular.ttf"
FONT_PATH = "Iansui-Regular.ttf"

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get(FONT_URL, timeout=10)
            r.raise_for_status()
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
        except Exception as e:
            print(f"Font download failed: {e}")

download_font()

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
            
            # B. 讀取醫師資料 (針對新格式優化)
            # 新格式標頭為: 區域,西醫師,牙醫師,中醫師,總計
            df_doc = pd.read_csv(CSV_DOCTOR_URL, encoding="utf-8")
            # 過濾掉最後一列的「總計」(全縣加總)
            df_doc = df_doc[df_doc['區域'] != '總計']
            # 選取需要的欄位
            df_doc = df_doc[['區域', '總計']].copy()
            df_doc.columns = ['town_name', 'doctor_per_10k']
            df_doc['doctor_per_10k'] = pd.to_numeric(df_doc['doctor_per_10k'], errors='coerce').fillna(0)

            # C. 讀取人口資料 (處理原始資料中的逗號與分割問題)
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

            # 定義 65 歲以上人口
            cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101)) or '100' in c]
            df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)

            df_pop_grouped = df_pop.groupby('area_name').agg({
                'pop_65plus': 'sum'
            }).reset_index()

            # E. 合併資料
            df_merged = pd.merge(
                df_pop_grouped, 
                df_doc, 
                left_on='area_name', 
                right_on='town_name', 
                how='left'
            ).fillna(0)
            
            # 定義雙變量：
            # var1: 65歲以上人口數
            # var2: 每萬人醫師數 (直接由新 CSV 提供)
            df_merged['var1'] = df_merged['pop_65plus']
            df_merged['var2'] = df_merged['doctor_per_10k']

            # F. 合併至地理資料
            gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')

            # G. 雙變量分級 (使用分位數 qcut 分成三等份)
            def get_bins(series):
                # 處理重複值較多時使用 rank(method='first') 確保能分成三份
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
    # 雙變量矩陣顏色 (橫軸：人口，縱軸：醫師)
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'   
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    with solara.Column(align="center", style={"width": "100%"}):
        solara.Markdown("# 彰化縣：高齡人口與醫師資源雙變量地圖分析")
        
        fig = plt.figure(figsize=(10, 11)) 
        
        # --- 地圖區域 ---
        ax = fig.add_axes([0.05, 0.3, 0.9, 0.65])
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.5)
        ax.set_axis_off()

        # --- 雙變量圖例區域 ---
        ax_leg = fig.add_axes([0.15, 0.08, 0.16, 0.16])
        for i in range(1, 4):
            for j in range(1, 4):
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))
        
        ax_leg.set_xlim(1, 4)
        ax_leg.set_ylim(1, 4)
        
        # 設定圖例文字
        ax_leg.set_xticks([1.5, 2.5, 3.5])
        ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop, fontsize=15)
        ax_leg.set_yticks([1.5, 2.5, 3.5])
        ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop, fontsize=15)
        
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop, fontsize=18)
        ax_leg.set_ylabel('每萬人醫師數 →', fontproperties=font_prop, fontsize=18)
        
        # 移除圖例邊框
        for s in ax_leg.spines.values(): s.set_visible(False)
        ax_leg.tick_params(left=False, bottom=False)

        solara.FigureMatplotlib(fig)

Page()