import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="План/Факт Анализ v6.4", page_icon="🏆", layout="wide")
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

plan_df_original = None
fact_df_original = None

col1, col2 = st.columns(2)

with col1:
    st.subheader("Источник данных для 'Плана'")
    plan_source_type = st.radio(
        "Выберите источник:",
        ("Загрузить файл", "Использовать Google Sheet"),
        key="plan_source",
        horizontal=True
    )
    
    if plan_source_type == "Загрузить файл":
        plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
        if plan_file:
            plan_df_original = pd.read_excel(plan_file)
    
    elif plan_source_type == "Использовать Google Sheet":
        g_sheet_url = st.text_input(
            "Вставьте ссылку на Google Таблицу:", 
            "https://docs.google.com/spreadsheets/d/1D8hz6ZLo_orDMokYms2lQkO_A3nnYNEFYe-mO1CDcrY/edit?usp=sharing"
        )
        if g_sheet_url:
            try:
                # Преобразуем URL для прямого скачивания CSV
                csv_url = g_sheet_url.replace("/edit?usp=sharing", "/export?format=csv").replace("/edit", "/export?format=csv")
                plan_df_original = pd.read_csv(csv_url)
                st.info(f"✅ Таблица успешно загружена. Найдено {len(plan_df_original)} строк.")
            except Exception as e:
                st.error(f"Не удалось загрузить таблицу. Ошибка: {e}")
                st.warning("Убедитесь, что ссылка верна и доступ к таблице открыт (хотя бы для просмотра).")

with col2:
    st.subheader("Источник данных для 'Факта'")
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")
    if fact_file:
        fact_df_original = pd.read_excel(fact_file)


# --- Анализ качества данных ---
if plan_df_original is not None and fact_df_original is not None:
    st.header("1.1. Анализ качества загруженных данных")
    plan_quality = analyze_data_quality(plan_df_original, "План")
    fact_quality = analyze_data_quality(fact_df_original, "Факт")
    quality_df = pd.concat([plan_quality, fact_quality], ignore_index=True)
    
    st.subheader("📊 Статистика по колонкам")
    st.dataframe(quality_df, use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Колонок в данных 'План'", len(plan_df_original.columns))
        st.metric("Строк в данных 'План'", len(plan_df_original))
    with col2:
        st.metric("Колонок в файле 'Факт'", len(fact_df_original.columns))
        st.metric("Строк в файле 'Факт'", len(fact_df_original))

    st.header("2. Настройка и обработка данных")
    
    plan_format = st.radio(
        "Выберите формат данных 'План':",
        ('Плоский (стандартный)', 'Широкий (горизонтальный)'), horizontal=True,
        help="Широкий формат - когда данные по магазинам идут вправо по колонкам."
    )

    with st.form("processing_form"):
        plan_mappings = {}
        id_vars = []
        
        plan_cols = plan_df_original.columns.tolist()
        fact_cols = fact_df_original.columns.tolist()

        if plan_format == 'Широкий (горизонтальный)':
            st.subheader("Настройка для широкого формата 'План'")
            id_vars = st.multiselect(
                "Выберите все колонки, описывающие товар (НЕ относящиеся к магазинам)",
                options=plan_cols,
                default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment'] if col in plan_cols]
            )
        else: # Плоский формат
            st.subheader("Сопоставление для данных 'План' (плоский формат)")
            PLAN_REQUIRED_FIELDS = {
                'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
                'Segment': 'Сегмент', 'brend': 'Бренд', 'Price': 'Цена',
                'Plan_STUKI': 'Плановые остатки (шт.)', 'Plan_GRN': 'Плановые остатки (грн.)'
            }
            for internal, display in PLAN_REQUIRED_FIELDS.items():
                default_selection = [c for c in plan_cols if c.lower() == internal.lower() or c.lower() == display.lower()]
                default_index = plan_cols.index(default_selection[0]) if default_selection else 0
                
                plan_mappings[internal] = st.selectbox(
                    f'"{display}"', plan_cols, key=f'plan_{internal}', index=default_index
                )

        st.subheader("Сопоставление для файла 'Факт'")
        fact_mappings = {}
        FACT_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
            'brend': 'Бренд', 'Fact_STUKI': 'Фактические остатки (шт.)'
        }
        for internal, display in FACT_REQUIRED_FIELDS.items():
            default_selection = [c for c in fact_cols if c.lower() == internal.lower() or c.lower() == display.lower()]
            default_index = fact_cols.index(default_selection[0]) if default_selection else 0
            
            fact_mappings[internal] = st.selectbox(
                f'"{display}"', fact_cols, key=f'fact_{internal}', index=default_index
            )
        
        col1, col2 = st.columns(2)
        with col1:
            remove_duplicates = st.checkbox("Удалить дубликаты", value=True)
        with col2:
            fill_zeros = st.checkbox("Заполнить пропуски нулями", value=True)
            
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            # Обработка данных 'План'
            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars:
                    st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original.copy(), id_vars)
            else: # Плоский формат
                plan_rename_map = {v: k for k, v in plan_mappings.items()}
                plan_df = plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)
                
            if plan_df is None:
                st.error("Не удалось обработать данные 'План'.")
                st.stop()
            
            # Обработка файла 'Факт'
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            # Удаление дубликатов
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            if remove_duplicates:
                plan_keys_exist = all(key in plan_df.columns for key in merge_keys)
                fact_keys_exist = all(key in fact_df.columns for key in merge_keys)
                if plan_keys_exist:
                    plan_df = plan_df.drop_duplicates(subset=merge_keys)
                if fact_keys_exist:
                    fact_df = fact_df.drop_duplicates(subset=merge_keys)
            
            # Приведение типов для слияния
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key] = plan_df[key].astype(str)
                    fact_df[key] = fact_df[key].astype(str)

            # Слияние данных
            fact_cols_to_merge = [key for key in merge_keys + ['Fact_STUKI'] if key in fact_df.columns]
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

            # Обработка числовых колонок
            numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in numeric_columns:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
                    if fill_zeros:
                        merged_df[col] = merged_df[col].fillna(0)
            
            # Расчеты
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df.get('Price', 0)
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

        except KeyError as e:
            st.session_state.processed_df = None
            st.error(f"❌ Ошибка: колонка не найдена - {e}. Проверьте правильность сопоставления колонок на шаге 2.")
        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"❌ Ошибка при обработке данных: {e}")

