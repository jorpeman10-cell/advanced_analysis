"""
统一导出管理模块
支持所有标签页的 PDF/Excel 导出
"""

import pandas as pd
from io import BytesIO
from datetime import datetime
from typing import Dict, List, Optional
import streamlit as st


class ExportManager:
    """统一导出管理器"""
    
    @staticmethod
    def to_excel(data_dict: Dict[str, pd.DataFrame], filename: str = None) -> bytes:
        """
        导出多个 DataFrame 到一个 Excel 文件（多 Sheet）
        
        Args:
            data_dict: {sheet_name: DataFrame}
            filename: 文件名（可选）
        
        Returns:
            Excel 文件字节流
        """
        if filename is None:
            filename = f"TSTAR_Export_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name, df in data_dict.items():
                # 限制 sheet 名长度
                safe_name = str(sheet_name)[:31]
                df.to_excel(writer, sheet_name=safe_name, index=False)
        
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    def to_csv(df: pd.DataFrame, filename: str = None) -> bytes:
        """导出单个 DataFrame 为 CSV"""
        if filename is None:
            filename = f"TSTAR_Export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    def render_export_buttons(data_dict: Dict[str, pd.DataFrame], 
                              key_prefix: str = "export",
                              show_csv: bool = True,
                              show_excel: bool = True):
        """
        渲染导出按钮组
        
        Args:
            data_dict: {sheet_name: DataFrame}
            key_prefix: Streamlit widget key 前缀
            show_csv: 是否显示 CSV 导出
            show_excel: 是否显示 Excel 导出
        """
        cols = st.columns([1, 1, 4])
        
        with cols[0]:
            if show_excel and st.button("📥 Excel", key=f"{key_prefix}_excel"):
                excel_data = ExportManager.to_excel(data_dict)
                st.download_button(
                    label="下载 Excel",
                    data=excel_data,
                    file_name=f"TSTAR_{key_prefix}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{key_prefix}_excel_dl"
                )
        
        with cols[1]:
            if show_csv and len(data_dict) == 1:
                df = list(data_dict.values())[0]
                if st.button("📄 CSV", key=f"{key_prefix}_csv"):
                    csv_data = ExportManager.to_csv(df)
                    st.download_button(
                        label="下载 CSV",
                        data=csv_data,
                        file_name=f"TSTAR_{key_prefix}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key=f"{key_prefix}_csv_dl"
                    )
    
    @staticmethod
    def prepare_consultant_export(consultant_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """准备顾问分析导出数据"""
        return {
            '顾问明细': consultant_df,
        }
    
    @staticmethod
    def prepare_mapping_export(org_df: pd.DataFrame, 
                                creator_df: pd.DataFrame,
                                cat_df: pd.DataFrame,
                                lowq_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """准备 Mapping 分析导出数据"""
        return {
            'Mapping清单': org_df,
            '录入人排名': creator_df,
            '节点分布': cat_df,
            '待整改清单': lowq_df,
        }
    
    @staticmethod
    def prepare_gap_export(gap_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """准备产能差距分析导出数据"""
        return {
            '产能差距分析': gap_df,
        }


def render_export_section(data_dict: Dict[str, pd.DataFrame], 
                          title: str = "导出数据",
                          key_prefix: str = "export"):
    """
    渲染统一的导出区域（带标题和按钮）
    """
    with st.expander(f"📥 {title}", expanded=False):
        st.markdown("将当前数据导出为 Excel 文件：")
        
        # 显示数据预览
        for sheet_name, df in data_dict.items():
            st.markdown(f"**{sheet_name}**: {len(df)} 行 × {len(df.columns)} 列")
        
        # 导出按钮
        if st.button("生成 Excel 文件", key=f"{key_prefix}_btn", type="primary"):
            excel_data = ExportManager.to_excel(data_dict)
            st.download_button(
                label="⬇️ 下载 Excel",
                data=excel_data,
                file_name=f"TSTAR_{key_prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{key_prefix}_dl",
                use_container_width=True
            )
