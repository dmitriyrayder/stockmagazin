import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Универсальный План/Факт Анализ v5.1",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Универсальный сервис для План/Факт анализа")
st.info(
    "**Как это работает:** 1. Загрузите файлы. 2. Сопоставьте колонки. "
    "3. Нажмите 'Применить и обработать'. Анализ появится ниже и будет обновляться при смене фильтров."
)

# --- Инициализация Session State ---
if 'plan_df_original' not in st.session_state:
    st.session_state.plan_df_original = None
if 'fact_df_original' not in st.session_state:
    st.session_state.fact_df_original = None
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'mappings' not in st.session_state:
    st.session_state.mappings = {}

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

if plan_file:
    st.session_state.plan_df_original = pd.read_excel(plan_file)
if fact_file:
    st.session_state.fact_df_original = pd.read_excel(fact_file)

# --- Шаг 2: Сопоставление колонок (появляется после загрузки) ---
if st.session_state.plan_df_original is not None and st.session_state.fact_df_original is not None:
    
    with st.form("mapping_form"):
        st.header("2. Сопоставление колонок")
        
        PLAN_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
            'Price': 'Цена', 'brend': 'Бренд', 'Segment': 'Сегмент',
            'Plan_STUKI': 'Остатки-План (шт.)', 'Plan_GRN': 'Остатки в деньгах (план)'
        }
        FACT_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
            'Fact_STUKI': 'Фактические остатки (шт.)'
        }

        plan_cols = st.session_state.plan_df_original.columns.tolist()
        fact_cols = st.session_state.fact_df_original.columns.tolist()

        col_map1, col_map2 = st.columns(2)
        plan_mappings = {}
        fact_mappings = {}

        with col_map1:
            st.subheader("Поля из файла 'План'")
            for internal_name, display_name in PLAN_REQUIRED_FIELDS.items():
                plan_mappings[internal_name] = st.selectbox(
                    f'"{display_name}"', plan_cols, key=f'plan_select_{internal_name}'
                )

        with col_map2:
            st.subheader("Поля из файла 'Факт'")
            for internal_name, display_name in FACT_REQUIRED_FIELDS.items():
                fact_mappings[internal_name] = st.selectbox(
                    f'"{display_name}"', fact_cols, key=f'fact_select_{internal_name}'
                )
        
        # Кнопка теперь внутри формы
        submitted = st.form_submit_button("🚀 Применить и обработать данные", type="primary")

    # --- Шаг 3: Обработка данных (выполняется только при отправке формы) ---
    if submitted:
        try:
            plan_rename_map = {v: k for k, v in plan_mappings.items()}
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            
            if len(plan_rename_map) != len(PLAN_REQUIRED_FIELDS) or len(fact_rename_map) != len(FACT_REQUIRED_FIELDS):
                 st.error("Ошибка: Одна и та же колонка выбрана для нескольких полей. Проверьте сопоставление.")
                 st.stop()
            
            plan_df_renamed = st.session_state.plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)
            fact_df_renamed = st.session_state.fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)
            
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            plan_df_renamed.dropna(subset=merge_keys, inplace=True)
            fact_df_renamed.dropna(subset=merge_keys, inplace=True)
            
            merged_df = pd.merge(plan_df_renamed, fact_df_renamed, on=merge_keys, how='outer')

            columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in columns_to_fill:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
            
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            
            st.session_state.processed_df = merged_df
            st.success("Данные успешно обработаны! Анализ доступен ниже и будет обновляться при смене фильтров.")
        
        except Exception as e:
            st.session_state.processed_df = None # Сбрасываем результат в случае ошибки
            st.error(f"Ошибка при обработке данных: {e}")
            st.warning("Убедитесь, что вы правильно сопоставили числовые колонки (Цена, Остатки) и текстовые.")


# --- Шаг 4: АНАЛИЗ (ЭТОТ БЛОК ТЕПЕРЬ СНАРУЖИ И ЗАВИСИТ ТОЛЬКО ОТ НАЛИЧИЯ ДАННЫХ В СЕССИИ) ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df

    # --- Быстрый анализ по всем магазинам ---
    st.header("3. Быстрый анализ отклонений по магазинам")
    
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(
        store_summary['Plan_STUKI'] > 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100,
        np.where(store_summary['Отклонение_шт'] != 0, np.inf, 0))
    
    threshold = st.number_input("Показать магазины, где отклонение в штуках БОЛЬШЕ чем (%)", 
                                min_value=0, max_value=500, value=10, step=5)
    
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].copy()
    problem_stores_df = problem_stores_df.sort_values(by='Отклонение_%_шт', ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    display_summary_df = problem_stores_df.rename(columns={
            'магазин': 'Магазин', 'Plan_STUKI': 'План, шт.', 'Fact_STUKI': 'Факт, шт.',
            'Отклонение_шт': 'Расхождение, шт.', 'Отклонение_%_шт': 'Расхождение, %',
            'Plan_GRN': 'План, Грн.', 'Fact_GRN': 'Факт, Грн.'
        })
    st.dataframe(display_summary_df[['Магазин', 'План, шт.', 'Факт, шт.', 'Расхождение, шт.', 'Расхождение, %', 'План, Грн.', 'Факт, Грн.']]
                 .style.format({'План, шт.': '{:,.0f}', 'Факт, шт.': '{:,.0f}', 'Расхождение, шт.': '{:,.0f}',
                                'Расхождение, %': '{:.1f}%', 'План, Грн.': '{:,.2f}', 'Факт, Грн.': '{:,.2f}'}),
                 use_container_width=True)

    # --- Детальный анализ выбранного магазина ---
    st.sidebar.header("Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique())
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list
    
    if not stores_for_selection:
        st.sidebar.warning("Нет магазинов для выбора по заданным критериям.")
    else:
        selected_store = st.sidebar.selectbox("Шаг 1: Выберите магазин", options=stores_for_selection)
        
        # Остальная часть аналитики, которая зависит от выбранного магазина
        if selected_store:
            # Весь код для детального анализа, графиков и таблиц
            # ...
            st.header(f"4. Детальный анализ магазина: '{selected_store}'")
            # ... и так далее, как было в предыдущих версиях.
