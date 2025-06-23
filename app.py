import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Анализ План/Факт v3.1",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Сервис для сравнения План/Факт остатков")
st.write("Загрузите файлы Excel, выберите магазин и фильтры для детального анализа.")

# --- Блок загрузки файлов ---
st.header("1. Загрузка и проверка файлов")

col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"])
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"])

def validate_columns(df, required_cols, filename):
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"**Ошибка в файле '{filename}':** Отсутствуют обязательные колонки: `{', '.join(missing_cols)}`")
        return False
    return True

# --- Основная логика после загрузки файлов ---
if plan_file and fact_file:
    try:
        plan_df = pd.read_excel(plan_file)
        fact_df = pd.read_excel(fact_file)

        # ПРОВЕРКА: Убедимся, что в файле "План" есть обе колонки
        REQUIRED_PLAN_COLS = ['магазин', 'ART', 'Describe', 'MOD', 'Price', 'brend', 'Segment', 'Должно_быть_на_остатках', 'Остатки в деньгах']
        REQUIRED_FACT_COLS = ['магазин', 'ART', 'Describe', 'MOD', 'остатки']

        if not validate_columns(plan_df, REQUIRED_PLAN_COLS, plan_file.name) or \
           not validate_columns(fact_df, REQUIRED_FACT_COLS, fact_file.name):
            st.stop()

        # --- ИСПРАВЛЕННОЕ ПЕРЕИМЕНОВАНИЕ ---
        # Здесь реализовано логически верное переименование
        plan_df = plan_df.rename(columns={
            'Должно_быть_на_остатках': 'Plan_STUKI', # Это количество
            'Остатки в деньгах': 'Plan_GRN'         # Это деньги
        })
        fact_df = fact_df.rename(columns={'остатки': 'Fact_STUKI'})
        
        merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
        plan_df.dropna(subset=merge_keys, inplace=True)
        fact_df.dropna(subset=merge_keys, inplace=True)
        
        merged_df = pd.merge(plan_df, fact_df[merge_keys + ['Fact_STUKI']], on=merge_keys, how='outer')

        columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
        for col in columns_to_fill:
            if col in merged_df.columns:
                merged_df[col] = merged_df[col].fillna(0)
        
        merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']

        # --- Боковая панель с фильтрами ---
        st.sidebar.header("Параметры анализа")
        all_stores = sorted(merged_df['магазин'].dropna().unique())
        selected_store = st.sidebar.selectbox("Шаг 1: Выберите магазин", options=all_stores)
        store_df = merged_df[merged_df['магазин'] == selected_store].copy()
        all_segments = ['Выбрать все'] + sorted(store_df['Segment'].dropna().unique())
        selected_segment = st.sidebar.selectbox("Шаг 2: Выберите сегмент", options=all_segments)
        all_brands = ['Выбрать все'] + sorted(store_df['brend'].dropna().unique())
        selected_brand = st.sidebar.selectbox("Шаг 3: Выберите бренд", options=all_brands)
        
        # --- Применение фильтров ---
        filtered_df = store_df.copy()
        if selected_segment != 'Выбрать все':
            filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
        if selected_brand != 'Выбрать все':
            filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

        # --- Визуализация структуры магазина ---
        st.header(f"2. Анализ структуры магазина '{selected_store}'")
        segment_data = store_df.groupby('Segment')['Plan_GRN'].sum().reset_index()
        segment_data = segment_data[segment_data['Plan_GRN'] > 0]
        fig_pie = px.pie(segment_data, values='Plan_GRN', names='Segment', 
                         title='Структура сегментов по плановой стоимости (Грн.)', hole=0.3)
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)

        # --- Итоговые метрики ---
        st.header(f"3. Результаты План/Факт анализа")
        filter_info = []
        if selected_segment != 'Выбрать все': filter_info.append(f"Сегмент: **{selected_segment}**")
        if selected_brand != 'Выбрать все': filter_info.append(f"Бренд: **{selected_brand}**")
        st.markdown("Применены фильтры: " + (", ".join(filter_info) if filter_info else "*Все товары магазина*"))

        total_plan_qty = filtered_df['Plan_STUKI'].sum()
        total_fact_qty = filtered_df['Fact_STUKI'].sum()
        total_plan_money = filtered_df['Plan_GRN'].sum()
        total_fact_money = filtered_df['Fact_GRN'].sum()

        qty_completion_percent = (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0
        money_completion_percent = (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0

        st.subheader("Сводная статистика")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="План, шт.", value=f"{int(total_plan_qty)}")
            st.metric(label="Факт, шт.", value=f"{int(total_fact_qty)}", delta=f"{int(total_fact_qty - total_plan_qty)} шт.")
        with col2:
            st.metric(label="План, деньги", value=f"{total_plan_money:,.2f} Грн.")
            st.metric(label="Факт, деньги", value=f"{total_fact_money:,.2f} Грн.", delta=f"{(total_fact_money - total_plan_money):,.2f} Грн.")
        with col3:
            st.metric(label="Выполнение плана по кол-ву", value=f"{qty_completion_percent:.1f}%")
            st.metric(label="Выполнение плана по деньгам", value=f"{money_completion_percent:.1f}%")

        # --- Спидометры ---
        if selected_segment != 'Выбрать все':
            st.subheader(f"Выполнение плана по сегменту: '{selected_segment}'")
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                fig_gauge_qty = go.Figure(go.Indicator(
                    mode="gauge+number", value=total_fact_qty, title={'text': "<b>Выполнение в штуках (шт.)</b>"},
                    gauge={'axis': {'range': [0, total_plan_qty]}, 'bar': {'color': "#1f77b4"},
                           'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': total_plan_qty}}))
                st.plotly_chart(fig_gauge_qty, use_container_width=True)
            with g_col2:
                fig_gauge_money = go.Figure(go.Indicator(
                    mode="gauge+number+delta", value=total_fact_money, title={'text': "<b>Выполнение в деньгах (Грн.)</b>"},
                    number={'suffix': " Грн."}, delta={'reference': total_plan_money},
                    gauge={'axis': {'range': [0, total_plan_money]}, 'bar': {'color': "#1f77b4"},
                           'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': total_plan_money}}))
                st.plotly_chart(fig_gauge_money, use_container_width=True)

        # --- Детальная таблица ---
        st.header("4. Детальная таблица с расхождениями")
        filtered_df['Отклонение, шт'] = filtered_df['Fact_STUKI'] - filtered_df['Plan_STUKI']
        discrepancy_df = filtered_df[filtered_df['Отклонение, шт'] != 0].copy()
        st.write(f"Найдено позиций с расхождениями: **{len(discrepancy_df)}**")
        display_columns = {
            'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд',
            'Segment': 'Сегмент', 'Price': 'Цена, Грн.', 'Plan_STUKI': 'План, шт.',
            'Fact_STUKI': 'Факт, шт.', 'Отклонение, шт': 'Отклонение, шт.'
        }
        columns_to_show = [col for col in display_columns.keys() if col in discrepancy_df.columns]
        st.dataframe(
            discrepancy_df[columns_to_show].rename(columns=display_columns), 
            use_container_width=True, height=400
        )

    except Exception as e:
        st.error(f"**Критическая ошибка при обработке файлов:** {e}")
        st.warning("Пожалуйста, проверьте формат данных и названия столбцов в ваших файлах Excel.")

else:
    st.info("Пожалуйста, загрузите оба файла, чтобы начать анализ.")
