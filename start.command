#!/bin/bash
cd "$(dirname "$0")"

# 依存パッケージをインストール（初回のみ）
pip3 install -q -r requirements.txt 2>/dev/null

# Streamlit起動
python3 -m streamlit run app.py --server.port 8502
