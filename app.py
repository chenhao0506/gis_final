import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import solara
import os
import requests
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties

# --- 1. 配置資料來源 ---
TOWNSHIPS_URL = 'https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/changhua.geojson'
CSV_POPULATION_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/age_population.csv"
CSV_HOSPITAL_URL = "https://raw.githubusercontent.com/peijhuuuuu/Changhua_hospital/main/113hospital.csv"

# 下載中文字型 (解決 Hugging Face 亂碼問題)
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
FONT_PATH = "NotoSansTC.ttf"

if not os.path.exists(FONT_PATH):
    try:
        r = requests.get(FONT_URL)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    except:
        print("字型下載失敗")

font_prop = FontProperties(fname=FONT_PATH)

@solara.component
def Page():
    def load_and_process():
        try:
            # A. 讀取地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL)
            
            # B. 讀取 CSV (加入 sep=None 自動偵測分隔符，解決 1 element 錯誤)
            df_pop = pd.read_csv(CSV_POPULATION_URL, encoding='big5', sep=None, engine='python')
            df_hosp = pd.read_csv(CSV_HOSPITAL_URL, encoding='big5', sep=None, engine='python')

            # C. 安全地重命名人口資料欄位
            # 確保列數足夠才重命名，避免 Length mismatch
            if len(df_pop.columns) >= 2:
                pop_new_names = ['area_name', 'gender'] + list(df_pop.columns[2:])
                df_pop.columns = pop_new_names
            
            # D. 安全地重命名醫院資料欄位
            if len(df_hosp.columns) >= 3:
                # 根據資料結構：0:鄉鎮, 1:合計, 2:醫院數
                hosp_new_names = ['town_name', 'total_count', 'hosp_count'] + list(df_hosp.columns[3:])
                df_hosp.columns = hosp_new_names
            else:
                return "醫院資料讀取失敗，請檢查 CSV 分隔符號"

            # E. 數據清理與加總
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = df_pop[col].astype(str).str.replace(',', '').replace('nan', '0').astype(float)

            # 篩選 65 歲以上 (搜尋標題含 65~100)
            cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 110))]
            df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)

            # 合併男女數據
            df_pop_grouped = df_pop.groupby('area_name').agg({
                'pop_65plus': 'sum',
                'pop_total': 'sum'
            }).reset_index()

            # F. 合併人口與醫院
            df_merged = pd.merge(
                df_pop_grouped, 
                df_hosp[['town_name', 'hosp_count']], 
                left_on='area_name', 
                right_on='town_name', 
                how='left'
            ).fillna(0)
            
            # 計算核心指標
            df_merged['var1'] = df_merged['pop_65plus'] 
            df_merged['var2'] = (df_merged['hosp_count'] / df_merged['pop_total']) * 10000

            # G. 合併至地理資料
            gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name')

            # H. 雙變量分類
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=[1, 2, 3]).astype(int)

            gdf_final['v1_bin'] = get_bins(gdf_final['var1'])
            gdf_final['v2_bin'] = get_bins(gdf_final['var2'])
            gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)

            return gdf_final
        except Exception as e:
            return str(e)

    # 執行處理
    result = solara.use_memo(load_and_process)

    # 錯誤處理顯示
    if isinstance(result, str):
        with solara.Column():
            solara.Error(f"發生錯誤: {result}")
            solara.Markdown("請檢查 CSV 檔案編碼或網路連結。")
        return

    gdf_final = result

    # --- 2. 設定配色與繪圖 ---
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'  
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    with solara.Column(align="center", style={"padding": "30px"}):
        solara.Markdown("# 彰化縣高齡人口與醫療資源分佈分析")
        
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.8)
        ax.set_axis_off()

        # 繪製 3x3 圖例
        ax_leg = fig.add_axes([0.1, 0.1, 0.2, 0.2])
        for i in range(1, 4):
            for j in range(1, 4):
                code = f"{i}{j}"
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[code], edgecolor='white'))
        
        ax_leg.set_xlim(1, 4); ax_leg.set_ylim(1, 4)
        ax_leg.set_xticks([1.5, 2.5, 3.5]); ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_yticks([1.5, 2.5, 3.5]); ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop, fontsize=10)
        ax_leg.set_ylabel('每萬人醫院數 →', fontproperties=font_prop, fontsize=10)
        ax_leg.set_aspect('equal')
        for s in ax_leg.spines.values(): s.set_visible(False)

        solara.FigureMatplotlib(fig)
        
        with solara.Card("結果解讀說明"):
            solara.Markdown("""
            - **深紅色 (31)**：高齡人口多但醫療資源密度低 (關注區)。
            - **深紫色 (33)**：兩者皆高，高齡化嚴重但醫療資源相對豐富。
            - **深藍色 (13)**：高齡人口少但醫療密度極高。
            """)

# --- 啟動 ---
if __name__ == "__main__":
    Page()