import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# --- Конфигурация страницы ---
st.set_page_config(page_title="План/Факт Анализ v11.0-Hybrid", page_icon="🏆", layout="wide")
st.title("🏆 Универсальный сервис для План/Факт анализа")
st.info("Эта версия поддерживает **горизонтальный (широкий)** и плоский формат файла 'План'. Ключ для объединения: **Магазин + Описание + Модель**.")

# --- Вспомогательные функции ---
@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    magazin_cols = sorted([col for col in plan_data_cols if str(col).startswith('Magazin')])
    stuki_cols = sorted([col for col in plan_data_cols if str(col).startswith('Plan_STUKI')])
    grn_cols = sorted([col for col in plan_data_cols if str(col).startswith('Plan_GRN')])

    if not (len(magazin_cols) == len(stuki_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры файла Плана: Количество колонок с префиксами 'Magazin' и 'Plan_STUKI' не совпадает или равно нулю.")
        return None
    
    # Колонка Plan_GRN опциональна
    has_grn = len(magazin_cols) == len(grn_cols)

    flat_parts = []
    for i in range(len(magazin_cols)):
        # Собираем текущие колонки
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i]]
        if has_grn:
            current_cols.append(grn_cols[i])
            
        part_df = _wide_df[current_cols].copy()
        
        # Переименовываем
        rename_dict = {magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI'}
        if has_grn:
            rename_dict[grn_cols[i]] = 'Plan_GRN'
        
        part_df.rename(columns=rename_dict, inplace=True)
        flat_parts.append(part_df)
        
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True)
    return flat_df

@st.cache_data
def calculate_metrics(df):
    """Рассчитывает основные метрики для данных."""
    total_plan_qty = df['Plan_STUKI'].sum()
    total_fact_qty = df['Fact_STUKI'].sum()
    total_plan_money = df.get('Plan_GRN', 0).sum()
    total_fact_money = df.get('Fact_GRN', 0).sum()
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
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"])
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"])

if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file, engine='openpyxl')
    fact_df_original = pd.read_excel(fact_file, engine='openpyxl')

    st.header("2. Настройка обработки")
    
    with st.form("processing_form"):
        plan_format = st.radio(
            "1. Выберите формат вашего файла 'План':",
            ('Горизонтальный (широкий)', 'Плоский (обычный)'), horizontal=True
        )

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("2. Настройка файла 'План'")
            plan_cols = plan_df_original.columns.tolist()
            if plan_format == 'Горизонтальный (широкий)':
                id_vars = st.multiselect(
                    "Выберите все колонки, описывающие товар (НЕ относящиеся к магазинам)",
                    options=plan_cols,
                    default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment'] if col in plan_cols],
                    help="Это колонки, которые не повторяются для каждого магазина."
                )
            else: # Плоский формат
                plan_map_flat = {
                    'магазин': st.selectbox("Магазин", plan_cols, key='plan_magazin'),
                    'Describe': st.selectbox("Описание", plan_cols, key='plan_describe'),
                    'MOD': st.selectbox("Модель", plan_cols, key='plan_mod'),
                    'Plan_STUKI': st.selectbox("План (шт.)", plan_cols, key='plan_stuki'),
                    # Опциональные поля из Плана
                    'ART': st.selectbox("Артикул (опционально)", [None] + plan_cols, key='plan_art'),
                    'brend': st.selectbox("Бренд (опционально)", [None] + plan_cols, key='plan_brend'),
                    'Segment': st.selectbox("Сегмент (опционально)", [None] + plan_cols, key='plan_segment'),
                    'Price': st.selectbox("Цена (опционально)", [None] + plan_cols, key='plan_price'),
                    'Plan_GRN': st.selectbox("План (грн.) (опционально)", [None] + plan_cols, key='plan_grn'),
                }
        with c2:
            st.subheader("3. Настройка файла 'Факт'")
            fact_cols = fact_df_original.columns.tolist()
            fact_map = {
                'магазин': st.selectbox("Магазин", fact_cols, key='fact_magazin'),
                'Describe': st.selectbox("Описание", fact_cols, key='fact_describe'),
                'MOD': st.selectbox("Модель", fact_cols, key='fact_mod'),
                'Fact_STUKI': st.selectbox("Факт (шт.)", fact_cols, key='fact_stuki'),
            }

        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            # --- Обработка ---
            merge_keys = ['магазин', 'Describe', 'MOD']

            # 1. Готовим файл ПЛАН в зависимости от формата
            if plan_format == 'Горизонтальный (широкий)':
                if not id_vars:
                    st.error("Для горизонтального формата необходимо выбрать описательные колонки товара.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
                if plan_df is None: st.stop() # Ошибка уже показана в функции
            else: # Плоский формат
                plan_rename_map = {v: k for k, v in plan_map_flat.items() if v is not None}
                plan_df = plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)

            # 2. Готовим файл ФАКТ
            fact_rename_map = {v: k for k, v in fact_map.items() if v is not None}
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            # 3. Приведение типов ключей
            for key in merge_keys:
                if key in plan_df.columns: plan_df[key] = plan_df[key].astype(str).str.strip()
                if key in fact_df.columns: fact_df[key] = fact_df[key].astype(str).str.strip()

            # 4. Объединение таблиц (OUTER JOIN, чтобы видеть все расхождения)
            merged_df = pd.merge(plan_df, fact_df, on=merge_keys, how='outer')
            
            # 5. Обработка и расчеты
            numeric_cols = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in numeric_cols:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
                else: 
                    merged_df[col] = 0

            if 'Price' not in merged_df.columns or merged_df['Price'].sum() == 0:
                st.warning("Колонка 'Цена' не найдена или пуста. Расчеты в деньгах по факту могут быть неверны.")
            
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            
            merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
            merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
            merged_df['Отклонение_%_шт'] = np.where(merged_df['Plan_STUKI'] != 0, (merged_df['Отклонение_шт'] / merged_df['Plan_STUKI']) * 100, np.inf * np.sign(merged_df['Отклонение_шт']))
            merged_df['Отклонение_%_грн'] = np.where(merged_df['Plan_GRN'] > 0, (merged_df['Отклонение_грн'] / merged_df['Plan_GRN']) * 100, np.inf * np.sign(merged_df['Отклонение_грн']))
            
            st.session_state.processed_df = merged_df
            st.success("✅ Данные успешно обработаны!")
            st.metric("Записей после объединения", f"{len(merged_df):,}")

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"❌ Ошибка при обработке данных: {e}")
            st.error("Совет: Проверьте, что для обязательных полей выбраны правильные колонки.")

# --- Секция Аналитики (остается без изменений) ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df
    
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
        all_brands = sorted(store_df.get('brend', pd.Series()).dropna().unique())
        
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
