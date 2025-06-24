import streamlit as st
import pandas as pd
import re

st.set_page_config(layout="wide")
st.title("Тестирование преобразования: Широкий формат -> Плоский")

# --- 1. Создание примера "широкого" DataFrame ---
# Это имитирует ваш горизонтальный файл "План"
data = {
    'Артикул': ['ART001', 'ART002', 'ART003'],
    'Описание': ['Кроссовки', 'Ботинки', 'Сандалии'],
    'Цена': [1500, 2200, 800],
    'Бренд': ['Nike', 'Timberland', 'Ecco'],
    '1_Plan_STUKI': [10, 5, 12],
    '1_Plan_GRN': [15000, 11000, 9600],
    '2_Plan_STUKI': [8, 0, 15],
    '2_Plan_GRN': [12000, 0, 12000],
    '15_Plan_STUKI': [20, 8, 5],
    '15_Plan_GRN': [30000, 17600, 4000]
}
wide_df = pd.DataFrame(data)

st.header("Исходная 'широкая' таблица")
st.dataframe(wide_df)
st.markdown("---")

# --- 2. Интерфейс для пользователя ---
st.header("Настройки преобразования")

all_columns = wide_df.columns.tolist()

# Пользователь выбирает колонки, которые описывают товар
id_vars = st.multiselect(
    "Шаг 1: Выберите идентификационные колонки (те, что не меняются от магазина к магазину)",
    options=all_columns,
    default=['Артикул', 'Описание', 'Цена', 'Бренд']
)

# Пользователь указывает суффиксы
col1, col2 = st.columns(2)
with col1:
    suffix_stuki = st.text_input("Шаг 2: Укажите суффикс для плановых штук", value="_Plan_STUKI")
with col2:
    suffix_grn = st.text_input("Шаг 3: Укажите суффикс для плановых гривен", value="_Plan_GRN")

if st.button("🚀 Начать преобразование"):

    if not id_vars or not suffix_stuki or not suffix_grn:
        st.error("Пожалуйста, заполните все настройки.")
    else:
        # --- 3. Этап 1: pd.melt() (Unpivot) ---
        st.subheader("Этап 1: Применение `melt` для 'разворачивания' таблицы")
        
        # Определяем колонки, которые нужно "развернуть"
        value_vars = [col for col in wide_df.columns if col not in id_vars]

        if not value_vars:
            st.error("Не найдено колонок для преобразования. Проверьте выбор идентификационных колонок.")
        else:
            melted_df = pd.melt(
                wide_df,
                id_vars=id_vars,
                value_vars=value_vars,
                var_name='temp_variable',
                value_name='value'
            )
            st.info(f"Таблица 'развернута'. Теперь у нас {len(melted_df)} строк.")
            st.dataframe(melted_df)
            st.markdown("---")

            # --- 4. Этап 2: Извлечение информации ---
            st.subheader("Этап 2: Извлечение 'Магазина' и 'Типа данных' из временной колонки")

            # Создаем копию, чтобы избежать SettingWithCopyWarning
            extracted_df = melted_df.copy()

            # Функция для извлечения номера магазина и типа данных
            def extract_info(variable_name):
                # Ищем число в начале строки - это и есть номер магазина
                match = re.match(r'^(\d+)', variable_name)
                if match:
                    store_id = match.group(1)
                    # Все, что после номера магазина и подчеркивания - это тип данных
                    data_type = variable_name[len(store_id)+1:]
                    return store_id, data_type
                return None, None
            
            # Применяем функцию к колонке 'temp_variable'
            extracted_df[['магазин', 'Тип_данных']] = extracted_df['temp_variable'].apply(
                lambda x: pd.Series(extract_info(x))
            )
            
            # Удаляем временную колонку
            extracted_df = extracted_df.drop(columns=['temp_variable'])
            
            st.info("Созданы новые колонки 'магазин' и 'Тип_данных'.")
            st.dataframe(extracted_df)
            st.markdown("---")

            # --- 5. Этап 3: pivot_table() для сбора данных в одну строку ---
            st.subheader("Этап 3: Применение `pivot_table` для создания финальных колонок")
            
            # Определяем индекс для сводной таблицы - это все, кроме колонок с типами данных и значениями
            pivot_index = id_vars + ['магазин']
            
            try:
                pivoted_df = pd.pivot_table(
                    extracted_df,
                    index=pivot_index,
                    columns='Тип_данных',
                    values='value',
                    aggfunc='first' # Используем 'first', так как на пересечении всегда одно значение
                ).reset_index()

                # Переименовываем колонки для соответствия основному приложению
                final_df = pivoted_df.rename(columns={
                    suffix_stuki[1:]: 'Plan_STUKI', # Убираем '_' в начале
                    suffix_grn[1:]: 'Plan_GRN'
                })
                
                # --- 6. Финальный результат ---
                st.subheader("✅ Готовая 'плоская' таблица")
                st.info("Эта таблица готова для слияния с данными из файла 'Факт'.")
                st.dataframe(final_df)
                
            except Exception as e:
                st.error(f"Ошибка на этапе создания сводной таблицы: {e}")
                st.warning("Возможно, в данных есть дубликаты или проблема с форматом названий колонок.")
