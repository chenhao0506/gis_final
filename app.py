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

# 下載中文字型
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
FONT_PATH = "NotoSansTC.ttf"

if not os.path.exists(FONT_PATH):
    r = requests.get(FONT_URL); f = open(FONT_PATH, "wb"); f.write(r.content); f.close()

font_prop = FontProperties(fname=FONT_PATH)

@solara.component
def Page():
    def load_and_process():
        try:
            # A. 讀取地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL)
            
            # B. 讀取 CSV (改用更強大的讀取邏輯)
            def safe_read_csv(url):
                content = requests.get(url).content
                # 嘗試 Big5 讀取
                try:
                    df = pd.read_csv(io.BytesIO(content), encoding='big5', sep=None, engine='python')
                except:
                    df = pd.read_csv(io.BytesIO(content), encoding='utf-8', sep=None, engine='python')
                
                # 如果讀出來只有一欄，強行手動切分
                if len(df.columns) == 1:
                    col_name = df.columns[0]
                    new_df = df[col_name].str.split(',', expand=True)
                    # 把原本的標頭也拆了當作新的標頭
                    new_header = col_name.split(',')
                    if len(new_df.columns) == len(new_header):
                        new_df.columns = new_header
                    return new_df
                return df

            df_pop = safe_read_csv(CSV_POPULATION_URL)
            df_hosp = safe_read_csv(CSV_HOSPITAL_URL)

            # C. 重新命名 (對準資料位置)
            # 人口資料: 0:區域別, 1:性別
            df_pop.columns = ['area_name', 'gender'] + list(df_pop.columns[2:])
            # 醫院資料: 0:鄉鎮, 1:合計, 2:醫院數
            df_hosp.columns = ['town_name', 'total_count', 'hosp_count'] + list(df_hosp.columns[3:])

            # D. 處理人口數據
            age_cols = [c for c in df_pop.columns if '歲' in c]
            for col in age_cols:
                df_pop[col] = df_pop[col].astype(str).str.replace(',', '').replace('nan', '0').replace('None', '0').replace('', '0')
                df_pop[col] = pd.to_numeric(df_pop[col], errors='coerce').fillna(0)

            # 篩選 65 歲以上 (包含 100 歲以上)
            cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101)) or '100' in c]
            df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)

            df_pop_grouped = df_pop.groupby('area_name').agg({'pop_65plus': 'sum', 'pop_total': 'sum'}).reset_index()

            # E. 合併醫院與計算指標
            df_hosp['hosp_count'] = pd.to_numeric(df_hosp['hosp_count'], errors='coerce').fillna(0)
            df_merged = pd.merge(df_pop_grouped, df_hosp[['town_name', 'hosp_count']], left_on='area_name', right_on='town_name', how='left').fillna(0)
            
            df_merged['var1'] = df_merged['pop_65plus'] 
            df_merged['var2'] = (df_merged['hosp_count'] / df_merged['pop_total']) * 10000

            # F. 合併至地理資料
            gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name')

            # G. 分級 (Quantile)
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=[1, 2, 3]).astype(int)

            gdf_final['v1_bin'] = get_bins(gdf_final['var1'])
            gdf_final['v2_bin'] = get_bins(gdf_final['var2'])
            gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)

            return gdf_final
        except Exception as e:
            return f"Error details: {str(e)}"

    result = solara.use_memo(load_and_process)

    if isinstance(result, str):
        with solara.Column():
            solara.Error(f"讀取異常: {result}")
            solara.Markdown("嘗試解決方案：請確認 GitHub 上的 CSV 檔案是否為標準逗號分隔格式。")
        return

    gdf_final = result

    # --- 配色與繪圖 ---
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'  
    }
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    with solara.Column(align="center"):
        solara.Markdown("# 彰化縣高齡人口與醫療資源雙變量地圖")
        
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='white', linewidth=0.8)
        ax.set_axis_off()

        # 3x3 圖例
        ax_leg = fig.add_axes([0.1, 0.1, 0.2, 0.2])
        for i in range(1, 4):
            for j in range(1, 4):
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='white'))
        
        ax_leg.set_xlim(1, 4); ax_leg.set_ylim(1, 4)
        ax_leg.set_xticks([1.5, 2.5, 3.5]); ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_yticks([1.5, 2.5, 3.5]); ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop, fontsize=9)
        ax_leg.set_ylabel('每萬人醫院數 →', fontproperties=font_prop, fontsize=9)
        ax_leg.set_aspect('equal')
        for s in ax_leg.spines.values(): s.set_visible(False)

        solara.FigureMatplotlib(fig)
        solara.Info("圖例：深紅色代表高齡人口多但醫院密度低；深紫色代表兩者皆高。")

if __name__ == "__main__":
    Page()