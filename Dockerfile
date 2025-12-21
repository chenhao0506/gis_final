# 1. 使用 Python 3.11-slim
FROM python:3.11-slim

# 2. 設定工作目錄
WORKDIR /app

# 3. 複製需求檔案
COPY requirements.txt .

# 4. 安裝系統依賴
# Added libfontconfig1 for Matplotlib font rendering and cleaned up apt-get
RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 5. 複製所有程式碼
COPY . .

# 6. 修改執行指令 (從 solara 改為 python)
# 注意：確保您的 app.py 最後有 app.run_server(host='0.0.0.0', port=7860)
CMD ["python", "app.py"]