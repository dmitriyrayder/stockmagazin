import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- 1. НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(page_title="Анализ План/Факт v6.5", page_icon="🛠️", layout="wide")
st.title("🛠️ План/Факт Анализ с отладкой данных")

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    
    # Находим все колонки, которые не являются идентификаторами
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    
    # Находим базовые имена для повторяющихся колонок
    magazin_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Magazin'])
    stuki_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_STUKI'])
    grn_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_GRN'])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI' и 'Plan_GRN' не совпадает или равно нулю. Проверьте названия колонок в Excel.")
        return None
        
    flat_parts = []
    for i in range(len(magazin_cols)):
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
        part_df = _wide_df[current_cols].copy()
        
        part_df.rename(columns={
            magazin_cols[i]: 'магазин',
            stuki_cols[i]: 'Plan_STUKI',
            grn_cols[i]: 'Plan_GRN'
        }, inplace=True)
        
        flat_parts.append(part_df)
        
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True)
    return flat_df

# --- 3. ИНИЦИАЛИЗАЦИЯ SESSION STATE ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'plan_df_flat' not in st.session_state:
    st.session_state.plan_df_flat = None

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
        FACT_REQUIRED_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brand': 'Бренд', 'Fact_STUKI': 'Фактические остатки (шт.)'}
        for internal, display in FACT_REQUIRED_FIELDS.items():
            default_selection = next((col for col in fact_cols if display.lower() in col.lower()), None)
            default_index = fact_cols.index(default_selection) if default_selection else 0
            fact_mappings[internal] = st.selectbox(f'"{display}"', fact_cols, index=default_index, key=f'fact_{internal}')
            
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            st.session_state.processed_df = None
            st.session_state.plan_df_flat = None
            
            plan_df = None
            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars: 
                    st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
            else: # Плоский
                plan_df = plan_df_original.rename(columns={'Magazin': 'магазин', 'Brend': 'brand', 'Segment': 'Segment'})
                
            if plan_df is None or plan_df.empty: 
                st.error("Не удалось обработать файл 'План'. Проверьте структуру и выбор колонок.")
                st.stop()
            st.session_state.plan_df_flat = plan_df
            
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key] = plan_df[key].astype(str)
                    fact_df[key] = fact_df[key].astype(str)
            
            # ИСПРАВЛЕНИЕ 1: Проверяем наличие ключей перед мержем
            available_keys = [key for key in merge_keys if key in plan_df.columns and key in fact_df.columns]
            if not available_keys:
                st.error("Нет общих ключей для объединения данных. Проверьте соответствие колонок.")
                st.stop()
            
            fact_cols_to_merge = available_keys + ['Fact_STUKI']
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=available_keys, how='outer')

            # ИСПРАВЛЕНИЕ 2: Заполняем NaN ПЕРЕД преобразованием в numeric
            columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in columns_to_fill:
                if col in merged_df.columns:
                    # Сначала заполняем NaN нулями, потом преобразуем в numeric
                    merged_df[col] = merged_df[col].fillna(0)
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
            
            # ИСПРАВЛЕНИЕ 3: Пересчитываем Fact_GRN только если есть валидные данные
            if 'Price' in merged_df.columns and 'Fact_STUKI' in merged_df.columns:
                merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            else:
                merged_df['Fact_GRN'] = 0
                
            st.session_state.processed_df = merged_df
            st.success("Данные успешно обработаны!")

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"Произошла ошибка при обработке: {e}")

# --- 5. БЛОК ОТЛАДКИ (появляется после обработки) ---
if st.session_state.plan_df_flat is not None:
    with st.expander("🔍 Показать результат преобразования файла 'План' (для отладки)"):
        st.info("Проверьте эту таблицу. Если в колонках `Plan_STUKI` и `Plan_GRN` здесь уже стоят нули, значит проблема в структуре вашего исходного файла или в выборе идентификационных колонок.")
        st.dataframe(st.session_state.plan_df_flat)

