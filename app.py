import streamlit as st
import pandas as pd

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Анализ План/Факт v2.0",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Сервис для сравнения План/Факт остатков")
st.write(
    "Загрузите файлы Excel, выберите магазин и фильтры для анализа расхождений."
)

# --- Блок загрузки файлов ---
st.header("1. Загрузка и проверка файлов")

col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"])
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"])

# --- Функция для проверки колонок ---
def validate_columns(df, required_cols, filename):
    """Проверяет наличие необходимых колонок в DataFrame."""
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

        # --- Проверка качества данных (наличие колонок) ---
        REQUIRED_PLAN_COLS = ['магазин', 'ART', 'Describe', 'MOD', 'Price', 'brend', 'Sex', 'Pl/Metal', 'Segment', 'Оборачиваемость_позии', 'Должно_быть_на_остатках', 'Остатки в деньгах']
        REQUIRED_FACT_COLS = ['магазин', 'ART', 'Describe', 'MOD', 'остатки']

        is_plan_valid = validate_columns(plan_df, REQUIRED_PLAN_COLS, plan_file.name)
        is_fact_valid = validate_columns(fact_df, REQUIRED_FACT_COLS, fact_file.name)

        if not is_plan_valid or not is_fact_valid:
            st.stop() # Останавливаем выполнение, если проверка не пройдена

        # --- Статистика по загрузке ---
        initial_plan_rows = len(plan_df)
        initial_fact_rows = len(fact_df)
        
        # Ключи для слияния - если в этих колонках есть пустые значения, строка бесполезна
        merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
        plan_df.dropna(subset=merge_keys, inplace=True)
        fact_df.dropna(subset=merge_keys, inplace=True)
        
        processed_plan_rows = len(plan_df)
        processed_fact_rows = len(fact_df)
        
        with st.expander("Показать статистику загрузки файлов", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.subheader(f"Файл 'План' ({plan_file.name})")
                st.metric("Всего строк в файле", value=initial_plan_rows)
                st.metric("Строк обработано (с ключами)", value=processed_plan_rows)
                st.metric("Строк пропущено (без ключей)", value=initial_plan_rows - processed_plan_rows)
            with c2:
                st.subheader(f"Файл 'Факт' ({fact_file.name})")
                st.metric("Всего строк в файле", value=initial_fact_rows)
                st.metric("Строк обработано (с ключами)", value=processed_fact_rows)
                st.metric("Строк пропущено (без ключей)", value=initial_fact_rows - processed_fact_rows)
        
        # --- Предварительная обработка и слияние таблиц ---
        plan_df = plan_df.rename(columns={'Должно_быть_на_остатках': 'План_остатки_шт', 'Остатки в деньгах': 'План_остатки_деньги'})
        fact_df = fact_df.rename(columns={'остатки': 'Факт_остатки_шт'})
        
        # Слияние 'outer' join - лучший выбор для план/факт анализа.
        # Он сохраняет все строки из обеих таблиц, показывая и недостачи (есть в плане, нет в факте)
        # и излишки (есть в факте, нет в плане). 'right' join скрыл бы недостачи.
        merged_df = pd.merge(plan_df, fact_df[merge_keys + ['Факт_остатки_шт']], on=merge_keys, how='outer')

        # РЕШЕНИЕ ПРОБЛЕМЫ С 'Price': Заполняем пропуски нулями ПОСЛЕ слияния, но ДО расчетов.
        # Это ключевой шаг, чтобы избежать ошибок при вычислении 'Факт_остатки_деньги'.
        columns_to_fill = ['План_остатки_шт', 'Факт_остатки_шт', 'План_остатки_деньги', 'Price']
        for col in columns_to_fill:
            if col in merged_df.columns:
                merged_df[col] = merged_df[col].fillna(0)
        
        merged_df['Факт_остатки_деньги'] = merged_df['Факт_остатки_шт'] * merged_df['Price']

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

        # --- Расчет итоговых метрик ---
        st.header(f"2. Результаты анализа для магазина: '{selected_store}'")
        
        filter_info = []
        if selected_segment != 'Выбрать все': filter_info.append(f"Сегмент: **{selected_segment}**")
        if selected_brand != 'Выбрать все': filter_info.append(f"Бренд: **{selected_brand}**")
        st.markdown("Применены фильтры: " + (", ".join(filter_info) if filter_info else "*нет*"))

        total_plan_qty = filtered_df['План_остатки_шт'].sum()
        total_fact_qty = filtered_df['Факт_остатки_шт'].sum()
        total_plan_money = filtered_df['План_остатки_деньги'].sum()
        total_fact_money = filtered_df['Факт_остатки_деньги'].sum()

        # Расчет процентов выполнения плана
        # Проверяем деление на ноль
        qty_completion_percent = (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0
        money_completion_percent = (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0

        # --- Отображение расширенной статистики ---
        st.subheader("Сводная статистика")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="План, шт.", value=f"{int(total_plan_qty)}")
            st.metric(label="Факт, шт.", value=f"{int(total_fact_qty)}", delta=f"{int(total_fact_qty - total_plan_qty)} шт.")
        with col2:
            st.metric(label="План, деньги", value=f"{total_plan_money:,.2f} руб.")
            st.metric(label="Факт, деньги", value=f"{total_fact_money:,.2f} руб.", delta=f"{(total_fact_money - total_plan_money):,.2f} руб.")
        with col3:
            st.metric(label="Выполнение плана по кол-ву", value=f"{qty_completion_percent:.1f}%")
            st.metric(label="Выполнение плана по деньгам", value=f"{money_completion_percent:.1f}%")


        # --- Отображение детальной таблицы ---
        st.header("3. Детальная таблица с расхождениями")
        filtered_df['Отклонение, шт'] = filtered_df['Факт_остатки_шт'] - filtered_df['План_остатки_шт']
        
        discrepancy_df = filtered_df[filtered_df['Отклонение, шт'] != 0].copy()
        st.write(f"Найдено позиций с расхождениями: **{len(discrepancy_df)}**")

        display_columns = {
            'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд',
            'Segment': 'Сегмент', 'Price': 'Цена', 'План_остатки_шт': 'План, шт.',
            'Факт_остатки_шт': 'Факт, шт.', 'Отклонение, шт': 'Отклонение, шт.'
        }
        
        columns_to_show = [col for col in display_columns.keys() if col in discrepancy_df.columns]
        
        st.dataframe(
            discrepancy_df[columns_to_show].rename(columns=display_columns), 
            use_container_width=True,
            height=400
        )
        st.info("💡 В таблице выше показаны только те товары, где фактические остатки не совпадают с плановыми.")

    except Exception as e:
        st.error(f"**Критическая ошибка при обработке файлов:** {e}")
        st.warning("Пожалуйста, проверьте формат данных и названия столбцов в ваших файлах Excel.")

else:
    st.info("Пожалуйста, загрузите оба файла, чтобы начать анализ.")
