import streamlit as st
import pandas as pd
import io

# --------------------------------------------------------------------- #
# --- БЛОК 0: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
# --------------------------------------------------------------------- #

@st.cache_data
def load_data(uploaded_file):
    """Загружает данные из загруженного файла (CSV или Excel)."""
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                return pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith(('.xls', '.xlsx')):
                return pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Ошибка при чтении файла: {e}")
            return None
    return None

def transform_plan_to_long(df_plan_wide):
    """Преобразует широкую таблицу с планом в длинный формат."""
    try:
        id_vars = ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment']
        missing_cols = [col for col in id_vars if col not in df_plan_wide.columns]
        if missing_cols:
            st.error(f"В файле Плана отсутствуют обязательные столбцы-идентификаторы: {', '.join(missing_cols)}")
            return None
        
        df_plan_long = pd.wide_to_long(
            df_plan_wide,
            stubnames=['Magazin', 'Plan_STUKI', 'Plan_GRN', 'Оборачиваемость'],
            i=id_vars,
            j='_temp_id',
            sep='',
            suffix=r'\d+'
        ).reset_index()
        
        df_plan_long = df_plan_long.drop(columns='_temp_id')
        df_plan_long['Segment'] = df_plan_long['Segment'].fillna('Не задан')
        return df_plan_long
    except Exception as e:
        st.error(f"Ошибка при преобразовании таблицы Плана: {e}.")
        st.info("Убедитесь, что в файле Плана есть группы столбцов с префиксами 'Magazin', 'Plan_STUKI' и т.д.")
        return None

def prepare_fact_data(df_fact):
    """Подготавливает таблицу с фактом к слиянию."""
    required_cols = ['магазин', 'ART', 'Fact_STUKI']
    missing_cols = [col for col in required_cols if col not in df_fact.columns]
    if missing_cols:
        st.error(f"В файле Факта отсутствуют обязательные столбцы: {', '.join(missing_cols)}")
        return None
    df_fact_prepared = df_fact.rename(columns={'магазин': 'Magazin'})
    return df_fact_prepared[['Magazin', 'ART', 'Fact_STUKI']]

def run_data_quality_checks(df, table_name):
    """Проводит базовую проверку качества данных и выводит результат."""
    with st.expander(f"🔍 Проверка качества данных: {table_name}"):
        if df is None:
            st.warning("Файл не загружен или не удалось его прочитать.")
            return
        st.markdown(f"**Размер:** {df.shape[0]} строк, {df.shape[1]} столбцов.")
        st.dataframe(df.head())

