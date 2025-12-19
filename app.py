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

# 下載中文字型 (Noto Sans TC)
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
FONT_PATH = "NotoSansTC.ttf"

if not os.path.exists(FONT_PATH):
    r = requests.get(FONT_URL)
    with open(FONT_PATH, "wb") as f:
        f.write(r.content)

font_prop = FontProperties(fname=FONT_PATH)

@solara.component
def Page():
    def load_and_process():
        try:
            # A. 讀取地理資料
            gdf = gpd.read_file(TOWNSHIPS_URL)
            
            # B. 讀取 CSV
            def safe_read_csv(url):
                content = requests.get(url).content
                try:
                    df = pd.read_csv(io.BytesIO(content), encoding='utf-8', sep=None, engine='python')
                except:
                    df = pd.read_csv(io.BytesIO(content), encoding='big5', sep=None, engine='python')
                
                # 清除欄位名稱的空格或特殊字元
                df.columns = df.columns.str.strip()
                
                if len(df.columns) == 1:
                    col_name = df.columns[0]
                    new_df = df[col_name].str.split(',', expand=True)
                    new_header = [h.strip() for h in col_name.split(',')]
                    if len(new_df.columns) == len(new_header):
                        new_df.columns = new_header
                    return new_df
                return df

            df_pop = safe_read_csv(CSV_POPULATION_URL)
            df_hosp = safe_read_csv(CSV_HOSPITAL_URL)

            # C. 重新命名並確保資料乾淨
            # 假設：第一欄是區域名稱，其餘欄位包含年齡數據
            df_pop.rename(columns={df_pop.columns[0]: 'area_name'}, inplace=True)
            df_hosp.rename(columns={df_hosp.columns[0]: 'town_name', df_hosp.columns[2]: 'hosp_count'}, inplace=True)

            # D. 處理人口數據
            age_cols = [c for c in df_pop.columns if '歲' in str(c)]
            for col in age_cols:
                df_pop[col] = df_pop[col].astype(str).str.replace(',', '').replace(['nan', 'None', ''], '0')
                df_pop[col] = pd.to_numeric(df_pop[col], errors='coerce').fillna(0)

            # 篩選 65 歲以上
            cols_65plus = [c for c in age_cols if any(str(i) in c for i in range(65, 101)) or '100' in c]
            df_pop['pop_65plus'] = df_pop[cols_65plus].sum(axis=1)
            df_pop['pop_total'] = df_pop[age_cols].sum(axis=1)

            df_pop_grouped = df_pop.groupby('area_name').agg({'pop_65plus': 'sum', 'pop_total': 'sum'}).reset_index()

            # E. 合併醫院
            df_hosp['hosp_count'] = pd.to_numeric(df_hosp['hosp_count'], errors='coerce').fillna(0)
            df_merged = pd.merge(df_pop_grouped, df_hosp[['town_name', 'hosp_count']], left_on='area_name', right_on='town_name', how='left').fillna(0)
            
            df_merged['var1'] = df_merged['pop_65plus'] 
            df_merged['var2'] = (df_merged['hosp_count'] / (df_merged['pop_total'] + 1)) * 10000

            # F. 合併至地理資料 (注意：欄位名稱 townname 必須完全匹配)
            gdf_final = gdf.merge(df_merged, left_on='townname', right_on='area_name', how='inner')

            # G. 分級 (處理重複值問題，加入 rank)
            def get_bins(series):
                return pd.qcut(series.rank(method='first'), 3, labels=['1', '2', '3'])

            gdf_final['v1_bin'] = get_bins(gdf_final['var1'])
            gdf_final['v2_bin'] = get_bins(gdf_final['var2'])
            gdf_final['bi_class'] = gdf_final['v1_bin'].astype(str) + gdf_final['v2_bin'].astype(str)

            return gdf_final
        except Exception as e:
            import traceback
            return f"錯誤詳情: {str(e)}\n{traceback.format_exc()}"

    # 使用 use_memo 避免重複下載資料
    result = solara.use_memo(load_and_process, dependencies=[])

    if isinstance(result, str):
        with solara.Column():
            solara.Error("資料處理失敗")
            solara.Preformatted(result)
        return

    gdf_final = result

    # --- 配色與繪圖 ---
    color_matrix = {
        '11': '#e8e8e8', '21': '#e4acac', '31': '#c85a5a', 
        '12': '#b0d5df', '22': '#ad9ea5', '32': '#985356', 
        '13': '#64acbe', '23': '#627f8c', '33': '#574249'  
    }
    
    # 確保顏色對應正確
    gdf_final['color'] = gdf_final['bi_class'].map(color_matrix)

    with solara.Column(align="center", style={"width": "100%"}):
        solara.Markdown("# 彰化縣高齡人口與醫療資源雙變量地圖")
        
        # 使用 matplotlib 面向對象寫法
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111)
        
        # 繪製地圖
        gdf_final.plot(ax=ax, color=gdf_final['color'], edgecolor='gray', linewidth=0.5)
        ax.set_axis_off()

        # 3x3 圖例 (雙變量矩陣)
        ax_leg = fig.add_axes([0.15, 0.15, 0.15, 0.15]) # x, y, width, height
        for i in range(1, 4):
            for j in range(1, 4):
                # i: 65歲人口等級 (x), j: 醫院密度等級 (y)
                ax_leg.add_patch(Rectangle((i, j), 1, 1, facecolor=color_matrix[f"{i}{j}"], edgecolor='w'))
        
        ax_leg.set_xlim(1, 4)
        ax_leg.set_ylim(1, 4)
        ax_leg.set_xticks([1.5, 2.5, 3.5])
        ax_leg.set_xticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_yticks([1.5, 2.5, 3.5])
        ax_leg.set_yticklabels(['低', '中', '高'], fontproperties=font_prop)
        ax_leg.set_xlabel('65歲以上人口 →', fontproperties=font_prop, fontsize=8)
        ax_leg.set_ylabel('醫院密度 →', fontproperties=font_prop, fontsize=8)
        
        # 移除圖例邊框
        for s in ax_leg.spines.values(): s.set_visible(False)
        ax_leg.tick_params(left=False, bottom=False)

        solara.FigureMatplotlib(fig)
        
        with solara.Card():
            solara.Markdown("""
            ### 圖表說明
            - **橫軸 (X)**：65歲以上高齡人口總數。
            - **縱軸 (Y)**：每萬人擁有的醫院數量（醫療資源可及性）。
            - **深灰色/紫色區域**：代表該區人口老化且醫療資源豐富。
            - **深紅色區域**：代表該區人口老化嚴重，但醫療資源相對匱乏。
            """)

# 啟動命令: solara run your_script.py