from __future__ import annotations

from pathlib import Path

import pandas as pd

try:
    import streamlit as st
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Streamlit is not installed. Install dependencies with `pip install -r requirements.txt` "
        f"and rerun `streamlit run app.py`. Detail: {exc}"
    ) from exc

from stock_screener.analyze_reports import analyze_reports
from stock_screener.io import default_candidate_paths, read_table
from stock_screener.paths import OUTPUT_DIR, period_output_path
from stock_screener.refresh_reports import refresh_reports


st.set_page_config(page_title="半年报文本验证", layout="wide")


def load_optional_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return read_table(path)


def show_status_cards(df: pd.DataFrame) -> None:
    if df.empty or "candidate_status" not in df.columns:
        st.info("暂无文本分析结果。")
        return
    counts = df["candidate_status"].fillna("unknown").value_counts().to_dict()
    columns = st.columns(4)
    for column, label in zip(columns, ["A_confirmed", "B_watch", "C_reject", "D_pending"]):
        column.metric(label, int(counts.get(label, 0)))


def main() -> None:
    st.title("A股半年报文本验证 Dashboard")
    st.caption("研究辅助工具：只对初筛通过名单做正式半年报文本分析，不生成交易指令。")

    with st.sidebar:
        period = st.text_input("报告期", value="20260630")
        st.write("候选池默认路径")
        for path in default_candidate_paths(period):
            exists = "存在" if path.exists() else "缺失"
            st.code(f"{path} [{exists}]")
        candidate_file = st.file_uploader("或上传候选池 CSV/XLSX", type=["csv", "xlsx"])
        run_limit = st.number_input("本次最多处理数量", min_value=1, max_value=500, value=30, step=1)

    uploaded_path: Path | None = None
    if candidate_file is not None:
        suffix = Path(candidate_file.name).suffix.lower()
        uploaded_path = OUTPUT_DIR / f"uploaded_candidates_{period}{suffix}"
        uploaded_path.parent.mkdir(parents=True, exist_ok=True)
        uploaded_path.write_bytes(candidate_file.getbuffer())

    tab_candidates, tab_reports, tab_analysis, tab_export = st.tabs(
        ["候选池", "半年报抓取", "半年报文本分析", "导出"]
    )

    with tab_candidates:
        st.subheader("初筛候选池")
        try:
            candidate_path = uploaded_path
            candidates = read_table(candidate_path) if candidate_path else load_optional_table(
                next((path for path in default_candidate_paths(period) if path.exists()), Path("__missing__"))
            )
            if candidates.empty:
                st.warning("未找到候选池。请先放置 candidates_{period}.xlsx/csv，或在侧边栏上传。")
            else:
                st.dataframe(candidates, use_container_width=True, height=480)
        except Exception as exc:
            st.error(f"读取候选池失败：{exc}")

    with tab_reports:
        st.subheader("公告下载与章节截取")
        col1, col2 = st.columns(2)
        if col1.button("刷新半年报公告/PDF", type="primary"):
            try:
                with st.spinner("正在刷新公告、下载PDF并截取章节..."):
                    manifest = refresh_reports(period=period, candidate_path=uploaded_path, limit=int(run_limit))
                st.success(f"完成 {len(manifest)} 条记录。")
            except Exception as exc:
                st.error(f"刷新失败：{exc}")
        manifest = load_optional_table(period_output_path("report_manifest", period, ".xlsx"))
        if manifest.empty:
            st.info("暂无 report_manifest。")
        else:
            st.dataframe(manifest, use_container_width=True, height=480)

    with tab_analysis:
        st.subheader("LLM 文本验证结果")
        if st.button("分析已缓存章节", type="primary"):
            try:
                with st.spinner("正在分析半年报章节..."):
                    result = analyze_reports(period=period, candidate_path=uploaded_path, limit=int(run_limit))
                st.success(f"完成 {len(result)} 只股票文本分析。")
            except Exception as exc:
                st.error(f"分析失败：{exc}")

        analysis = load_optional_table(period_output_path("report_analysis", period, ".xlsx"))
        show_status_cards(analysis)
        if not analysis.empty:
            sort_col = "verification_total_score" if "verification_total_score" in analysis.columns else None
            if sort_col:
                analysis = analysis.sort_values(sort_col, ascending=False, na_position="last")
            st.dataframe(analysis, use_container_width=True, height=560)

    with tab_export:
        st.subheader("文件导出")
        for label, path in [
            ("公告/PDF状态", period_output_path("report_manifest", period, ".xlsx")),
            ("文本分析结果", period_output_path("report_analysis", period, ".xlsx")),
        ]:
            if path.exists():
                st.download_button(
                    label=f"下载 {label}",
                    data=path.read_bytes(),
                    file_name=path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.info(f"{label} 尚未生成：{path}")


if __name__ == "__main__":
    main()

