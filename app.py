import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="План/Факт Анализ v6.0", page_icon="🏆", layout="wide")
st.title("🏆 Универсальный сервис для План/Факт анализа")

# --- Вспомогательные функции ---
@st.cache_data
def analyze_data_quality(df, file_name):
    """Анализирует качество данных в DataFrame."""
    quality_info = []
    for col in df.columns:
        total_rows = len(df)
        non_null_count = df[col].notna().sum()
        null_count = df[col].isna().sum()
        
        valid_numeric = pd.to_numeric(df[col], errors='coerce').notna().sum() if df[col].dtype in ['int64', 'float64'] else 'N/A'
        quality_info.append({
            'Файл': file_name, 'Колонка': col, 'Общее количество': total_rows,
            'Заполнено': non_null_count, 'Пустые': null_count,
            'Валидные числа': valid_numeric, 'Процент заполнения': f"{(non_null_count/total_rows*100):.1f}%"
        })
    return pd.DataFrame(quality_info)

@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    
    magazin_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Magazin'])
    stuki_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_STUKI'])
    grn_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_GRN'])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols)):
        st.error("Ошибка структуры файла Плана: Количество колонок не совпадает.")
        return None
        
    flat_parts = []
    for i in range(len(magazin_cols)):
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
        part_df = _wide_df[current_cols].copy()
        
        part_df.rename(columns={
            magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI', grn_cols[i]: 'Plan_GRN'
        }, inplace=True)
        flat_parts.append(part_df)
        
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True)
    return flat_df

def calculate_metrics(df):
    """Рассчитывает основные метрики для данных."""
    total_plan_qty = df['Plan_STUKI'].sum()
    total_fact_qty = df['Fact_STUKI'].sum()
    total_plan_money = df['Plan_GRN'].sum()
    total_fact_money = df['Fact_GRN'].sum()
    
    return {
        'total_plan_qty': total_plan_qty, 'total_fact_qty': total_fact_qty,
        'total_plan_money': total_plan_money, 'total_fact_money': total_fact_money,
        'qty_deviation': total_fact_qty - total_plan_qty, 'money_deviation': total_fact_money - total_plan_money,
        'qty_completion': (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0,
        'money_completion': (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0
    }

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

# --- Анализ качества данных ---
if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file)
    fact_df_original = pd.read_excel(fact_file)
    
    st.header("1.1. Анализ качества загруженных данных")
    
    plan_quality = analyze_data_quality(plan_df_original, "План")
    fact_quality = analyze_data_quality(fact_df_original, "Факт")
    quality_df = pd.concat([plan_quality, fact_quality], ignore_index=True)
    
    st.subheader("📊 Статистика по колонкам")
    st.dataframe(quality_df, use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Колонок в файле План", len(plan_df_original.columns))
        st.metric("Строк в файле План", len(plan_df_original))
    with col2:
        st.metric("Колонок в файле Факт", len(fact_df_original.columns))
        st.metric("Строк в файле Факт", len(fact_df_original))

    st.header("2. Настройка и обработка данных")
    
    plan_format = st.radio(
        "Выберите формат вашего файла 'План':",
        ('Плоский (стандартный)', 'Широкий (горизонтальный)'), horizontal=True,
        help="Широкий формат - когда данные по магазинам идут вправо по колонкам."
    )

    with st.form("processing_form"):
        id_vars = []
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
            'brend': 'Бренд', 'Fact_STUKI': 'Фактические остатки (шт.)'
        }
        for internal, display in FACT_REQUIRED_FIELDS.items():
            fact_mappings[internal] = st.selectbox(f'"{display}"', fact_cols, key=f'fact_{internal}')
        
        col1, col2 = st.columns(2)
        with col1:
            remove_duplicates = st.checkbox("Удалить дубликаты", value=True)
        with col2:
            fill_zeros = st.checkbox("Заполнить пропуски нулями", value=True)
            
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            # Обработка файла План
            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars:
                    st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
            else:
                plan_df = plan_df_original.rename(columns={'Magazin': 'магазин'})
                
            if plan_df is None:
                st.error("Не удалось обработать файл 'План'.")
                st.stop()
            
            # Обработка файла Факт
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            # Удаление дубликатов
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            if remove_duplicates:
                plan_df = plan_df.drop_duplicates(subset=merge_keys)
                fact_df = fact_df.drop_duplicates(subset=merge_keys)
            
            # Приведение типов для слияния
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key] = plan_df[key].astype(str)
                    fact_df[key] = fact_df[key].astype(str)

            # Слияние данных
            fact_cols_to_merge = merge_keys + ['Fact_STUKI']
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

            # Обработка числовых колонок
            numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in numeric_columns:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
                    if fill_zeros:
                        merged_df[col] = merged_df[col].fillna(0)
            
            # Расчеты
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
            merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
            merged_df['Отклонение_%_шт'] = np.where(
                merged_df['Plan_STUKI'] > 0, 
                merged_df['Отклонение_шт'] / merged_df['Plan_STUKI'] * 100, 
                np.where(merged_df['Отклонение_шт'] != 0, np.inf, 0)
            )
            merged_df['Отклонение_%_грн'] = np.where(
                merged_df['Plan_GRN'] > 0, 
                merged_df['Отклонение_грн'] / merged_df['Plan_GRN'] * 100, 
                np.where(merged_df['Отклонение_грн'] != 0, np.inf, 0)
            )
            
            st.session_state.processed_df = merged_df
            st.success("✅ Данные успешно обработаны!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Записей в плане", len(plan_df))
            with col2:
                st.metric("Записей в факте", len(fact_df))
            with col3:
                st.metric("Записей после объединения", len(merged_df))

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"❌ Ошибка при обработке данных: {e}")

