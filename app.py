import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# --- Конфигурация страницы ---
st.set_page_config(page_title="План/Факт Анализ v8.0-Robust", page_icon="🏆", layout="wide")
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
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            valid_numeric = 'N/A (Дата)'
        else:
            valid_numeric = pd.to_numeric(df[col], errors='coerce').notna().sum()
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
    magazin_cols = sorted([col for col in plan_data_cols if str(col).startswith('Magazin')])
    stuki_cols = sorted([col for col in plan_data_cols if str(col).startswith('Plan_STUKI')])
    grn_cols = sorted([col for col in plan_data_cols if str(col).startswith('Plan_GRN')])
    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI', 'Plan_GRN' не совпадает или равно нулю. Проверьте префиксы.")
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

def calculate_metrics(df):
    """Рассчитывает основные метрики для данных."""
    total_plan_qty = df['Plan_STUKI'].sum()
    total_fact_qty = df['Fact_STUKI'].sum()
    total_plan_money = df['Plan_GRN'].sum()
    total_fact_money = df['Fact_GRN'].sum()
    return {'total_plan_qty': total_plan_qty, 'total_fact_qty': total_fact_qty, 'total_plan_money': total_plan_money, 'total_fact_money': total_fact_money, 'qty_deviation': total_fact_qty - total_plan_qty, 'money_deviation': total_fact_money - total_plan_money, 'qty_completion': (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0, 'money_completion': (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0}

@st.cache_data
def convert_df_to_excel(df):
    """Конвертирует DataFrame в байты Excel для скачивания."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    processed_data = output.getvalue()
    return processed_data

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state: st.session_state.processed_df = None

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)
with col1: plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
with col2: fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

# --- Анализ и обработка ---
if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file, engine='openpyxl')
    fact_df_original = pd.read_excel(fact_file, engine='openpyxl')

    st.header("1.1. Анализ качества загруженных данных")
    plan_quality = analyze_data_quality(plan_df_original, "План")
    fact_quality = analyze_data_quality(fact_df_original, "Факт")
    st.dataframe(pd.concat([plan_quality, fact_quality], ignore_index=True), use_container_width=True)

    st.header("2. Настройка и обработка данных")
    plan_format = st.radio("Выберите формат файла 'План':", ('Плоский (стандартный)', 'Широкий (горизонтальный)'), horizontal=True)

    with st.form("processing_form"):
        st.subheader("Настройка ключей и сопоставление колонок")
        all_plan_columns = plan_df_original.columns.tolist()
        potential_keys = ['ART', 'Describe', 'MOD', 'Brend', 'Segment', 'Price']
        default_keys = [col for col in potential_keys if col in all_plan_columns]
        
        product_keys = st.multiselect(
            "1. Выберите колонки, уникально описывающие товар (ключи)",
            options=all_plan_columns, default=default_keys,
            help="Эти колонки будут использованы для объединения данных. 'ART' обязателен."
        )

        # --- ИСПРАВЛЕННАЯ ЛОГИКА ---
        st.subheader("2. Сопоставление для файла 'Факт'")
        fact_mappings = {}
        fact_cols = fact_df_original.columns.tolist()
        
        # Динамически создаем список полей для сопоставления
        fields_to_map_for_fact = {'магазин': 'Магазин', 'Fact_STUKI': 'Фактические остатки (шт.)'}
        for key in product_keys:
            if key not in fields_to_map_for_fact:
                fields_to_map_for_fact[key] = key.capitalize() # Используем сам ключ как отображаемое имя

        # Создаем селект-боксы для каждого необходимого поля
        for internal_name, display_name in fields_to_map_for_fact.items():
            # Попробуем найти похожую колонку для авто-выбора
            default_selection = next((col for col in fact_cols if display_name.lower() in str(col).lower()), fact_cols[0])
            fact_mappings[internal_name] = st.selectbox(f'Выберите колонку для "{display_name}"', fact_cols, index=fact_cols.index(default_selection), key=f'fact_{internal_name}')
        
        col1, col2 = st.columns(2)
        with col1: remove_duplicates = st.checkbox("Удалить дубликаты по ключам", value=True)
        with col2: fill_zeros = st.checkbox("Заполнить пропуски в числовых данных нулями", value=True)
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            plan_df_renamed = plan_df_original.rename(columns={'Brend': 'brend'})
            if plan_format == 'Широкий (горизонтальный)':
                if not product_keys: st.error("Для широкого формата необходимо выбрать ключи."); st.stop()
                plan_df = transform_wide_to_flat(plan_df_renamed, product_keys)
            else:
                plan_df = plan_df_renamed.rename(columns={'Magazin': 'магазин'})

            if plan_df is None: st.error("Не удалось обработать файл 'План'."); st.stop()
            
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            fact_df = fact_df_original[list(set(fact_rename_map.keys()))].rename(columns=fact_rename_map)

            merge_keys = ['магазин'] + product_keys
            if 'ART' not in merge_keys: st.error("Колонка 'ART' должна быть выбрана в качестве ключа."); st.stop()
            st.info(f"Объединение будет произведено по ключам: {', '.join(merge_keys)}")

            if remove_duplicates:
                plan_df.drop_duplicates(subset=merge_keys, inplace=True)
                fact_df.drop_duplicates(subset=merge_keys, inplace=True)
            
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key] = plan_df[key].astype(str).str.strip()
                    fact_df[key] = fact_df[key].astype(str).str.strip()
            
            fact_cols_to_merge = list(set(merge_keys + ['Fact_STUKI']))
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

            numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in numeric_columns:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
                    if fill_zeros: merged_df[col] = merged_df[col].fillna(0)
            
            if 'Price' not in merged_df.columns:
                 st.warning("Колонка 'Price' не найдена. Расчеты в деньгах (GRN) могут быть неполными.")
                 merged_df['Price'] = 0
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            
            merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
            merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
            merged_df['Отклонение_%_шт'] = np.where(merged_df['Plan_STUKI'] != 0, (merged_df['Отклонение_шт'] / merged_df['Plan_STUKI']) * 100, np.inf * np.sign(merged_df['Отклонение_шт']))
            merged_df['Отклонение_%_грн'] = np.where(merged_df['Plan_GRN'] != 0, (merged_df['Отклонение_грн'] / merged_df['Plan_GRN']) * 100, np.inf * np.sign(merged_df['Отклонение_грн']))
            
            st.session_state.processed_df = merged_df
            st.success("✅ Данные успешно обработаны!")
            st.metric("Записей после объединения", f"{len(merged_df):,}")

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"❌ Ошибка при обработке данных: {e}")
            st.error("Совет: Убедитесь, что для каждого поля сопоставлена уникальная колонка из файла 'Факт'.")
            
# --- Секция Аналитики (без изменений, т.к. она была корректна) ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df
    # ... (весь остальной код аналитики остается таким же, как в предыдущем ответе) ...
    st.header("3. Быстрый анализ отклонений по магазинам")
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()
    
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_грн'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] > 0, (store_summary['Отклонение_шт'] / store_summary['Plan_STUKI']) * 100, np.inf * np.sign(store_summary['Отклонение_шт']))
    store_summary['Отклонение_%_грн'] = np.where(store_summary['Plan_GRN'] > 0, (store_summary['Отклонение_грн'] / store_summary['Plan_GRN']) * 100, np.inf * np.sign(store_summary['Отклонение_грн']))
    
    col1, col2 = st.columns(2)
    with col1:
        threshold = st.number_input("Показать магазины, где абсолютное отклонение в штуках > чем (%)", min_value=0, value=10, step=5)
    with col2:
        sort_by = st.selectbox("Сортировать по", ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'])
    
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'].abs() > threshold].copy()
    if not problem_stores_df.empty:
        problem_stores_df = problem_stores_df.reindex(problem_stores_df[sort_by].abs().sort_values(ascending=False).index)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с абсолютным отклонением > {threshold}%:**")
    
    if not problem_stores_df.empty:
        st.dataframe(problem_stores_df.style.format({
            'Plan_STUKI': '{:,.0f}', 'Fact_STUKI': '{:,.0f}', 'Отклонение_шт': '{:+.0f}',
            'Plan_GRN': '{:,.2f}', 'Fact_GRN': '{:,.2f}', 'Отклонение_грн': '{:+.2f}',
            'Отклонение_%_шт': '{:+.1f}%', 'Отклонение_%_грн': '{:+.1f}%'
        }), use_container_width=True)
    else:
        st.info("Отлично! Нет магазинов с отклонением больше заданного порога.")

    st.sidebar.header("🔍 Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique()) if not problem_stores_df.empty else []
    
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list
    
    if not stores_for_selection:
        st.sidebar.warning("Нет магазинов для выбора по заданным критериям.")
    else:
        selected_store = st.sidebar.selectbox("Выберите магазин:", options=stores_for_selection)
        store_df = processed_df[processed_df['магазин'] == selected_store].copy()

        all_segments = sorted(store_df['Segment'].dropna().unique()) if 'Segment' in store_df.columns else []
        all_brands = sorted(store_df['brend'].dropna().unique()) if 'brend' in store_df.columns else []
        
        selected_segment = st.sidebar.selectbox("Фильтр по сегменту", options=['Все'] + all_segments) if all_segments else 'Все'
        selected_brand = st.sidebar.selectbox("Фильтр по бренду", options=['Все'] + all_brands) if all_brands else 'Все'
        
        filtered_df = store_df.copy()
        if selected_segment != 'Все' and 'Segment' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
        if selected_brand != 'Все' and 'brend' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['brend'] == selected_brand]
        
        st.markdown("---")
        st.header(f"4. 🏪 Детальный анализ магазина: '{selected_store}'")
        metrics = calculate_metrics(filtered_df)

        st.subheader("📊 Ключевые показатели")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("План (шт.)", f"{int(metrics['total_plan_qty']):,}")
        col2.metric("Факт (шт.)", f"{int(metrics['total_fact_qty']):,}", delta=f"{int(metrics['qty_deviation']):+,}")
        col3.metric("План (грн.)", f"{metrics['total_plan_money']:,.0f}")
        col4.metric("Факт (грн.)", f"{metrics['total_fact_money']:,.0f}", delta=f"{metrics['money_deviation']:+,.0f}")

        if 'Segment' in filtered_df.columns and filtered_df['Segment'].nunique() > 1:
            st.subheader("🥧 Структура сегментов (по деньгам)")
            segment_data = filtered_df.groupby('Segment').agg(Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')).reset_index()
            total_plan_grn = metrics['total_plan_money']
            total_fact_grn = metrics['total_fact_money']
            segment_data['Структура План, %'] = (segment_data['Plan_GRN'] / total_plan_grn * 100) if total_plan_grn > 0 else 0
            segment_data['Структура Факт, %'] = (segment_data['Fact_GRN'] / total_fact_grn * 100) if total_fact_grn > 0 else 0
            segment_data['Отклонение, п.п.'] = segment_data['Структура Факт, %'] - segment_data['Структура План, %']
            display_table = segment_data[['Segment', 'Структура План, %', 'Структура Факт, %', 'Отклонение, п.п.']].rename(columns={'Segment': 'Сегмент'})
            display_table = display_table.sort_values(by='Структура План, %', ascending=False)
            st.dataframe(display_table, column_config={"Структура План, %": st.column_config.ProgressColumn("Структура План, %", format="%.1f%%", min_value=0, max_value=100),"Структура Факт, %": st.column_config.ProgressColumn("Структура Факт, %", format="%.1f%%", min_value=0, max_value=100),"Отклонение, п.п.": st.column_config.NumberColumn("Отклонение, п.п.", help="Разница долей (Факт % - План %)", format="%+,.1f п.п.")}, use_container_width=True, hide_index=True)

        st.subheader("⚡ Спидометры выполнения плана")
        col1, col2 = st.columns(2)
        with col1:
            gauge_max_qty = max(metrics['total_plan_qty'], metrics['total_fact_qty']) * 1.2 or 1
            fig_gauge_qty = go.Figure(go.Indicator(mode="gauge+number+delta", value=metrics['total_fact_qty'], title={'text': "<b>Выполнение в штуках</b>"}, delta={'reference': metrics['total_plan_qty']}, gauge={'axis': {'range': [0, gauge_max_qty]}, 'bar': {'color': "#1f77b4"}, 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': metrics['total_plan_qty']}}))
            st.plotly_chart(fig_gauge_qty, use_container_width=True)
        with col2:
            gauge_max_money = max(metrics['total_plan_money'], metrics['total_fact_money']) * 1.2 or 1
            fig_gauge_money = go.Figure(go.Indicator(mode="gauge+number+delta", value=metrics['total_fact_money'], title={'text': "<b>Выполнение в деньгах</b>"}, number={'suffix': " грн."}, delta={'reference': metrics['total_plan_money']}, gauge={'axis': {'range': [0, gauge_max_money]}, 'bar': {'color': "#2ca02c"}, 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': metrics['total_plan_money']}}))
            st.plotly_chart(fig_gauge_money, use_container_width=True)

        st.subheader("⚠️ Анализ расхождений по позициям")
        discrepancy_df = filtered_df[(filtered_df['Отклонение_шт'] != 0) | (filtered_df['Отклонение_грн'] != 0)].copy()
        
        if not discrepancy_df.empty:
            show_mode = st.radio("Показать:", ['Все расхождения', 'Только переостаток (Факт > План)', 'Только недостаток (Факт < План)'], horizontal=True, key=f"show_{selected_store}")
            if show_mode == 'Только переостаток (Факт > План)': table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
            elif show_mode == 'Только недостаток (Факт < План)': table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
            else: table_df = discrepancy_df
            
            sort_column_discr = st.selectbox("Сортировать по модулю:", ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'], key=f"sort_{selected_store}")
            if not table_df.empty:
                table_df = table_df.reindex(table_df[sort_column_discr].abs().sort_values(ascending=False).index)
            
            display_columns_map = {'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Price': 'Цена', 'Plan_STUKI': 'План, шт', 'Fact_STUKI': 'Факт, шт', 'Отклонение_шт': 'Откл, шт', 'Отклонение_%_шт': 'Откл, %', 'Plan_GRN': 'План, грн', 'Fact_GRN': 'Факт, грн', 'Отклонение_грн': 'Откл, грн'}
            columns_to_show = [col for col in display_columns_map.keys() if col in table_df.columns]
            display_df_discr = table_df[columns_to_show].rename(columns=display_columns_map)
            st.dataframe(display_df_discr, use_container_width=True, height=400)
            excel_data_discr = convert_df_to_excel(display_df_discr)
            st.download_button(label="📥 Экспорт таблицы расхождений в Excel", data=excel_data_discr, file_name=f"расхождения_{selected_store}_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.success("🎉 Поздравляем! В данном магазине (с учетом фильтров) расхождений не обнаружено.")

    st.markdown("---")
    st.header("5. Экспорт полных данных")
    st.write("Вы можете скачать полный объединенный набор данных для дальнейшего анализа в других инструментах.")
    excel_data_full = convert_df_to_excel(processed_df)
    st.download_button(label="📥 Экспорт всех обработанных данных в Excel", data=excel_data_full, file_name=f"полный_анализ_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("---")
    st.info("Анализ завершен. Для нового анализа перезагрузите страницу или загрузите новые файлы.")