@st.cache_data
def to_excel(df):
    """Конвертирует DataFrame в Excel файл для скачивания."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    processed_data = output.getvalue()
    return processed_data

# --- Основной интерфейс приложения Streamlit ---

st.title("Анализатор 'План/Факт'")
st.markdown("Загрузите файлы с плановыми и фактическими показателями для их сличения и анализа.")

# --------------------------------------------------------------------- #
# --- БЛОК 1: ЗАГРУЗКА ФАЙЛОВ И ПРОВЕРКА КАЧЕСТВА ---
# --------------------------------------------------------------------- #
st.sidebar.header("Загрузка файлов")
plan_file = st.sidebar.file_uploader("1. Загрузите файл ПЛАНА", type=['csv', 'xlsx'])
fact_file = st.sidebar.file_uploader("2. Загрузите файл ФАКТА", type=['csv', 'xlsx'])

if plan_file and fact_file:
    df_plan_wide = load_data(plan_file)
    df_fact = load_data(fact_file)
    
    st.header("1. Проверка исходных данных")
    run_data_quality_checks(df_plan_wide, "План (Исходный)")
    run_data_quality_checks(df_fact, "Факт (Исходный)")

    if df_plan_wide is not None and df_fact is not None:
        
        # --------------------------------------------------------------------- #
        # --- БЛОК 2: ПРЕОБРАЗОВАНИЕ И СЛИЯНИЕ ДАННЫХ ---
        # --------------------------------------------------------------------- #
        st.header("2. Обработка и слияние")
        
        with st.spinner('Преобразуем, готовим и сличаем данные...'):
            df_plan_long = transform_plan_to_long(df_plan_wide)
            df_fact_prepared = prepare_fact_data(df_fact)

            if df_plan_long is not None and df_fact_prepared is not None:
                df_final = pd.merge(
                    df_plan_long, df_fact_prepared, how='outer', on=['ART', 'Magazin'], indicator=True
                )
                # Финальная обработка
                df_final['Plan_STUKI'] = df_final['Plan_STUKI'].fillna(0).astype(int)
                df_final['Fact_STUKI'] = df_final['Fact_STUKI'].fillna(0).astype(int)
                df_final['Segment'] = df_final['Segment'].fillna('Продажи без плана')
                df_final['Отклонение_штуки'] = df_final['Fact_STUKI'] - df_final['Plan_STUKI']
                df_final['Выполнение_плана_%'] = (100 * df_final['Fact_STUKI'] / df_final['Plan_STUKI']).replace([float('inf'), -float('inf')], 100).fillna(0).round(2)
                st.success("Данные успешно обработаны и объединены!")
            else:
                st.error("Ошибка на этапе подготовки данных. Невозможно продолжить.")
                st.stop() # Останавливаем выполнение, если подготовка не удалась
        
        st.subheader("Детальная таблица: План/Факт по каждому товару")
        st.dataframe(df_final)

        # --------------------------------------------------------------------- #
        # --- БЛОК 3: АНАЛИТИЧЕСКАЯ СВОДКА ---
        # --------------------------------------------------------------------- #
        st.header("3. Аналитическая сводка по Магазинам и Сегментам")
        try:
            pivot_table = pd.pivot_table(
                df_final, index=['Magazin', 'Segment'],
                values=['Plan_STUKI', 'Fact_STUKI', 'Отклонение_штуки'], aggfunc='sum'
            )
            pivot_table['Выполнение_плана_%'] = (
                100 * pivot_table['Fact_STUKI'] / pivot_table['Plan_STUKI']
            ).replace([float('inf'), -float('inf')], 100).fillna(0).round(2)
            st.dataframe(pivot_table.style.format({
                'Plan_STUKI': '{:,.0f}', 'Fact_STUKI': '{:,.0f}',
                'Отклонение_штуки': '{:,.0f}', 'Выполнение_плана_%': '{:.2f}%'
            }).background_gradient(cmap='RdYlGn', subset=['Выполнение_плана_%'], vmin=0, vmax=120))
        except Exception as e:
            st.error(f"Не удалось построить сводную таблицу: {e}")

        # --------------------------------------------------------------------- #
        # --- НОВЫЙ БЛОК 4: ИНТЕРАКТИВНЫЕ ФИЛЬТРЫ ---
        # --------------------------------------------------------------------- #
        st.header("4. Глубокий анализ и фильтрация")
        st.info("Выберите магазины и сегменты для детального просмотра и выгрузки.")

        # Получаем уникальные значения для фильтров из итоговой таблицы
        all_magazins = sorted(df_final['Magazin'].unique())
        all_segments = sorted(df_final['Segment'].unique())

        # Создаем виджеты для множественного выбора
        selected_magazins = st.multiselect(
            'Выберите Магазин(ы)',
            options=all_magazins,
            default=all_magazins # По умолчанию выбраны все
        )
        selected_segments = st.multiselect(
            'Выберите Сегмент(ы)',
            options=all_segments,
            default=all_segments # По умолчанию выбраны все
        )

        # --------------------------------------------------------------------- #
        # --- НОВЫЙ БЛОК 5: ОТФИЛЬТРОВАННАЯ ТАБЛИЦА И ВЫГРУЗКА ---
        # --------------------------------------------------------------------- #
        st.subheader("Отфильтрованные данные")

        # Применяем фильтры к DataFrame
        if not selected_magazins or not selected_segments:
            st.warning("Пожалуйста, выберите хотя бы один магазин и один сегмент.")
        else:
            filtered_df = df_final[
                df_final['Magazin'].isin(selected_magazins) &
                df_final['Segment'].isin(selected_segments)
            ].copy() # .copy() чтобы избежать SettingWithCopyWarning
            
            # Показываем отфильтрованную таблицу
            st.dataframe(filtered_df)
            st.success(f"Найдено {len(filtered_df)} позиций, соответствующих вашему выбору.")
            
            # Готовим данные для выгрузки
            excel_data = to_excel(filtered_df)

            # Создаем кнопку для скачивания
            st.download_button(
                label="📥 Скачать отчет в Excel",
                data=excel_data,
                file_name="plan_fact_report_filtered.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

else:
    st.info("Пожалуйста, загрузите оба файла в левой панели, чтобы начать анализ.")