# --- Аналитика ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df

    st.header("3. Быстрый анализ отклонений по магазинам")
    
    # Агрегация по магазинам
    store_summary = processed_df.groupby('магазин').agg({
        'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum', 'Plan_GRN': 'sum', 'Fact_GRN': 'sum'
    }).reset_index()
    
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_грн'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
    store_summary['Отклонение_%_шт'] = np.where(
        store_summary['Plan_STUKI'] > 0, 
        abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100,
        np.where(store_summary['Отклонение_шт'] != 0, np.inf, 0)
    )
    store_summary['Отклонение_%_грн'] = np.where(
        store_summary['Plan_GRN'] > 0, 
        abs(store_summary['Отклонение_грн']) / store_summary['Plan_GRN'] * 100,
        np.where(store_summary['Отклонение_грн'] != 0, np.inf, 0)
    )
    
    # Настройки фильтрации
    col1, col2 = st.columns(2)
    with col1:
        threshold = st.number_input("Показать магазины, где отклонение в штуках БОЛЬШЕ чем (%)", min_value=0, max_value=500, value=10, step=5)
    with col2:
        sort_by = st.selectbox("Сортировать по", ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'])
    
    # Фильтрация проблемных магазинов
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].copy().sort_values(by=sort_by, ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    
    if not problem_stores_df.empty:
        # Форматирование таблицы
        display_df = problem_stores_df.copy()
        for col in ['Plan_STUKI', 'Fact_STUKI']:
            display_df[col] = display_df[col].astype(int)
        for col in ['Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
            display_df[col] = display_df[col].round(2)
        for col in ['Отклонение_%_шт', 'Отклонение_%_грн']:
            display_df[col] = display_df[col].round(1)
        
        st.dataframe(display_df, use_container_width=True)
        
        # Графики
        st.subheader("Визуализация отклонений")
        tab1, tab2 = st.tabs(["📊 По количеству", "💰 По деньгам"])
        
        with tab1:
            fig_qty = px.bar(problem_stores_df.head(10), x='магазин', y='Отклонение_%_шт',
                           title='ТОП-10 магазинов по отклонению в штуках (%)',
                           color='Отклонение_%_шт', color_continuous_scale='RdYlBu_r')
            fig_qty.update_xaxes(tickangle=45)
            st.plotly_chart(fig_qty, use_container_width=True)
        
        with tab2:
            fig_money = px.bar(problem_stores_df.head(10), x='магазин', y='Отклонение_%_грн',
                             title='ТОП-10 магазинов по отклонению в деньгах (%)',
                             color='Отклонение_%_грн', color_continuous_scale='RdYlBu_r')
            fig_money.update_xaxes(tickangle=45)
            st.plotly_chart(fig_money, use_container_width=True)
    else:
        st.info("Нет магазинов с отклонением больше заданного порога.")

    # --- Детальный анализ ---
    st.sidebar.header("🔍 Детальный анализ")
    
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique()) if not problem_stores_df.empty else []
    
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

            # Дополнительные фильтры
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

            metrics = calculate_metrics(filtered_df)

            # Отображение информации о фильтрах
            filter_info = []
            if selected_segment != 'Все': 
                filter_info.append(f"Сегмент: **{selected_segment}**")
            if selected_brand != 'Все': 
                filter_info.append(f"Бренд: **{selected_brand}**")
            
            if filter_info:
                st.info("🔍 Применены фильтры: " + ", ".join(filter_info))

            # 1. Ключевые метрики
            st.subheader("📊 Ключевые показатели")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("План (шт.)", f"{int(metrics['total_plan_qty']):,}")
            with col2:
                st.metric("Факт (шт.)", f"{int(metrics['total_fact_qty']):,}", delta=f"{int(metrics['qty_deviation']):+,}")
            with col3:
                st.metric("План (грн.)", f"{metrics['total_plan_money']:,.0f}")
            with col4:
                st.metric("Факт (грн.)", f"{metrics['total_fact_money']:,.0f}", delta=f"{metrics['money_deviation']:+,.0f}")

            # 2. Проценты выполнения
            st.subheader("🎯 Выполнение плана")
            col1, col2 = st.columns(2)
            with col1:
                completion_color = "normal" if 80 <= metrics['qty_completion'] <= 120 else "inverse"
                st.metric("Выполнение по количеству", f"{metrics['qty_completion']:.1f}%",
                         delta=f"{metrics['qty_completion'] - 100:.1f}%", delta_color=completion_color)
            with col2:
                completion_color = "normal" if 80 <= metrics['money_completion'] <= 120 else "inverse"
                st.metric("Выполнение по стоимости", f"{metrics['money_completion']:.1f}%",
                         delta=f"{metrics['money_completion'] - 100:.1f}%", delta_color=completion_color)

            # 3. Структура сегментов
            if len(all_segments) > 1 and 'Segment' in store_df.columns:
                st.subheader("🥧 Структура сегментов")
                segment_data = store_df.groupby('Segment').agg({'Plan_GRN': 'sum', 'Fact_GRN': 'sum'}).reset_index()
                segment_data = segment_data[segment_data['Plan_GRN'] > 0]
                
                if not segment_data.empty:
                    col1, col2 = st.columns(2)
                    with col1:
                        fig_pie_plan = px.pie(segment_data, values='Plan_GRN', names='Segment',
                                            title='План по сегментам (грн.)', hole=0.3)
                        st.plotly_chart(fig_pie_plan, use_container_width=True)
                    with col2:
                        fig_pie_fact = px.pie(segment_data, values='Fact_GRN', names='Segment',
                                            title='Факт по сегментам (грн.)', hole=0.3)
                        st.plotly_chart(fig_pie_fact, use_container_width=True)

            # 4. Спидометры
            if selected_segment != 'Все':
                st.subheader(f"⚡ Спидометры для сегмента: '{selected_segment}'")
                col1, col2 = st.columns(2)
                
                with col1:
                    gauge_max_qty = max(metrics['total_plan_qty'], metrics['total_fact_qty']) * 1.2
                    fig_gauge_qty = go.Figure(go.Indicator(
                        mode="gauge+number+delta", value=metrics['total_fact_qty'],
                        title={'text': "<b>Выполнение в штуках</b>"}, delta={'reference': metrics['total_plan_qty']},
                        gauge={'axis': {'range': [0, gauge_max_qty]}, 'bar': {'color': "#1f77b4"},
                               'steps': [{'range': [0, metrics['total_plan_qty'] * 0.8], 'color': "lightgray"},
                                        {'range': [metrics['total_plan_qty'] * 0.8, metrics['total_plan_qty'] * 1.2], 'color': "gray"}],
                               'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': metrics['total_plan_qty']}}
                    ))
                    st.plotly_chart(fig_gauge_qty, use_container_width=True)
                
                with col2:
                    gauge_max_money = max(metrics['total_plan_money'], metrics['total_fact_money']) * 1.2
                    fig_gauge_money = go.Figure(go.Indicator(
                        mode="gauge+number+delta", value=metrics['total_fact_money'],
                        title={'text': "<b>Выполнение в деньгах</b>"}, number={'suffix': " грн."},
                        delta={'reference': metrics['total_plan_money']},
                        gauge={'axis': {'range': [0, gauge_max_money]}, 'bar': {'color': "#1f77b4"},
                               'steps': [{'range': [0, metrics['total_plan_money'] * 0.8], 'color': "lightgray"},
                                        {'range': [metrics['total_plan_money'] * 0.8, metrics['total_plan_money'] * 1.2], 'color': "gray"}],
                               'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': metrics['total_plan_money']}}
                    ))
                    st.plotly_chart(fig_gauge_money, use_container_width=True)

            # 5. Анализ расхождений
            st.subheader("⚠️ Анализ расхождений")
            discrepancy_df = filtered_df[(filtered_df['Отклонение_шт'] != 0) | (filtered_df['Отклонение_грн'] != 0)].copy()
            
            if not discrepancy_df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Позиций с расхождениями", len(discrepancy_df))
                with col2:
                    overstock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] > 0])
                    st.metric("Переостаток", overstock)
                with col3:
                    understock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] < 0])
                    st.metric("Недостаток", understock)
                
                # Настройки отображения таблицы
                show_mode = st.radio("Показать:", ['Все расхождения', 'Только переостаток', 'Только недостаток'], horizontal=True)
                
                if show_mode == 'Только переостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
                elif show_mode == 'Только недостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
                else:
                    table_df = discrepancy_df
                
                sort_column = st.selectbox("Сортировать по:", ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'])
                table_df = table_df.sort_values(by=sort_column, ascending=False, key=abs)
                
                # Отображение таблицы расхождений
                display_columns = {'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд',
                                 'Segment': 'Сегмент', 'Price': 'Цена (грн.)', 'Plan_STUKI': 'План (шт.)',
                                 'Fact_STUKI': 'Факт (шт.)', 'Отклонение_шт': 'Откл. (шт.)', 'Отклонение_%_шт': 'Откл. (%)',
                                 'Plan_GRN': 'План (грн.)', 'Fact_GRN': 'Факт (грн.)', 'Отклонение_грн': 'Откл. (грн.)'}
                
                columns_to_show = [col for col in display_columns.keys() if col in table_df.columns]
                display_df = table_df[columns_to_show].copy()
                
                # Форматирование числовых колонок
                for col in ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].astype(int)
                for col in ['Price', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].round(2)
                for col in ['Отклонение_%_шт', 'Отклонение_%_грн']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].round(1)
                
                st.dataframe(display_df.rename(columns=display_columns), use_container_width=True, height=400)
                
                # Экспорт
                if st.button("📥 Экспорт таблицы расхождений в Excel"):
                    output_df = display_df.rename(columns=display_columns)
                    output_df.to_excel(f"расхождения_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", index=False)
                    st.success("Файл экспортирован!")
