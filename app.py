import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- 1. НАСТРОЙКА СТРАНИЦЫ И ЗАГОЛОВОК ---
st.set_page_config(page_title="Анализ по Сегментам v6.3", page_icon="🎯", layout="wide")
st.title("🎯 План/Факт Анализ с детализацией по Сегментам")

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    magazin_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Magazin'])
    stuki_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_STUKI'])
    grn_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_GRN'])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI', 'Plan_GRN' не совпадает или равно нулю.")
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

# --- 3. ИНИЦИАЛИЗАЦИЯ SESSION STATE (КЛЮЧЕВОЙ МОМЕНТ) ---
# Этот блок должен быть наверху, чтобы ключи были созданы ДО их использования
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- 4. БЛОК ЗАГРУЗКИ И ОБРАБОТКИ ---
st.header("1. Загрузка и настройка")

col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"])
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"])

if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file)
    fact_df_original = pd.read_excel(fact_file)

    plan_format = st.radio(
        "Выберите формат вашего файла 'План':",
        ('Плоский (стандартный)', 'Широкий (горизонтальный)'),
        horizontal=True
    )

    with st.form("processing_form"):
        if plan_format == 'Широкий (горизонтальный)':
            st.subheader("Настройка для широкого файла 'План'")
            all_plan_columns = plan_df_original.columns.tolist()
            id_vars = st.multiselect(
                "Выберите все колонки, описывающие товар (НЕ относящиеся к магазинам)",
                options=all_plan_columns,
                default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment'] if col in all_plan_columns]
            )
        
        st.subheader("Сопоставление для файла 'Факт'")
        fact_mappings = {}
        fact_cols = fact_df_original.columns.tolist()
        FACT_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
            'brand': 'Бренд', 'Fact_STUKI': 'Фактические остатки (шт.)'
        }
        for internal, display in FACT_REQUIRED_FIELDS.items():
            default_selection = next((col for col in fact_cols if display.lower() in col.lower()), None)
            default_index = fact_cols.index(default_selection) if default_selection else 0
            fact_mappings[internal] = st.selectbox(f'"{display}"', fact_cols, index=default_index, key=f'fact_{internal}')
            
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            # Очищаем старые данные перед новой обработкой
            st.session_state.processed_df = None

            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars:
                    st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
            else: # Плоский
                plan_df = plan_df_original.rename(columns={'Magazin': 'магазин', 'Brend': 'brand', 'Segment': 'Segment'})
                
            if plan_df is None: st.stop()
            
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key] = plan_df[key].astype(str)
                    fact_df[key] = fact_df[key].astype(str)
            
            # Убедимся, что все нужные колонки существуют перед слиянием
            fact_cols_to_merge = [key for key in merge_keys if key in fact_df.columns] + ['Fact_STUKI']
            
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

            columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in columns_to_fill:
                 if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
            
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']

            st.session_state.processed_df = merged_df
            st.success("Данные успешно обработаны!")

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"Произошла ошибка при обработке: {e}")

# --- 5. АНАЛИТИЧЕСКИЙ БЛОК ---
# Этот блок выполняется только если в session_state есть обработанные данные
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
            
            segment_summary['Отклонение_%_шт'] = np.where(
                segment_summary['Plan_STUKI'] > 0, 
                (segment_summary['Отклонение_шт'] / segment_summary['Plan_STUKI']) * 100,
                np.where(segment_summary['Отклонение_шт'] != 0, np.inf, 0)
            )
            
            segment_summary['Абс_Отклонение_%_шт'] = abs(segment_summary['Отклонение_%_шт'])
            segment_summary = segment_summary.sort_values(['магазин', 'Абс_Отклонение_%_шт'], ascending=[True, False])

            st.dataframe(
                segment_summary[['магазин', 'Segment', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт']],
                use_container_width=True,
                column_config={"Отклонение_%_шт": st.column_config.ProgressColumn(
                        "Откл, %", format="%.1f%%", min_value=-150, max_value=150)},
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

    # --- Детальный анализ в сайдбаре ---
    st.sidebar.header("🔍 Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    
    problem_stores_sidebar_list = problem_stores_df['магазин'].unique().tolist() if not problem_stores_df.empty else []
    
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_sidebar_list if analysis_scope == 'Только проблемные' and problem_stores_sidebar_list else all_stores_list
    
    if stores_for_selection:
        selected_store = st.sidebar.selectbox("Выберите магазин:", options=stores_for_selection)
        if selected_store:
            st.header(f"Детальный анализ магазина: '{selected_store}'")
            # Сюда можно вставить полный блок детального анализа из предыдущих версий
            st.info(f"Здесь будет отображена полная аналитика для магазина {selected_store}.")
            st.dataframe(processed_df[processed_df['магазин'] == selected_store])
    else:
        st.sidebar.warning("Нет магазинов для выбора.")
