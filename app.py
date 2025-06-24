import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Анализ по Сегментам v6.1", page_icon="🎯", layout="wide")

st.title("🎯 План/Факт Анализ с детализацией по Сегментам")

# --- Функция для преобразования широкого формата ---
@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    # ... (эта функция остается без изменений)
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    magazin_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Magazin'])
    stuki_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_STUKI'])
    grn_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_GRN'])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols)):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI' и 'Plan_GRN' не совпадает.")
        return None
        
    flat_parts = []
    for i in range(len(magazin_cols)):
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
        part_df = _wide_df[current_cols].copy()
        part_df.rename(columns={magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI', grn_cols[i]: 'Plan_GRN'}, inplace=True)
        flat_parts.append(part_df)
        
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True)
    return flat_df

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- Шаг 1: Загрузка файлов и Шаг 2: Настройка (код без изменений) ---
# ... (опускаю для краткости, он идентичен предыдущей версии)

# --- Аналитика (отображается после успешной обработки) ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df
    
    st.header("3. Быстрый анализ отклонений")
    st.info("Здесь можно найти магазины с наибольшим расхождением, а также посмотреть детализацию по сегментам внутри каждого проблемного магазина.")

    # --- Общий анализ по магазинам ---
    st.subheader("Сводная таблица по магазинам")
    
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] > 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, np.inf)
    
    threshold = st.number_input("Порог отклонения в штуках (%)", value=10, key="threshold_main")
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values('Отклонение_%_шт', ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    st.dataframe(problem_stores_df, use_container_width=True)

    # --- НОВЫЙ БЛОК: Детализация по сегментам ---
    if not problem_stores_df.empty:
        with st.expander("Показать детализацию по сегментам для проблемных магазинов", expanded=False):
            
            # Получаем список только проблемных магазинов для фильтрации
            problem_stores_list = problem_stores_df['магазин'].tolist()
            
            # Фильтруем основной датафрейм, чтобы оставить только данные по этим магазинам
            segment_detail_df = processed_df[processed_df['магазин'].isin(problem_stores_list)].copy()
            
            # Агрегируем данные по магазину и сегменту
            segment_summary = segment_detail_df.groupby(['магазин', 'Segment']).agg(
                Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
                Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
            ).reset_index()
            
            # Рассчитываем отклонения для сегментов
            segment_summary['Отклонение_шт'] = segment_summary['Fact_STUKI'] - segment_summary['Plan_STUKI']
            segment_summary['Отклонение_%_шт'] = np.where(segment_summary['Plan_STUKI'] > 0, (segment_summary['Отклонение_шт'] / segment_summary['Plan_STUKI']) * 100, np.inf)

            # Опциональная сортировка для наглядности
            segment_summary['Абс_Отклонение_%_шт'] = abs(segment_summary['Отклонение_%_шт'])
            segment_summary = segment_summary.sort_values(['магазин', 'Абс_Отклонение_%_шт'], ascending=[True, False])

            # Для более красивого вывода, можно использовать st.dataframe с форматированием
            st.dataframe(
                segment_summary[['магазин', 'Segment', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт']],
                use_container_width=True,
                column_config={
                    "магазин": st.column_config.TextColumn("Магазин"),
                    "Segment": st.column_config.TextColumn("Сегмент"),
                    "Plan_STUKI": st.column_config.NumberColumn("План, шт.", format="%d"),
                    "Fact_STUKI": st.column_config.NumberColumn("Факт, шт.", format="%d"),
                    "Отклонение_шт": st.column_config.NumberColumn("Откл, шт.", format="%d"),
                    "Отклонение_%_шт": st.column_config.ProgressColumn(
                        "Откл, %",
                        help="Процент отклонения факта от плана. Зеленый - излишек, красный - недостача.",
                        format="%.1f%%",
                        min_value=-200,  # Установите разумные пределы для Progress Bar
                        max_value=200,
                    ),
                },
                hide_index=True
            )
            
            # --- Визуализация для анализа по сегментам ---
            st.subheader("Визуальный анализ отклонений по сегментам")

            # Даем пользователю выбрать магазин для графика
            chart_store = st.selectbox(
                "Выберите магазин для визуализации:",
                options=problem_stores_list,
                key="segment_chart_store"
            )
            
            if chart_store:
                chart_data = segment_summary[segment_summary['магазин'] == chart_store]
                
                fig = px.bar(
                    chart_data,
                    x='Segment',
                    y='Отклонение_%_шт',
                    color='Отклонение_%_шт',
                    color_continuous_scale='RdYlGn_r', # Красный-Желтый-Зеленый (перевернутый)
                    title=f"Отклонение План/Факт по сегментам в магазине '{chart_store}' (%)"
                )
                fig.update_layout(
                    coloraxis_colorbar=dict(title="Откл, %"),
                    yaxis_title="Отклонение от плана (%)"
                )
                fig.add_hline(y=0, line_width=2, line_dash="dash", line_color="black") # Линия нуля
                st.plotly_chart(fig, use_container_width=True)

    # --- Детальный анализ (в сайдбаре) ---
    st.sidebar.header("🔍 Детальный анализ")
    # ... (здесь идет блок детального анализа, он не меняется)
    # ...