# --- Аналитика ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df

    st.header("3. Быстрый анализ отклонений по магазинам и сегментам")
    
    if 'Segment' in processed_df.columns:
        group_by_cols = ['магазин', 'Segment']
        summary_df = processed_df.groupby(group_by_cols).agg({
            'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum', 'Plan_GRN': 'sum', 'Fact_GRN': 'sum'
        }).reset_index()
        
        summary_df['Отклонение_шт'] = summary_df['Fact_STUKI'] - summary_df['Plan_STUKI']
        summary_df['Отклонение_грн'] = summary_df['Fact_GRN'] - summary_df['Plan_GRN']
        summary_df['Отклонение_%_шт'] = np.where(
            summary_df['Plan_STUKI'] > 0, 
            abs(summary_df['Отклонение_шт']) / summary_df['Plan_STUKI'] * 100,
            np.where(summary_df['Отклонение_шт'] != 0, np.inf, 0)
        )
        summary_df['Отклонение_%_грн'] = np.where(
            summary_df['Plan_GRN'] > 0, 
            abs(summary_df['Отклонение_грн']) / summary_df['Plan_GRN'] * 100,
            np.where(summary_df['Отклонение_грн'] != 0, np.inf, 0)
        )
        
        col1, col2 = st.columns(2)
        with col1:
            threshold = st.number_input("Показать комбинации, где отклонение в штуках БОЛЬШЕ чем (%)", min_value=0, max_value=500, value=10, step=5)
        with col2:
            sort_by = st.selectbox("Сортировать по", ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'], key="sort_summary")
        
        problem_df = summary_df[summary_df['Отклонение_%_шт'] > threshold].copy().sort_values(by=sort_by, ascending=False)
        
        st.write(f"**Найдено {len(problem_df)} комбинаций 'Магазин-Сегмент' с отклонением > {threshold}%:**")
        
        if not problem_df.empty:
            display_df_summary = problem_df.copy()
            for col in ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт']:
                display_df_summary[col] = display_df_summary[col].astype(int)
            for col in ['Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
                display_df_summary[col] = display_df_summary[col].round(2)
            for col in ['Отклонение_%_шт', 'Отклонение_%_грн']:
                display_df_summary[col] = display_df_summary[col].round(1)
            
            st.dataframe(display_df_summary.rename(columns={
                'магазин': 'Магазин', 'Segment': 'Сегмент', 'Plan_STUKI': 'План, шт', 'Fact_STUKI': 'Факт, шт',
                'Plan_GRN': 'План, грн', 'Fact_GRN': 'Факт, грн', 'Отклонение_шт': 'Откл, шт', 'Отклонение_грн': 'Откл, грн',
                'Отклонение_%_шт': 'Откл, % шт', 'Отклонение_%_грн': 'Откл, % грн'
            }), use_container_width=True, height=500)
            
            if st.button("📥 Экспорт результатов анализа в Excel"):
                export_df = display_df_summary.rename(columns={
                    'магазин': 'Магазин', 'Segment': 'Сегмент', 'Plan_STUKI': 'План, шт', 'Fact_STUKI': 'Факт, шт',
                    'Plan_GRN': 'План, грн', 'Fact_GRN': 'Факт, грн', 'Отклонение_шт': 'Отклонение, шт', 'Отклонение_грн': 'Отклонение, грн',
                    'Отклонение_%_шт': 'Отклонение, % шт', 'Отклонение_%_грн': 'Отклонение, % грн'
                })
                export_df.to_excel(f"анализ_отклонений_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", index=False)
                st.success("Файл экспортирован!")

        else:
            st.info("Нет комбинаций 'Магазин-Сегмент' с отклонением больше заданного порога.")
    else:
        st.warning("Колонка 'Segment' не найдена в данных. Анализ по сегментам недоступен.")
    
    st.sidebar.header("🔍 Детальный анализ")
    
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_df['магазин'].unique()) if 'problem_df' in locals() and not problem_df.empty else []
    
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

            all_segments = sorted(store_df['Segment'].dropna().unique()) if 'Segment' in store_df.columns else []
            all_brands = sorted(store_df['brend'].dropna().unique()) if 'brend' in store_df.columns else []
            
            selected_segment = st.sidebar.selectbox("Выберите сегмент", options=['Все'] + all_segments)
            selected_brand = st.sidebar.selectbox("Выберите бренд", options=['Все'] + all_brands)
            
            filtered_df = store_df.copy()
            if selected_segment != 'Все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            metrics = calculate_metrics(filtered_df)

            filter_info = []
            if selected_segment != 'Все': 
                filter_info.append(f"Сегмент: **{selected_segment}**")
            if selected_brand != 'Все': 
                filter_info.append(f"Бренд: **{selected_brand}**")
            
            if filter_info:
                st.info("🔍 Применены фильтры: " + ", ".join(filter_info))

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

            if 'Segment' in filtered_df.columns and filtered_df['Segment'].nunique() > 1:
                st.subheader("🥧 Структура сегментов (по деньгам)")
                
                segment_data = filtered_df.groupby('Segment').agg(
                    Plan_GRN=('Plan_GRN', 'sum'),
                    Fact_GRN=('Fact_GRN', 'sum')
                ).reset_index()

                total_plan_grn = metrics['total_plan_money']
                total_fact_grn = metrics['total_fact_money']
                
                segment_data['Структура План, %'] = (segment_data['Plan_GRN'] / total_plan_grn * 100) if total_plan_grn > 0 else 0
                segment_data['Структура Факт, %'] = (segment_data['Fact_GRN'] / total_fact_grn * 100) if total_fact_grn > 0 else 0
                segment_data['Отклонение, п.п.'] = segment_data['Структура Факт, %'] - segment_data['Структура План, %']

                display_table = segment_data.rename(columns={
                    'Segment': 'Сегмент', 'Plan_GRN': 'План, грн', 'Fact_GRN': 'Факт, грн'
                })

                display_table = display_table.sort_values(by='Структура План, %', ascending=False)
                
                st.dataframe(
                    display_table,
                    column_config={
                        "План, грн": st.column_config.NumberColumn(format="%.0f"),
                        "Факт, грн": st.column_config.NumberColumn(format="%.0f"),
                        "Структура План, %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                        "Структура Факт, %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                        "Отклонение, п.п.": st.column_config.NumberColumn(format="%+,.1f")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            
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

            st.subheader("⚠️ Анализ расхождений по позициям")
            discrepancy_df = filtered_df[(filtered_df['Отклонение_шт'] != 0) | (filtered_df['Отклонение_грн'] != 0)].copy()
            
            if not discrepancy_df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Позиций с расхождениями", len(discrepancy_df))
                with col2:
                    overstock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] > 0])
                    st.metric("Переостаток (позиций)", overstock)
                with col3:
                    understock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] < 0])
                    st.metric("Недостаток (позиций)", understock)
                
                show_mode = st.radio("Показать:", ['Все расхождения', 'Только переостаток', 'Только недостаток'], horizontal=True, key="show_discrepancy")
                
                if show_mode == 'Только переостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
                elif show_mode == 'Только недостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
                else:
                    table_df = discrepancy_df
                
                sort_column = st.selectbox("Сортировать по:", ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'], key="sort_discrepancy")
                table_df = table_df.sort_values(by=sort_column, ascending=False, key=abs)
                
                display_columns = {'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд',
                                 'Segment': 'Сегмент', 'Price': 'Цена (грн.)', 'Plan_STUKI': 'План (шт.)',
                                 'Fact_STUKI': 'Факт (шт.)', 'Отклонение_шт': 'Откл. (шт.)', 'Отклонение_%_шт': 'Откл. (%)',
                                 'Plan_GRN': 'План (грн.)', 'Fact_GRN': 'Факт (грн.)', 'Отклонение_грн': 'Откл. (грн.)'}
                
                columns_to_show = [col for col in display_columns.keys() if col in table_df.columns]
                display_df_final = table_df[columns_to_show].copy()
                
                for col in ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт']:
                    if col in display_df_final.columns:
                        display_df_final[col] = display_df_final[col].astype(int)
                for col in ['Price', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
                    if col in display_df_final.columns:
                        display_df_final[col] = display_df_final[col].round(2)
                for col in ['Отклонение_%_шт', 'Отклонение_%_грн']:
                    if col in display_df_final.columns:
                        display_df_final[col] = display_df_final[col].round(1)
                
                st.dataframe(display_df_final.rename(columns=display_columns), use_container_width=True, height=400)
                
                if st.button("📥 Экспорт таблицы расхождений в Excel", key="export_final_table"):
                    output_df = display_df_final.rename(columns=display_columns)
                    output_df.to_excel(f"расхождения_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", index=False)
                    st.success("Файл экспортирован!")
