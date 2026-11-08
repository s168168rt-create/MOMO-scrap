import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ---------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------
st.set_page_config(page_title="MOMO 商品價格查詢", page_icon="🛒", layout="wide")

URL = "https://apisearch.momoshop.com.tw/momoSearchCloud/moec/textSearch"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    )
}


def build_payload(keyword: str, page: int) -> dict:
    """建立 MOMO 搜尋 API 的 payload（與原 CODE01 相同，改為可帶入關鍵字與頁數）"""
    return {
        "host": "momoshop",
        "flag": "searchEngine",
        "data": {
            "specialGoodsType": "",
            "isBrandSeriesPage": "false",
            "authorNo": "",
            "originalCateCode": "",
            "cateType": "",
            "searchValue": keyword,
            "cateCode": "",
            "cateLevel": "-1",
            "cp": "N",
            "NAM": "N",
            "first": "N",
            "freeze": "N",
            "superstore": "N",
            "tvshop": "N",
            "china": "N",
            "tomorrow": "N",
            "stockYN": "N",
            "prefere": "N",
            "threeHours": "N",
            "video": "N",
            "cycle": "N",
            "cod": "N",
            "superstorePay": "N",
            "showType": "chessboardType",
            "curPage": str(page),
            "priceS": "0",
            "priceE": "9999999",
            "searchType": "1",
            "reduceKeyword": "",
            "isFuzzy": "0",
            "rtnCateDatainfo": {
                "cateCode": "",
                "cateLv": "-1",
                "keyword": keyword,
                "curPage": str(page),
                "historyDoPush": "false",
                "timestamp": int(time.time() * 1000),
            },
            "flag": 2018,
            "serviceCode": "MT01",
            "addressSearchData": {},
            "adSource": "tenmax",
        },
    }


@st.cache_data(ttl=600, show_spinner=False)
def fetch_products(keyword: str, pages: int) -> pd.DataFrame:
    """爬取 1 ~ pages 頁的商品，回傳 DataFrame（品名、價格）"""
    rows = []
    for page in range(1, pages + 1):
        resp = requests.post(
            URL, headers=HEADERS, json=build_payload(keyword, page), timeout=15
        )
        if resp.status_code != 200:
            raise RuntimeError(f"第 {page} 頁請求失敗，狀態碼: {resp.status_code}")

        goods = resp.json().get("rtnSearchData", {}).get("goodsInfoList", [])
        if not goods:  # 後面沒有資料就提早結束
            break
        for g in goods:
            rows.append(
                {
                    "頁數": page,
                    "品名": g.get("goodsName", ""),
                    "價格": g.get("goodsPrice", ""),
                }
            )
        time.sleep(0.5)  # 避免請求過快

    df = pd.DataFrame(rows, columns=["頁數", "品名", "價格"])
    if df.empty:
        return df

    # 價格清洗：只保留數字（去掉 $、逗號等）
    df["價格"] = df["價格"].astype(str).str.replace(r"[^\d]", "", regex=True)
    df = df[df["價格"] != ""].copy()
    df["價格"] = df["價格"].astype(int)
    return df.reset_index(drop=True)


def add_price_range(df: pd.DataFrame, bins: int = 5) -> pd.DataFrame:
    """依價格切成區間，供圓餅圖與旭日圖使用"""
    out = df.copy()
    if out["價格"].nunique() < 2:
        out["價格區間"] = f"${out['價格'].iloc[0]:,}"
        return out
    cut = pd.cut(out["價格"], bins=bins, include_lowest=True, duplicates="drop")
    out["價格區間"] = cut.apply(
        lambda iv: f"${int(iv.left):,} ~ ${int(iv.right):,}"
    )
    # 依區間大小排序用
    out["_order"] = cut.cat.codes
    return out


# ---------------------------------------------------------------
# 介面
# ---------------------------------------------------------------
st.title("🛒 MOMO 商品價格查詢與視覺化")

with st.sidebar:
    st.header("查詢條件")
    keyword = st.text_input("商品關鍵字", value="行動電源")
    pages = st.number_input("爬取頁數", min_value=1, max_value=20, value=2, step=1)
    chart_type = st.radio("圖表類型", ["圓餅圖", "折線圖", "旭日圖"])
    bins = st.slider("價格區間數（圓餅圖／旭日圖）", 2, 10, 5)
    show_n = st.slider("折線圖／旭日圖顯示商品數", 10, 200, 70, step=10)
    run = st.button("開始查詢", type="primary", use_container_width=True)

if run:
    if not keyword.strip():
        st.warning("請輸入商品關鍵字")
        st.stop()
    try:
        with st.spinner("資料爬取中..."):
            st.session_state["df"] = fetch_products(keyword.strip(), int(pages))
            st.session_state["kw"] = keyword.strip()
    except Exception as e:
        st.error(f"爬取失敗：{e}")
        st.stop()

df = st.session_state.get("df")
kw = st.session_state.get("kw", "")

if df is None:
    st.info("請在左側輸入商品與頁數，然後按「開始查詢」。")
    st.stop()

if df.empty:
    st.warning("查無資料，請換個關鍵字試試。")
    st.stop()

# ---- 統計數字 ----
avg_price = df["價格"].mean()
c1, c2, c3, c4 = st.columns(4)
c1.metric("商品數", f"{len(df):,}")
c2.metric("平均價格", f"${avg_price:,.0f}")
c3.metric("最高價格", f"${df['價格'].max():,}")
c4.metric("最低價格", f"${df['價格'].min():,}")

# ---- 圖表 ----
# Plotly 由瀏覽器渲染文字，不需要另外安裝中文字型
st.subheader(f"「{kw}」價格分析 － {chart_type}")

if chart_type == "圓餅圖":
    d = add_price_range(df, bins)
    cnt = (
        d.groupby(["價格區間", "_order"] if "_order" in d else ["價格區間"])
        .size()
        .reset_index(name="商品數")
    )
    if "_order" in cnt:
        cnt = cnt.sort_values("_order")
    fig = px.pie(cnt, names="價格區間", values="商品數", hole=0.3)
    fig.update_traces(textinfo="percent+label", sort=False)

elif chart_type == "折線圖":
    d = df.head(show_n).reset_index(drop=True)
    fig = px.line(
        d,
        x=d.index,
        y="價格",
        markers=True,
        hover_name="品名",
        labels={"x": "商品序號 (store id)", "價格": "價格 (price)"},
    )
    fig.add_hline(
        y=avg_price,
        line_dash="dash",
        line_color="red",
        annotation_text=f"平均 {avg_price:,.0f}",
    )

else:  # 旭日圖
    d = add_price_range(df.head(show_n), bins)
    d["商品"] = d["品名"].str.slice(0, 18) + "…"
    d["商品數"] = 1
    fig = px.sunburst(
        d,
        path=["價格區間", "商品"],
        values="商品數",
        hover_data={"價格": True},
    )

fig.update_layout(height=650, margin=dict(t=30, l=10, r=10, b=10))
st.plotly_chart(fig, use_container_width=True)

# ---- 資料表與下載 ----
st.subheader("原始資料")
st.dataframe(df, use_container_width=True, height=350)

filename = f"MOMO_{kw}_{datetime.now():%Y%m%d}.csv"
st.download_button(
    "下載 CSV",
    data=df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
    file_name=filename,
    mime="text/csv",
)
