import streamlit as st
import pandas as pd

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Анализ План/Факт",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Сервис для сравнения таблиц План/Факт")
st.write(
    "Загрузите файлы Excel с плановыми и фактическими остатками, "
    "чтобы провести анализ и увидеть расхождения."
)

# --- Блок загрузки файлов ---
st.header("1. Загрузка файлов")

# Размещаем загрузчики в две колонки для компактности
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"])
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"])

# --- Основная логика после загрузки файлов ---
if plan_file and fact_file:
    try:
        # Загрузка данных в pandas DataFrame
        plan_df = pd.read_excel(plan_file)
        fact_df = pd.read_excel(fact_file)

        st.success("✅ Файлы успешно загружены. Идет обработка...")

        # --- Предварительная обработка и слияние таблиц ---
        
        # Переименуем столбцы для единообразия перед слиянием
        # Столбец с фактическими остатками в таблице "Факт"
        fact_df = fact_df.rename(columns={'остатки': 'Факт_остатки_шт'})
        
        # Столбцы с плановыми остатками в таблице "План"
        plan_df = plan_df.rename(columns={
            'Должно_быть_на_остатках': 'План_остатки_шт',
            'Остатки в деньгах': 'План_остатки_деньги'
        })
        
        # Определяем ключевые столбцы для слияния.
        # Использование нескольких столбцов (составной ключ) намного надежнее,
        # чем один 'Describe', так как описание может быть одинаковым для разных артикулов.
        merge_keys = ['магазин', 'ART', 'Describe', 'MOD']

        # Выполняем слияние таблиц. 'outer' join покажет все позиции:
        # и те, что есть в плане, но нет в факте, и наоборот.
        merged_df = pd.merge(
            plan_df,
            fact_df,
            on=merge_keys,
            how='outer'
        )

        # Заполняем пропуски (NaN) нулями. Это происходит, когда товар есть
        # в одной таблице, но отсутствует в другой.
        columns_to_fill = ['План_остатки_шт', 'Факт_остатки_шт', 'План_остатки_деньги', 'Price']
        for col in columns_to_fill:
            if col in merged_df.columns:
                merged_df[col] = merged_df[col].fillna(0)
        
        # Рассчитываем фактические остатки в деньгах
        # (умножаем фактическое количество на цену из плана)
        merged_df['Факт_остатки_деньги'] = merged_df['Факт_остатки_шт'] * merged_df['Price']

        # --- Боковая панель с фильтрами ---
        st.sidebar.header("Фильтры для анализа")

        # 1. Фильтр по магазину (обязательный выбор)
        # Получаем уникальные магазины из объединенной таблицы
        all_stores = sorted(merged_df['магазин'].dropna().unique())
        selected_store = st.sidebar.selectbox(
            "Выберите магазин для анализа:",
            options=all_stores
        )

        # Фильтруем данные по выбранному магазину
        store_df = merged_df[merged_df['магазин'] == selected_store].copy()

        # 2. Фильтр по бренду
        all_brands = ['Выбрать все'] + sorted(store_df['brend'].dropna().unique())
        selected_brand = st.sidebar.selectbox(
            "Выберите бренд:",
            options=all_brands
        )

        # 3. Фильтр по сегменту
        all_segments = ['Выбрать все'] + sorted(store_df['Segment'].dropna().unique())
        selected_segment = st.sidebar.selectbox(
            "Выберите сегмент:",
            options=all_segments
        )

        # --- Применение фильтров по бренду и сегменту ---
        filtered_df = store_df.copy() # Начинаем с данных по магазину
        
        if selected_brand != 'Выбрать все':
            filtered_df = filtered_df[filtered_df['brend'] == selected_brand]
        
        if selected_segment != 'Выбрать все':
            filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]

        # --- Расчет итоговых метрик ---
        st.header(f"2. Итоговые результаты для магазина: '{selected_store}'")

        # Применяем фильтры к заголовку, если они выбраны
        filter_info = []
        if selected_brand != 'Выбрать все':
            filter_info.append(f"Бренд: **{selected_brand}**")
        if selected_segment != 'Выбрать все':
            filter_info.append(f"Сегмент: **{selected_segment}**")
        
        if filter_info:
            st.markdown("Применены фильтры: " + ", ".join(filter_info))
        else:
            st.markdown("Применены фильтры: *нет*")


        # Расчет сумм
        total_plan_qty = filtered_df['План_остатки_шт'].sum()
        total_fact_qty = filtered_df['Факт_остатки_шт'].sum()
        total_plan_money = filtered_df['План_остатки_деньги'].sum()
        total_fact_money = filtered_df['Факт_остатки_деньги'].sum()

        # Отображение метрик в колонках
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Остатки в штуках (шт.)")
            st.metric(label="ПЛАН", value=f"{int(total_plan_qty)} шт.")
            st.metric(label="ФАКТ", value=f"{int(total_fact_qty)} шт.", 
                      delta=f"{int(total_fact_qty - total_plan_qty)} шт.")

        with col2:
            st.subheader("Остатки в деньгах (руб.)")
            st.metric(label="ПЛАН", value=f"{total_plan_money:,.2f} руб.")
            st.metric(label="ФАКТ", value=f"{total_fact_money:,.2f} руб.",
                      delta=f"{(total_fact_money - total_plan_money):,.2f} руб.")

        # --- Отображение детальной таблицы с расхождениями ---
        st.header("3. Детальная таблица с расхождениями")
        
        # Добавляем столбец с отклонением для удобства
        filtered_df['Отклонение_шт'] = filtered_df['Факт_остатки_шт'] - filtered_df['План_остатки_шт']
        
        # Показываем только те строки, где есть расхождения
        discrepancy_df = filtered_df[filtered_df['Отклонение_шт'] != 0].copy()

        st.write(f"Найдено позиций с расхождениями: **{len(discrepancy_df)}**")

        # Выбираем и переименовываем столбцы для наглядности
        display_columns = {
            'ART': 'Артикул',
            'Describe': 'Описание',
            'MOD': 'Модель',
            'brend': 'Бренд',
            'Segment': 'Сегмент',
            'Price': 'Цена',
            'План_остатки_шт': 'План, шт.',
            'Факт_остатки_шт': 'Факт, шт.',
            'Отклонение_шт': 'Отклонение, шт.'
        }
        
        # Отфильтровываем столбцы, которых может не быть в исходных данных
        columns_to_show = [col for col in display_columns.keys() if col in discrepancy_df.columns]
        
        st.dataframe(
            discrepancy_df[columns_to_show].rename(columns=display_columns), 
            use_container_width=True
        )

        st.info("💡 Таблица выше показывает только те товары, где фактические остатки не совпадают с плановыми.")

    except Exception as e:
        st.error(f"Произошла ошибка при обработке файлов: {e}")
        st.warning("Пожалуйста, проверьте, что столбцы в ваших файлах имеют правильные названия и формат.")

else:
    st.info("Пожалуйста, загрузите оба файла, чтобы начать анализ.")
