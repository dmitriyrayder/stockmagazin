import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ... (весь код до блока аналитики остается без изменений) ...

# --- ВСЯ АНАЛИТИКА НАХОДИТСЯ ВНУТРИ ЭТОГО БЛОКА ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df
    
    st.header("Анализ отклонений")
    
    # --- Общий анализ по магазинам ---
    st.subheader("Сводная таблица по магазинам")
    
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    
    # ИСПРАВЛЕНИЕ 1: Для сводной таблицы по магазинам
    store_summary['Отклонение_%_шт'] = np.where(
        store_summary['Plan_STUKI'] > 0, 
        abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, 
        np.where(store_summary['Отклонение_шт'] != 0, np.inf, 0)
    )
    
    threshold = st.number_input("Порог отклонения в штуках (%)", value=10, key="threshold_main")
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values('Отклонение_%_шт', ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    st.dataframe(problem_stores_df, use_container_width=True)

    # --- Детализация по сегментам ---
    if not problem_stores_df.empty:
        with st.expander("Показать детализацию по сегментам для проблемных магазинов"):
            
            problem_stores_list = problem_stores_df['магазин'].tolist()
            segment_detail_df = processed_df[processed_df['магазин'].isin(problem_stores_list)].copy()
            
            segment_summary = segment_detail_df.groupby(['магазин', 'Segment']).agg(
                Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
                Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
            ).reset_index()
            
            segment_summary['Отклонение_шт'] = segment_summary['Fact_STUKI'] - segment_summary['Plan_STUKI']
            
            # ИСПРАВЛЕНИЕ 2: Для детализации по сегментам (строка 159)
            segment_summary['Отклонение_%_шт'] = np.where(
                segment_summary['Plan_STUKI'] > 0, 
                (segment_summary['Отклонение_шт'] / segment_summary['Plan_STUKI']) * 100,
                np.where(segment_summary['Отклонение_шт'] != 0, np.inf, 0)
            )
            
            segment_summary['Абс_Отклонение_%_шт'] = abs(segment_summary['Отклонение_%_шт'])
            segment_summary = segment_summary.sort_values(['магазин', 'Абс_Отклонение_%_шт'], ascending=[True, False])

            # ... (остальной код для детализации и сайдбара без изменений) ...
            st.dataframe(
                segment_summary[['магазин', 'Segment', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт']],
                use_container_width=True,
                column_config={
                    "Отклонение_%_шт": st.column_config.ProgressColumn(
                        "Откл, %", format="%.1f%%", min_value=-150, max_value=150)
                },
                hide_index=True
            )
            
            st.subheader("Визуальный анализ отклонений по сегментам")
            chart_store = st.selectbox("Выберите магазин для визуализации:", options=problem_stores_list)
            
            if chart_store:
                chart_data = segment_summary[segment_summary['магазин'] == chart_store]
                fig = px.bar(chart_data, x='Segment', y='Отклонение_%_шт', color='Отклонение_%_шт',
                             color_continuous_scale='RdYlGn_r', title=f"Отклонение по сегментам в магазине '{chart_store}' (%)")
                fig.add_hline(y=0, line_dash="dash", line_color="black")
                st.plotly_chart(fig, use_container_width=True)

    # ... (остальной код для сайдбара без изменений) ...
