import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- Настройка страницы ---
st.set_page_config(
    page_title="Финальный План/Факт Анализ v7.2", # Обновим версию
    page_icon="🏆",
    layout="wide"
)

st.title("🏆 Универсальный сервис для План/Факт анализа")
st.info(
    "**Как это работает:** 1. Загрузите файлы. 2. Проверьте качество данных. 3. Настройте формат и сопоставьте колонки. "
    "4. Запустите анализ. Результаты будут доступны ниже."
)


# --- Ключевые функции ---

@st.cache_data
def analyze_data_quality(df, file_name):
    """Анализирует качество данных в DataFrame (из Скрипта 1)."""
    quality_info = []
    total_rows = len(df)
    for col in df.columns:
        non_null_count = df[col].notna().sum()
        quality_info.append({
            'Файл': file_name,
            'Колонка': col,
            'Заполнено': non_null_count,
            'Пустые': total_rows - non_null_count,
            'Процент заполнения': f"{(non_null_count / total_rows * 100):.1f}%" if total_rows > 0 else "0.0%"
        })
    return pd.DataFrame(quality_info)

@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский (из Скрипта 1)."""
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    magazin_cols = sorted([col for col in plan_data_cols if col.startswith('Magazin')])
    stuki_cols = sorted([col for col in plan_data_cols if col.startswith('Plan_STUKI')])
    grn_cols = sorted([col for col in plan_data_cols if col.startswith('Plan_GRN')])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI' и 'Plan_GRN' не совпадает или равно нулю.")
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

    flat_df = pd.concat(flat_parts, ignore_index=True).dropna(subset=['магазин'])
    return flat_df

def calculate_metrics(df):
    """Расчет ключевых метрик для детального анализа (из Скрипта 2)."""
    metrics = {}
    metrics['total_plan_qty'] = df['Plan_STUKI'].sum()
    metrics['total_fact_qty'] = df['Fact_STUKI'].sum()
    metrics['total_plan_money'] = df['Plan_GRN'].sum()
    metrics['total_fact_money'] = df['Fact_GRN'].sum()
    metrics['qty_deviation'] = metrics['total_fact_qty'] - metrics['total_plan_qty']
    metrics['money_deviation'] = metrics['total_fact_money'] - metrics['total_plan_money']
    metrics['qty_completion'] = (metrics['total_fact_qty'] / metrics['total_plan_qty'] * 100) if metrics['total_plan_qty'] > 0 else 0
    metrics['money_completion'] = (metrics['total_fact_money'] / metrics['total_plan_money'] * 100) if metrics['total_plan_money'] > 0 else 0
    return metrics

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

# --- Шаг 1.1: Анализ качества данных (из Скрипта 1) ---
if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file)
    fact_df_original = pd.read_excel(fact_file)

    with st.expander("1.1 Анализ качества загруженных данных", expanded=True):
        plan_quality = analyze_data_quality(plan_df_original, "План")
        fact_quality = analyze_data_quality(fact_df_original, "Факт")
        quality_df = pd.concat([plan_quality, fact_quality], ignore_index=True)
        st.dataframe(quality_df, use_container_width=True)

    # --- Шаг 2: Настройка и обработка ---
    st.header("2. Настройка и обработка данных")

    plan_format = st.radio(
        "Выберите формат вашего файла 'План':",
        ('Плоский (стандартный)', 'Широкий (горизонтальный)'),
        horizontal=True, help="Широкий формат - когда данные по магазинам идут вправо по колонкам."
    )

    with st.form("processing_form"):
        plan_mappings, fact_mappings = {}, {}
        
        # --- Настройка сопоставления колонок (логика из обоих скриптов) ---
        col_map1, col_map2 = st.columns(2)

        with col_map1:
            st.subheader("Поля из файла 'План'")
            if plan_format == 'Широкий (горизонтальный)':
                all_plan_columns = plan_df_original.columns.tolist()
                id_vars = st.multiselect(
                    "Выберите все колонки, описывающие товар (НЕ для магазинов)",
                    options=all_plan_columns,
                    default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'brend', 'Segment'] if col in all_plan_columns],
                    help="Это колонки, которые останутся неизменными: артикул, описание, цена и т.д."
                )
            else: # Плоский формат
                PLAN_REQUIRED_FIELDS = {
                    'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
                    'Price': 'Цена', 'brend': 'Бренд', 'Segment': 'Сегмент',
                    'Plan_STUKI': 'Остатки-План (шт.)', 'Plan_GRN': 'Остатки в деньгах (план)'
                }
                plan_cols = [''] + plan_df_original.columns.tolist()
                for internal, display in PLAN_REQUIRED_FIELDS.items():
                    plan_mappings[internal] = st.selectbox(f'"{display}"', plan_cols, key=f'plan_{internal}')
        
        with col_map2:
            st.subheader("Поля из файла 'Факт'")
            FACT_REQUIRED_FIELDS = {
                'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
                'Fact_STUKI': 'Фактические остатки (шт.)'
            }
            fact_cols = [''] + fact_df_original.columns.tolist()
            for internal, display in FACT_REQUIRED_FIELDS.items():
                fact_mappings[internal] = st.selectbox(f'"{display}"', fact_cols, key=f'fact_{internal}')

        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            # --- Обработка файла План ---
            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars:
                    st.error("Для широкого формата необходимо выбрать идентификационные колонки товара.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
            else: # Плоский формат
                plan_rename_map = {v: k for k, v in plan_mappings.items() if v}
                if len(plan_rename_map) < len(PLAN_REQUIRED_FIELDS):
                     st.error("Не все обязательные поля для файла 'План' сопоставлены.")
                     st.stop()
                plan_df = plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)

            if plan_df is None:
                st.error("Не удалось обработать файл 'План'. Проверьте его структуру.")
                st.stop()

            # --- Обработка файла Факт ---
            fact_rename_map = {v: k for k, v in fact_mappings.items() if v}
            if len(fact_rename_map) < len(FACT_REQUIRED_FIELDS):
                st.error("Не все обязательные поля для файла 'Факт' сопоставлены.")
                st.stop()
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            # --- Слияние и финальные расчеты ---
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            for key in merge_keys:
                plan_df[key] = plan_df[key].astype(str).str.strip()
                if key in fact_df.columns:
                    fact_df[key] = fact_df[key].astype(str).str.strip()
            
            fact_cols_to_merge = [col for col in merge_keys + ['Fact_STUKI'] if col in fact_df.columns]
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

            # Заполнение пропусков и расчеты
            numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in numeric_columns:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)

            # Ключевые расчеты
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
            merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
            merged_df['Отклонение_%_шт'] = np.where(merged_df['Plan_STUKI'] != 0, (merged_df['Отклонение_шт'] / merged_df['Plan_STUKI']) * 100, np.inf)
            merged_df['Отклонение_%_грн'] = np.where(merged_df['Plan_GRN'] != 0, (merged_df['Отклонение_грн'] / merged_df['Plan_GRN']) * 100, np.inf)
            
            st.session_state.processed_df = merged_df
            st.success(f"✅ Данные успешно обработаны! Всего записей в итоговой таблице: {len(merged_df)}")

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"❌ Произошла ошибка при обработке: {e}")


# --- Блок Аналитики (отображается после успешной обработки) ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df

    # --- Шаг 3: Быстрый анализ отклонений (из Скрипта 2, улучшенный) ---
    st.header("3. Сводный анализ отклонений")

    # Агрегация по магазинам
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] != 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, np.inf)

    threshold = st.number_input("Показать магазины, где отклонение в штуках БОЛЬШЕ чем (%)", min_value=0, max_value=500, value=10, step=5)
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values('Отклонение_%_шт', ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    if not problem_stores_df.empty:
        st.dataframe(problem_stores_df.style.format({
            'Plan_STUKI': '{:,.0f}', 'Fact_STUKI': '{:,.0f}', 'Отклонение_шт': '{:,.0f}',
            'Plan_GRN': '{:,.2f}', 'Fact_GRN': '{:,.2f}',
            'Отклонение_%_шт': '{:.1f}%'
        }), use_container_width=True)
    else:
        st.info("Нет магазинов с отклонением больше заданного порога.")
    
    # --- Шаг 4: Детальный анализ (из Скрипта 2) ---
    st.sidebar.header("🔍 Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique())
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list

    if not stores_for_selection:
        st.sidebar.warning("Нет магазинов для выбора по заданным критериям.")
    else:
        selected_store = st.sidebar.selectbox("Выберите магазин для детального анализа:", options=stores_for_selection)

        if selected_store:
            st.markdown("---")
            st.header(f"4. 🏪 Детальный анализ магазина: '{selected_store}'")
            store_df = processed_df[processed_df['магазин'] == selected_store].copy()

            # Доп. фильтры в сайдбаре
            all_segments = sorted(store_df['Segment'].dropna().unique()) if 'Segment' in store_df.columns else []
            all_brands = sorted(store_df['brend'].dropna().unique()) if 'brend' in store_df.columns else []
            
            selected_segment = st.sidebar.selectbox("Выберите сегмент", options=['Все'] + all_segments)
            selected_brand = st.sidebar.selectbox("Выберите бренд", options=['Все'] + all_brands)
            
            # Применение фильтров
            filtered_df = store_df.copy()
            if selected_segment != 'Все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            # Расчет метрик и отображение
            metrics = calculate_metrics(filtered_df)
            st.subheader("📊 Ключевые показатели")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("План (шт.)", f"{int(metrics['total_plan_qty']):,}")
            c2.metric("Факт (шт.)", f"{int(metrics['total_fact_qty']):,}", delta=f"{int(metrics['qty_deviation']):+,}")
            c3.metric("План (грн.)", f"{metrics['total_plan_money']:,.0f}")
            c4.metric("Факт (грн.)", f"{metrics['total_fact_money']:,.0f}", delta=f"{metrics['money_deviation']:+,.0f}")
            
            # Таблица расхождений
            st.subheader("⚠️ Анализ расхождений по позициям")
            discrepancy_df = filtered_df[(filtered_df['Отклонение_шт'] != 0)].copy()

            if not discrepancy_df.empty:
                show_mode = st.radio("Показать:", ['Все расхождения', 'Только переостаток', 'Только недостаток'], horizontal=True)
                if show_mode == 'Только переостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
                elif show_mode == 'Только недостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
                else:
                    table_df = discrepancy_df
                
                sort_column = st.selectbox("Сортировать по:", ['Отклонение_шт', 'Отклонение_грн', 'Отклонение_%_шт'])
                table_df = table_df.sort_values(by=sort_column, ascending=False, key=abs)
                
                display_columns = ['ART', 'Describe', 'brend', 'Segment', 'Price', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт', 'Отклонение_грн']
                columns_to_show = [col for col in display_columns if col in table_df.columns]
                st.dataframe(table_df[columns_to_show], use_container_width=True, height=400)
                
                # <<< ИСПРАВЛЕНИЕ ЗДЕСЬ >>>
                # Декоратор @st.cache_data убран, так как он вызывал ошибку хеширования DataFrame
                def convert_df_to_excel(df):
                    return df.to_excel(index=False)
                
                excel_data = convert_df_to_excel(table_df[columns_to_show])
                st.download_button(
                    label="📥 Экспорт таблицы расхождений в Excel",
                    data=excel_data,
                    file_name=f"расхождения_{selected_store}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.success("🎉 Расхождений не обнаружено!")
            
            # Анализ по категориям (бренды/сегменты)
            if len(all_segments) > 1 or len(all_brands) > 1:
                st.subheader("📊 Сводный анализ по категориям")
                tab1, tab2 = st.tabs(["По сегментам", "По брендам"])
                with tab1:
                    if 'Segment' in store_df.columns and len(all_segments) > 1:
                        segment_analysis = store_df.groupby('Segment').agg(Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')).reset_index()
                        segment_analysis['Выполнение_%_грн'] = (segment_analysis['Fact_GRN'] / segment_analysis['Plan_GRN'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
                        fig = px.bar(segment_analysis, x='Segment', y='Выполнение_%_грн', title='Выполнение плана по сегментам (%)')
                        fig.add_hline(y=100, line_dash="dash", line_color="red")
                        st.plotly_chart(fig, use_container_width=True)
                with tab2:
                    if 'brend' in store_df.columns and len(all_brands) > 1:
                        brand_analysis = store_df.groupby('brend').agg(Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')).reset_index()
                        brand_analysis['Выполнение_%_грн'] = (brand_analysis['Fact_GRN'] / brand_analysis['Plan_GRN'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
                        brand_analysis = brand_analysis.nlargest(15, 'Plan_GRN')
                        fig = px.bar(brand_analysis, x='brend', y='Выполнение_%_грн', title='Выполнение плана по ТОП-15 брендам (%)')
                        fig.add_hline(y=100, line_dash="dash", line_color="red")
                        st.plotly_chart(fig, use_container_width=True)

# --- Футер ---
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666;'>🏆 Финальный План/Факт Анализ v7.2</div>", unsafe_allow_html=True)