# --- 6. АНАЛИТИЧЕСКИЙ БЛОК ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df
    
    st.header("Анализ отклонений")
    st.subheader("Сводная таблица по магазинам")
    
    # ИСПРАВЛЕНИЕ 4: Проверяем наличие колонок перед группировкой
    required_cols = ['магазин', 'Plan_STUKI', 'Fact_STUKI', 'Plan_GRN']
    missing_cols = [col for col in required_cols if col not in processed_df.columns]
    
    if missing_cols:
        st.error(f"Отсутствуют необходимые колонки: {missing_cols}")
        st.stop()
    
    # ИСПРАВЛЕНИЕ 5: Добавляем отладочную информацию перед группировкой
    with st.expander("🔍 Показать объединенные данные (для отладки)"):
        st.write("Первые 10 строк объединенной таблицы:")
        st.dataframe(processed_df.head(10))
        st.write("Сводка по числовым колонкам:")
        numeric_cols = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Fact_GRN']
        available_numeric = [col for col in numeric_cols if col in processed_df.columns]
        if available_numeric:
            st.dataframe(processed_df[available_numeric].describe())
    
    # Группировка с проверкой на наличие данных
    groupby_cols = {'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum'}
    if 'Plan_GRN' in processed_df.columns:
        groupby_cols['Plan_GRN'] = 'sum'
    if 'Fact_GRN' in processed_df.columns:
        groupby_cols['Fact_GRN'] = 'sum'
    
    store_summary = processed_df.groupby('магазин').agg(groupby_cols).reset_index()
    
    # ИСПРАВЛЕНИЕ 6: Улучшенная диагностика проблем с данными
    plan_stuki_sum = store_summary['Plan_STUKI'].sum() if 'Plan_STUKI' in store_summary.columns else 0
    plan_grn_sum = store_summary['Plan_GRN'].sum() if 'Plan_GRN' in store_summary.columns else 0
    
    if plan_stuki_sum == 0 and plan_grn_sum == 0:
        st.warning("⚠️ Внимание: Суммы по плану равны нулю!")
        st.info("Возможные причины:\n- Некорректное сопоставление колонок\n- Проблемы с форматом данных в исходном файле\n- Неправильный выбор идентификационных колонок для широкого формата")
    
    # Расчет отклонений
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(
        store_summary['Plan_STUKI'] > 0, 
        abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, 
        np.where(store_summary['Отклонение_шт'] != 0, np.inf, 0)
    )
    
    # Добавляем отклонения по сумме, если есть данные
    if 'Plan_GRN' in store_summary.columns and 'Fact_GRN' in store_summary.columns:
        store_summary['Отклонение_сумма'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
        store_summary['Отклонение_%_сумма'] = np.where(
            store_summary['Plan_GRN'] > 0, 
            abs(store_summary['Отклонение_сумма']) / store_summary['Plan_GRN'] * 100, 
            np.where(store_summary['Отклонение_сумма'] != 0, np.inf, 0)
        )
    
    threshold = st.number_input("Порог отклонения в штуках (%)", value=10, key="threshold_main")
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values('Отклонение_%_шт', ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    st.dataframe(problem_stores_df, use_container_width=True)

    # Дополнительная аналитика
    if not problem_stores_df.empty:
        with st.expander("📊 Детализация по сегментам"):
            if 'Segment' in processed_df.columns:
                segment_analysis = processed_df.groupby(['магазин', 'Segment']).agg(groupby_cols).reset_index()
                st.dataframe(segment_analysis)
            else:
                st.info("Колонка 'Segment' не найдена в данных")
    
    # Сайдбар с дополнительной информацией
    with st.sidebar:
        st.header("📈 Общая статистика")
        st.metric("Всего магазинов", len(store_summary))
        st.metric("Проблемных магазинов", len(problem_stores_df))
        
        if plan_stuki_sum > 0:
            st.metric("Общий план (шт.)", f"{plan_stuki_sum:,.0f}")
            st.metric("Общий факт (шт.)", f"{store_summary['Fact_STUKI'].sum():,.0f}")
        
        if plan_grn_sum > 0:
            st.metric("Общий план (сумма)", f"{plan_grn_sum:,.0f}")
            st.metric("Общий факт (сумма)", f"{store_summary['Fact_GRN'].sum():,.0f}")
