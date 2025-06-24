import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Анализ План/Факт v6.4", page_icon="🛠️", layout="wide")
st.title("🛠️ План/Факт Анализ с отладкой данных")

# ... (функция transform_wide_to_flat остается без изменений) ...
@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    # ...

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'plan_df_flat' not in st.session_state:
    st.session_state.plan_df_flat = None


# --- Блок загрузки и настройки ---
# ... (опускаю для краткости, он не менялся)

# --- После нажатия кнопки "Обработать" ---
if submitted:
    try:
        # Сбрасываем старые результаты
        st.session_state.processed_df = None
        st.session_state.plan_df_flat = None
        
        # --- Обработка файла План ---
        if plan_format == 'Широкий (горизонтальный)':
            if not id_vars:
                st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                st.stop()
            plan_df = transform_wide_to_flat(plan_df_original, id_vars)
        else: # Плоский
            plan_df = plan_df_original.rename(columns={'Magazin': 'магазин', 'Brend': 'brand', 'Segment': 'Segment'})
            
        if plan_df is None or plan_df.empty:
            st.error("Не удалось обработать файл 'План' или результат оказался пустым. Проверьте структуру файла и выбор колонок.")
            st.stop()
        
        # Сохраняем результат трансформации для отладки
        st.session_state.plan_df_flat = plan_df
        
        # --- Обработка файла Факт ---
        fact_rename_map = {v: k for k, v in fact_mappings.items()}
        fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

        # --- Слияние и финальные расчеты ---
        merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
        for key in merge_keys:
            if key in plan_df.columns and key in fact_df.columns:
                plan_df[key] = plan_df[key].astype(str)
                fact_df[key] = fact_df[key].astype(str)
        
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

# --- НОВЫЙ БЛОК: Отладка преобразования Плана ---
if st.session_state.plan_df_flat is not None:
    with st.expander("🔍 Показать результат преобразования файла 'План' (для отладки)"):
        st.info(
            "Проверьте эту таблицу. Если в колонках `Plan_STUKI` и `Plan_GRN` здесь уже стоят нули, "
            "значит проблема в структуре вашего исходного файла или в выборе идентификационных колонок на шаге 2."
        )
        st.dataframe(st.session_state.plan_df_flat)


# --- Аналитический блок ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df
    
    st.header("Анализ отклонений")
    st.subheader("Сводная таблица по магазинам")
    
    # Расчеты теперь должны работать, так как мы можем проверить plan_df_flat
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'),
        Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'),
        Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()

    # Проверка после агрегации
    if store_summary['Plan_STUKI'].sum() == 0 and store_summary['Plan_GRN'].sum() == 0:
        st.warning(
            "Внимание: Суммы по плану равны нулю. Это подтверждает, что плановые данные не были корректно считаны. "
            "Пожалуйста, проверьте отладочную таблицу выше."
        )

    # ... (остальной код анализа без изменений) ...
