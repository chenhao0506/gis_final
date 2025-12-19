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

# 下載中文字型 (解決 Hugging Face Linux 環境亂碼問題)
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
FONT_PATH = "NotoSansTC.ttf"

if not os.path.exists(FONT_PATH):
    try:
        r = requests.get(FONT_URL)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    except:
        print("字型下載失敗，請檢查網路連線")

font_prop = FontProperties(fname=FONT_PATH)

@solara.component
def Page():
    # 使用 memo 確保資料只在啟動時處理一次
    def load_and_process():
        # A. 讀取地理資料
        gdf = gpd.read_file(TOWNSHIPS_URL)
        
        # B. 讀取 CSV (強制使用 Big5 編碼)
        # 使用 low_memory=False 確保穩定性
        df_pop_raw = pd.read_csv(CSV_POPULATION_URL, encoding='big5', low_memory=False)
        df_hosp_raw = pd.read_csv(CSV_HOSPITAL_URL, encoding='big5', low_memory=False)

        # C. 強制重新命名欄位，解決中文字標頭導致的 KeyError
        # 醫院資料: 0:鄉鎮, 1:合計, 2:醫院數
        df_hosp = df_hosp_raw.copy()
        df_hosp.columns = ['town_name', 'total_count', 'hosp_count', 'clinic_count'] + list(df_hosp.columns[4:])
        
        # 人口資料: 0:區域別, 1:性別, 2之後是各歲數人口
        df_pop = df_pop_raw.copy()
        df_pop.columns = ['area_name', 'gender'] + list(df_pop.columns[2:])

        # D. 清理與加總數據
        # 將所有人口欄位的逗號去掉並轉為浮點數
        age_cols = df_pop.columns[2:]
        for col in age_cols:
            df_pop[col] = df_pop[col].astype(str).str.replace(',', '').replace('nan', '0').astype(float)

        # 篩選 65 歲以上欄位 (尋找標題含有 "65" 到 "100" 字眼的欄位)
        cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 110))]
        
        df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
        df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)

        # 男女數據合併 (按區域別加總)
        df_pop_grouped = df_pop.groupby('area_name').agg({
            'pop_65plus': 'sum',
            'pop_total': 'sum'
        }).reset_index()

        # E. 合併資料 (人口 + 醫院)
        df_merged = pd.merge(
            df_pop_grouped, 
            df_hosp[['town_name', 'hosp_count']], 
            left_on='area_name', 
            right_on='town_name', 
            how='left'
        ).fillna(0)
        
        # F. 計算雙變量核心指標
        df_merged['var1'] = df_merged['pop_65plus'] # 變數 1: 高齡人口數
        df_merged['var2'] = (df_merged['hosp_count'] / df_merged['pop_total']) * 10000 # 變數 2: 每萬人醫院數

        # G. 合併至地理資料 (GeoJSON 屬性為 townname)
        gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name')

        # H. 分級分類 (Quantile 3x3)
        def get_bins(series):
            # 使用 rank 處理重複值問題，確保分為三組
            return pd.qcut(series.rank(method='first'), 3, labels=[1, 2, 3]).astype(int)

        gdf_final['v1_bin'] = get_bins(gdf_final['var1'])
        gdf_final['v2_bin'] = get_bins(gdf_final['var2'])
        gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)

        return gdf_final

    # 執行資料處理
    gdf_final = solara.use_memo(load_and_process)

    # --- 2. 設定配色矩陣 ---
    # 模仿你提供的藍、紅、紫專業配色
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', # X軸(高齡): 灰 -> 紅
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'  # Y軸(醫院): 灰 -> 藍
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    # --- 3. 建立 Solara 介面 ---
    with solara.Column(align="center", style={"padding": "30px", "background-color": "#f5f5f5"}):
        solara.Markdown("# 彰化縣高齡人口與醫療資源分佈")
        solara.Markdown("### 雙變量面量圖 (Bivariate Choropleth Map)")
        
        # 繪圖
        fig, ax = plt.subplots(figsize=(12, 12))
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.8)
        ax.set_axis_off()

        # 繪製非旋轉式 3x3 圖例
        ax_leg = fig.add_axes([0.1, 0.1, 0.22, 0.22])
        for i in range(1, 4):
            for j in range(1, 4):
                code = f"{i}{j}"
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[code], edgecolor='white', linewidth=0.5))
        
        ax_leg.set_xlim(1, 4)
        ax_leg.set_ylim(1, 4)
        
        # 設定標籤文字與字型
        ax_leg.set_xticks([1.5, 2.5, 3.5])
        ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_yticks([1.5, 2.5, 3.5])
        ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
        
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop, fontsize=11)
        ax_leg.set_ylabel('每萬人醫院數 →', fontproperties=font_prop, fontsize=11)
        ax_leg.set_aspect('equal')
        
        # 去除圖例背景邊框
        for spine in ax_leg.spines.values():
            spine.set_visible(False)

        # 輸出圖表
        solara.FigureMatplotlib(fig)

        with solara.Card("圖表說明"):
            solara.Markdown("""
            * **深紅色 (右下)**：高齡人口多，但醫療資源密度低 (可能為資源缺口區)。
            * **深藍色 (左上)**：高齡人口少，但醫療資源密度極高。
            * **深紫色 (右上)**：高齡人口與醫療資源密度皆高。
            * **淺灰色 (左下)**：兩者皆處於低分佈狀態。
            """)
        
        solara.Success("資料處理完成：已自動合併男女數據並修正 Big5 編碼問題。")

# 啟動應用
if __name__ == "__main__":
    Page()